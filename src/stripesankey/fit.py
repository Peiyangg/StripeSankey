"""
Step 2 -- fit one model per k, then take the consensus across k.

One fit per k from a fixed seed. Replicate fits at the same k are a separate
problem and deliberately out of scope: they disagree, and on two real tables
their disagreement is a continuum with no discrete modes to choose between, so
"the model at this k" has no obvious representative. ``modes.py`` holds the
machinery for when that is picked up.

The consensus here is **across k**, which is a different thing: each k's
co-membership has the share expected by chance removed before the k values are
averaged, so the clustering does not drift when the k range changes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .cache import _report_convergence, load_W
from .prep import load_features, load_manifest

__all__ = ["sweep", "verify_pass_loop"]


class _GensimLog(logging.Handler):
    """
    Capture the two things gensim already reports, and change nothing.

    gensim has no convergence API and no early stop -- ``passes`` runs exactly
    ``passes`` times -- but it computes and logs both quantities needed:

    ``topic diff=%f, rho=%f``   (INFO, once per M-step)
        The mean absolute change in ``Elogbeta`` over the last pass: did the
        model settle?
    ``%i/%i documents converged within %i iterations``   (DEBUG, per chunk)
        Is ``iterations`` -- the per-document E-step cap -- high enough?

    Do **not** replace this with a loop of ``update(corpus, passes=1)`` calls.
    gensim's learning rate is
    ``rho = (offset + pass_ + num_updates/chunksize) ** -decay`` and
    ``num_updates`` grows only once per ``update()`` call, so inside a native
    multi-pass run the decay is driven by ``pass_`` while in such a loop
    ``pass_`` is always 0. For a corpus smaller than ``chunksize`` the two
    schedules differ by more than 2x by the last pass, which keeps rho high,
    keeps the bound jittering, and silently stops reproducing earlier figures.
    """

    _DIFF = re.compile(r"topic diff=([\d.eE+-]+|nan|inf), rho=")
    _DOCS = re.compile(r"(\d+)/(\d+) documents converged within (\d+) iterations")

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.topic_diff: list[float] = []
        self.docs_converged: list[tuple[int, int]] = []

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return
        m = self._DIFF.match(msg)
        if m:
            try:
                self.topic_diff.append(float(m.group(1)))
            except ValueError:
                self.topic_diff.append(float("nan"))
            return
        m = self._DOCS.match(msg)
        if m:
            self.docs_converged.append((int(m.group(1)), int(m.group(2))))

    def verdict(self, rel_tol: float) -> dict:
        td = np.asarray(self.topic_diff, dtype=float)
        out: dict = {"passes_run": int(len(td))}
        if td.size and np.isfinite(td).any():
            finite = td[np.isfinite(td)]
            # Scale-free: `topic diff` is a mean absolute change in Elogbeta,
            # whose magnitude depends on the vocabulary size, so no absolute
            # tolerance is portable. Its own starting value sets the scale.
            # (It decays as a power law and never truly plateaus, so a
            # relative-decrement rule would call every run unconverged.)
            out["topic_diff_initial"] = float(finite[0])
            out["topic_diff_final"] = float(finite[-1])
            ratio = float(finite[-1] / finite.max()) if finite.max() > 0 else 0.0
            out["topic_diff_ratio"] = ratio
            out["converged"] = bool(ratio < rel_tol)
        else:
            out["converged"] = None
        if self.docs_converged:
            c = sum(a for a, _ in self.docs_converged)
            n = sum(b for _, b in self.docs_converged)
            out["docs_converged_frac"] = float(c / n) if n else None
        return out


class _NMF:
    """The built-in NMF backend as a picklable callable.

    A closure or lambda would not survive ``spawn``: the worker unpickles the
    factory by import, and a function defined inside another function has no
    importable name. Same reason a user-supplied ``implementation`` has to be
    module-level -- see the check in :func:`sweep`.
    """

    #: cvanmf's single decomposition: GKL loss, multiplicative updates,
    #: nndsvdar init, no regularisation.
    PARAMS = dict(beta_loss="kullback-leibler", solver="mu", init="nndsvdar",
                  max_iter=3000, alpha_W=0.0, alpha_H=0.0, l1_ratio=0.0)

    def __call__(self, k, seed):
        from sklearn.decomposition import NMF
        return NMF(n_components=k, random_state=seed, **self.PARAMS)


_W: dict = {}          # per-worker payload, set by _init_worker


def _init_worker(features_values, index, columns, backend, params):
    _W["X"] = np.asarray(features_values)
    _W["index"] = list(index)
    _W["columns"] = [str(c) for c in columns]
    _W["backend"] = backend
    _W["params"] = params
    if backend == "lda_gensim":
        from gensim.corpora import Dictionary
        dct = Dictionary([_W["columns"]])
        _W["dct"] = dct
        tid = dct.token2id
        _W["corpus"] = [
            [(tid[f], int(c)) for f, c in zip(_W["columns"], row) if c > 0]
            for row in _W["X"]
        ]
    # Quiet gensim's own stdout chatter; the handler below is the only reader.
    for name in ("gensim.models.ldamodel", "gensim.utils", "gensim.corpora.dictionary"):
        logging.getLogger(name).propagate = False


#: gensim's own offset default. The pass loop below adds 1 after the first
#: call; see :func:`_fit_gensim`.
_OFFSET = 1.0


def _settled(td, rel_tol: float, patience: int = 2) -> bool:
    """Has ``topic diff`` fallen below ``rel_tol`` of this run's own peak?

    ``patience`` consecutive passes must agree, so one lucky pass does not end
    training early.
    """
    if len(td) < patience + 1:
        return False
    peak = max(td)
    if not np.isfinite(peak) or peak <= 0:
        return False
    return all(x / peak < rel_tol for x in td[-patience:])


def _fit_gensim(k: int, seed: int, params: dict):
    """
    Fit one LDA model, stopping as soon as it settles.

    gensim has no early stop -- ``passes`` runs exactly ``passes`` times -- so
    the pass loop is driven here, one pass per ``update()`` call, with a
    convergence check in between. **That is only safe because two of gensim's
    internals are compensated for**, and the result is then bit-identical to a
    native multi-pass fit (verified by :func:`verify_pass_loop`):

    1. ``rho = (offset + pass_ + num_updates/chunksize) ** -decay``. In a native
       run the decay is driven by ``pass_``; in a loop ``pass_`` is always 0 and
       ``num_updates`` grows by one corpus per call instead. With
       ``chunksize == len(corpus)`` the two differ by exactly 1 after the first
       call, so ``offset + 1`` from the second call on makes the schedules
       identical.
    2. ``update()`` does ``state.numdocs += lencorpus``, and ``blend()`` uses
       ``state.numdocs`` as the target size that scales the sufficient
       statistics. Left alone it would grow by a corpus per pass and reweight
       every blend, so it is put back before each call.

    Skipping either one is not a small error: the naive loop's ``topic diff``
    departs from the native run's by 0.31 within a dozen passes.
    """
    from gensim.models import LdaModel

    cap = _GensimLog()
    glog = logging.getLogger("gensim.models.ldamodel")
    glog.setLevel(logging.DEBUG)
    prev, glog.handlers = glog.handlers, [cap]
    n_docs = len(_W["corpus"])
    try:
        model = LdaModel(
            corpus=_W["corpus"], id2word=_W["dct"], num_topics=k,
            passes=1, iterations=params["iterations"],
            alpha=params["alpha"], eta=params["eta"],
            random_state=seed, eval_every=None,
            chunksize=n_docs, offset=_OFFSET,
        )
        rel_tol = params["rel_tol"]
        for _ in range(params["max_passes"] - 1):
            if _settled(cap.topic_diff, rel_tol):
                break
            model.state.numdocs = 0                      # (2)
            model.update(_W["corpus"], passes=1, chunksize=n_docs,
                         offset=_OFFSET + 1.0)           # (1)
        gamma = model.inference(_W["corpus"])[0]
        W = gamma / gamma.sum(axis=1, keepdims=True)      # sample x LC
        # Dictionary ids follow first-appearance order, so reorder H's columns
        # onto `columns` -- both backends then return H aligned to the feature
        # table.
        order = [_W["dct"].token2id[f] for f in _W["columns"]]
        H = model.get_topics()[:, order]                  # LC x feature
        diag = cap.verdict(params["rel_tol"])
        # The whole trajectory, not just its endpoints: the shape is what shows
        # that the tail is a power law rather than a plateau, and it is only
        # `passes` floats per run.
        diag["topic_diff_series"] = [float(x) for x in cap.topic_diff]
        diag["perplexity"] = float(np.exp(-model.log_perplexity(_W["corpus"])))
    finally:
        glog.handlers = prev
    return W, H, diag


def _fit_sklearn(k: int, seed: int, params: dict):
    """
    Fit any sklearn-shaped decomposition and return ``(W, H)``.

    sklearn uses the same convention as the paper, so the two map straight
    across -- ``X (samples x features) ~ W . H``::

        W == fit_transform()   (samples, k)   row-normalised here
        H == components_       (k, features)
    """
    import warnings as _w
    from sklearn.exceptions import ConvergenceWarning

    est = params["factory"](k, seed)
    X = _W["X"].astype(float)
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        loadings = est.fit_transform(X)            # (samples, k)
        hit_cap = any(c.category is ConvergenceWarning for c in caught)

    H = est.components_                            # (k, features)
    totals = loadings.sum(axis=1, keepdims=True)
    totals[totals == 0] = 1.0
    W = loadings / totals                          # (samples, k)

    n_iter = getattr(est, "n_iter_", None)
    max_iter = getattr(est, "max_iter", None)
    diag = {
        "n_iter": int(n_iter) if n_iter is not None else None,
        "max_iter": int(max_iter) if max_iter is not None else None,
        # sklearn's NMF raises ConvergenceWarning at the cap; its LDA does not
        # warn at all, so `n_iter_ == max_iter` is the uniform fallback.
        "converged": (not hit_cap) if n_iter is None
        else bool(not hit_cap and n_iter < max_iter),
    }
    err = getattr(est, "reconstruction_err_", None)
    if err is not None:
        diag["reconstruction_err"] = float(err)
    return W, H, diag


def _fit_one(task):
    k, seed = task
    t0 = time.perf_counter()
    fn = _fit_gensim if _W["backend"] == "lda_gensim" else _fit_sklearn
    W, H, diag = fn(k, seed, _W["params"])
    diag["seconds"] = round(time.perf_counter() - t0, 3)
    return k, seed, W.astype(np.float32), H.astype(np.float32), diag


def _coherence(H: pd.DataFrame, texts, dictionary, topn=20):
    """``c_v`` from an H table, so no model object has to be kept."""
    from gensim.models import CoherenceModel

    topics = [list(H.loc[lc].nlargest(topn).index) for lc in H.index]
    cm = CoherenceModel(topics=topics, texts=texts, dictionary=dictionary,
                        coherence="c_v", topn=topn)
    return float(cm.get_coherence())


#: The fitting budget. Both entries are CEILINGS, not costs: each has an early
#: exit, so setting them high buys headroom rather than time.
#:
#: `iterations` is gensim's own per-document cap and already exits at
#: `gamma_threshold` -- a document that settles in 300 sweeps never runs 5000.
#: `max_passes` is enforced by the pass loop in `_fit_gensim`, which stops as
#: soon as the run settles. Measured need: 40-55 passes on one real table,
#: 61-118 on another, so 400 is headroom for both while costing what the data
#: actually asks for.
#:
#: Neither is assumed to have been enough -- both are measured per run and
#: reported (see `convergence_report`). Override via **fit_params if you must.
_FIT_BUDGET = {"max_passes": 400, "iterations": 5000,
               "alpha": "auto", "eta": "auto"}


def _write_fit(res, k, seed, W, H, diag, features, lcs, diags, verbose):
    """Persist one fit as it lands, so a crash loses one k rather than the sweep."""
    pd.DataFrame(W, index=features.index, columns=lcs(k)
                 ).to_csv(os.path.join(res, "W", f"W_{k}.csv"))
    pd.DataFrame(H, index=lcs(k), columns=features.columns
                 ).to_csv(os.path.join(res, "H", f"H_{k}.csv"))
    if diag.get("topic_diff_series"):
        ddir = os.path.join(res, "diagnostics")
        os.makedirs(ddir, exist_ok=True)
        pd.Series(diag["topic_diff_series"], name="topic_diff"
                  ).rename_axis("pass").to_csv(
            os.path.join(ddir, f"topic_diff_{k}.csv"))
    diag.update({"k": k, "seed": seed})
    diags.append(diag)
    if verbose:
        print(f"  k={k:>3}  {diag['seconds']:6.1f}s  "
              f"{diag.get('passes_run', '-')} passes  "
              f"{'settled' if diag.get('converged') else 'NOT settled'}", flush=True)


def sweep(base_directory: str,
          k_range: Iterable[int],
          *,
          implementation: str | Callable = "lda_gensim",
          random_state: int = 42,
          rel_tol: float = 1e-3,
          workers: int | None = None,
          force: bool = False,
          verbose: bool = True,
          **fit_params) -> dict:
    """
    Fit one model per k, then take the consensus across k.

    One fit per k, from a fixed seed. Replicate fits at the same k are a
    separate problem -- they disagree, and on two real tables their
    disagreement forms a continuum with no discrete modes to choose between --
    and this does not attempt it. See *Still open* in ``API_lda4microbiome.md``.

    The consensus is **across k**, which is a different thing: each k's
    co-membership has the share expected by chance removed before the k values
    are averaged, so the clustering does not drift when the k range changes.

    Args:
        base_directory: the folder ``prepare()`` wrote to; read and written.
        k_range: the k values to fit.
        implementation: ``'lda_gensim'``, ``'nmf'``, or a callable
            ``(k, seed) -> estimator`` satisfying sklearn's decomposition
            protocol (``fit_transform() -> W``, ``.components_ -> H``), which
            is the same convention this package uses. A callable
            must be importable by name -- module-level ``def`` or a class with
            ``__call__``, not a lambda -- because fits run in a spawn-based
            pool. Checked before any work is submitted.
        random_state: the seed. One fit per k means this fixes the result.
        rel_tol: a fit counts as settled when its final ``topic diff`` is below
            ``rel_tol`` of its own peak -- scale-free, because the raw value
            depends on vocabulary size.

            **The default is loose on purpose.** Measured over 450 fits at
            ``iterations=5000`` and a 150-pass budget, the ratio was tightly
            clustered: median 1.1e-4 at every k, min 2e-5, max 1.5e-3. There is
            no bimodality -- no "converged" and "not converged" population,
            just one spread -- so a cut at 1e-4 lands on the median and fails
            half the fits for no reason. 1e-3 sits above the bulk while still
            failing a genuinely under-trained fit (``passes=20,
            iterations=400`` gives 8.5e-3). It is also what the pass loop stops
            on, so it decides run time as well as the verdict.

            The companion number, ``docs_converged_frac``, is the one with a
            clean separation (0.54 at ``iterations=400`` against 0.95-0.99 at
            5000) and it gates a different limit -- the per-document cap.
        workers: processes to fit with (default: ``min(cpu_count, 10)``).
            ``workers=1`` fits in-process with no pool at all, which is the way
            out of any context where ``spawn`` cannot re-import the calling
            module -- a REPL, a piped script, some notebook setups.
        force: refit k values already on disk.
        **fit_params: override the fitting budget (``max_passes``,
            ``iterations``, ``alpha``, ``eta``). You should not need to. Both
            limits are ceilings with an early exit, so they are set high and
            each fit takes only as long as it needs; whether a ceiling was
            reached is measured, not assumed.

    .. important::
       Fits run in a process pool, and on macOS and Windows that means
       ``spawn``: each worker re-imports the calling module. A script that
       calls ``sweep()`` at import time therefore spawns workers that call it
       again, forever. Put the call behind ``if __name__ == "__main__":``.

    Returns the ``run_info`` dict.
    """
    res = os.path.join(base_directory, "results")
    for sub in ("W", "H"):
        os.makedirs(os.path.join(res, sub), exist_ok=True)

    manifest = load_manifest(base_directory)
    features = load_features(base_directory)
    k_list = sorted(set(int(k) for k in k_range))

    if callable(implementation):
        backend, factory, label = "callable", implementation, getattr(
            implementation, "__name__", "callable")
    elif implementation == "lda_gensim":
        backend, factory, label = "lda_gensim", None, "lda_gensim"
    elif implementation == "nmf":
        backend, factory, label = "callable", _NMF(), "nmf"
    else:
        raise ValueError(
            f"implementation={implementation!r}: expected 'lda_gensim', 'nmf', "
            "or a callable (k, seed) -> estimator"
        )

    if factory is not None:
        # Fail here, with a sentence that says what to do, rather than inside
        # multiprocessing with `Can't get local object '<locals>.factory'`.
        import pickle
        try:
            pickle.loads(pickle.dumps(factory))
        except Exception as exc:
            raise TypeError(
                f"implementation={label!r} cannot be sent to a worker process "
                f"({exc}). Fits run in a spawn-based pool, so the callable has "
                "to be importable by name: define it at module level (a plain "
                "`def`, or a class with `__call__`), not as a lambda or a "
                "function nested inside another."
            ) from exc

    unknown = set(fit_params) - set(_FIT_BUDGET)
    if unknown:
        raise TypeError(f"unexpected fit_params {sorted(unknown)}; "
                        f"overridable: {sorted(_FIT_BUDGET)}")
    budget = {**_FIT_BUDGET, **fit_params}
    params = {**budget, "rel_tol": rel_tol, "factory": factory}

    todo = k_list if force else [
        k for k in k_list
        if not os.path.exists(os.path.join(res, "W", f"W_{k}.csv"))
    ]
    if verbose:
        skipped = sorted(set(k_list) - set(todo))
        print(f"[sweep] {label}: k={k_list} -> {len(todo)} fit(s)"
              + (f" ({skipped} already on disk, skipped)" if skipped else ""))

    workers = workers or min(os.cpu_count() or 1, 10)
    diags: list[dict] = []
    lcs = lambda n: [f"LC{i}" for i in range(n)]

    t0 = time.perf_counter()
    if todo and workers == 1:
        # In-process, no pool. `workers=1` is the escape hatch for any context
        # where spawn cannot re-import the calling module -- a REPL, a piped
        # heredoc, some notebook setups -- which otherwise fails with
        # `BrokenProcessPool` and nothing useful to read.
        _init_worker(features.to_numpy(), features.index, features.columns,
                     backend, params)
        for done, k in enumerate(todo, start=1):
            k, seed, W, H, diag = _fit_one((k, random_state))
            _write_fit(res, k, seed, W, H, diag, features, lcs, diags, verbose)
    elif todo:
        # One BLAS thread per worker. Each fit is single-threaded work anyway,
        # and `workers` processes each spawning `cpu_count` BLAS threads
        # oversubscribes the machine. This has to be set in the PARENT: a
        # spawned worker reads these at numpy import time, before the
        # initializer runs.
        for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                   "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ.setdefault(_v, "1")
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker,
            initargs=(features.to_numpy(), features.index, features.columns,
                      backend, params),
        ) as pool:
            futs = [pool.submit(_fit_one, (k, random_state)) for k in todo]
            for fut in as_completed(futs):
                k, seed, W, H, diag = fut.result()
                _write_fit(res, k, seed, W, H, diag, features, lcs, diags, verbose)

    # ---- consensus ACROSS k -----------------------------------------------
    # `consensus_affinity` removes the co-membership expected by chance at each
    # k *before* averaging, so the answer does not drift when the k range
    # changes -- which is the whole reason it is keyed by k.
    from . import mr_consensus as mrc

    Ws = load_W(base_directory, k_list)
    index = next(iter(Ws.values())).index
    Q = mrc.consensus_affinity({k: df.to_numpy() for k, df in Ws.items()})
    labels = np.asarray(mrc.cluster_from_affinity(Q, resolution=0.0,
                                                  noise_threshold=0.0))
    # Q itself is not stored: it is N x N (47 MB at 2,400 samples) and
    # recomputable from W in a second. The labels are what the figures read.
    consensus = {
        "k_pooled": sorted(Ws),
        "sample_to_cluster": {str(s): int(l) for s, l in zip(index, labels)},
        "sizes": {int(c): int((labels == c).sum()) for c in sorted(set(labels))},
    }
    with open(os.path.join(res, "consensus.json"), "w") as f:
        json.dump(consensus, f, indent=2)
    if verbose:
        print(f"[sweep] consensus across k={consensus['k_pooled']}: "
              f"{len([c for c in consensus['sizes'] if c >= 0])} cluster(s) "
              f"{consensus['sizes']}")

    conv = {str(d["k"]): {q: d.get(q) for q in
                          ("converged", "topic_diff_final", "topic_diff_ratio",
                           "docs_converged_frac", "passes_run", "n_iter",
                           "max_iter", "perplexity", "reconstruction_err",
                           "seconds") if d.get(q) is not None}
            for d in diags}

    metrics = _representative_metrics(base_directory, k_list, conv, verbose=verbose)

    run_info = {
        "implementation": label,
        "level": manifest.get("level"),
        "k_list": k_list,
        "random_state": random_state,
        "params": {**budget, "rel_tol": rel_tol},
        "left_axis": "perplexity" if backend == "lda_gensim" else "reconstruction_err",
        "convergence": conv,
        "seconds": round(time.perf_counter() - t0, 1),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    info_path = os.path.join(res, "run_info.json")
    if os.path.exists(info_path) and not force:
        old = json.load(open(info_path))
        merged = {**(old.get("convergence") or {}), **conv}
        run_info = {**old, **run_info, "convergence": merged}
    with open(info_path, "w") as f:
        json.dump(run_info, f, indent=2)
    metrics.to_csv(os.path.join(res, "metrics.csv"), index=False)

    _report_convergence(run_info, verbose=verbose)
    return run_info


def _presence_texts(features: pd.DataFrame) -> list[list[str]]:
    """
    One token list per sample: the features **present**, not repeated by count.

    ``c_v`` slides a window over each text to estimate co-occurrence. Repeating
    a feature by its abundance -- 42 million tokens on a real table -- makes
    that window see one feature at a time and destroys the very statistic it is
    measuring, besides being unusable in memory.
    """
    cols = np.asarray([str(c) for c in features.columns])
    X = features.to_numpy()
    return [list(cols[row > 0]) for row in X]


def _representative_metrics(base_directory, k_list, conv, *, verbose=True) -> pd.DataFrame:
    """Coherence + the left-axis loss, per k.

    ``conv`` is passed in rather than re-read: run_info.json is written after
    this runs, so on a first sweep there is no file to read the loss out of.
    """
    features = load_features(base_directory)
    info_path = os.path.join(base_directory, "results", "run_info.json")
    prev = json.load(open(info_path)) if os.path.exists(info_path) else {}
    conv = {**(prev.get("convergence") or {}), **(conv or {})}

    rows, texts, dct = [], None, None
    for k in sorted(k_list):
        hpath = os.path.join(base_directory, "results", "H", f"H_{k}.csv")
        if not os.path.exists(hpath):
            continue
        row: dict = {"K": int(k)}
        here = conv.get(str(k), {})
        for q in ("perplexity", "reconstruction_err"):
            if q in here:
                row[q] = here[q]
        try:
            if texts is None:
                from gensim.corpora import Dictionary
                texts = _presence_texts(features)
                dct = Dictionary(texts)
            row["Coherence"] = _coherence(pd.read_csv(hpath, index_col=0), texts, dct)
        except Exception as exc:                      # pragma: no cover
            row["Coherence"] = float("nan")
            if verbose:
                print(f"  k={k}: coherence unavailable ({exc})")
        rows.append(row)
    return pd.DataFrame(rows)


def verify_pass_loop(corpus=None, dictionary=None, *, k: int = 4, passes: int = 10,
                     seed: int = 7, verbose: bool = True) -> dict:
    """
    Check that the pass loop still reproduces a native gensim fit exactly.

    :func:`_fit_gensim` drives gensim's pass loop itself so it can stop when a
    run settles, and it compensates for two gensim internals to do so (the
    ``rho`` schedule and ``state.numdocs``). Both are undocumented, so this
    runs the same fit both ways and compares. It is the thing that turns "we
    poke two private attributes" into a tested invariant: if a gensim release
    changes either, this fails loudly instead of the sweep silently producing
    different models.

    Pass a corpus, or leave it out for a small synthetic one.
    """
    from gensim.corpora import Dictionary
    from gensim.models import LdaModel

    if corpus is None:
        rng = np.random.default_rng(0)
        vocab = [f"w{i}" for i in range(60)]
        dictionary = Dictionary([vocab])
        tid = dictionary.token2id
        counts = rng.poisson(4, (40, 60))
        corpus = [[(tid[w], int(c)) for w, c in zip(vocab, row) if c > 0]
                  for row in counts]
    n = len(corpus)
    common = dict(id2word=dictionary, num_topics=k, iterations=400,
                  alpha="auto", eta="auto", random_state=seed,
                  eval_every=None, chunksize=n, offset=_OFFSET)

    cap_a = _GensimLog()
    glog = logging.getLogger("gensim.models.ldamodel")
    glog.setLevel(logging.DEBUG)
    prev = glog.handlers
    try:
        glog.handlers = [cap_a]
        native = LdaModel(corpus=corpus, passes=passes, **common)

        cap_b = _GensimLog()
        glog.handlers = [cap_b]
        looped = LdaModel(corpus=corpus, passes=1, **common)
        for _ in range(passes - 1):
            looped.state.numdocs = 0
            looped.update(corpus, passes=1, chunksize=n, offset=_OFFSET + 1.0)
    finally:
        glog.handlers = prev

    diff_dev = float(np.max(np.abs(np.asarray(cap_a.topic_diff)
                                   - np.asarray(cap_b.topic_diff))))
    topic_dev = float(np.max(np.abs(native.get_topics() - looped.get_topics())))
    ok = diff_dev == 0.0 and topic_dev < 1e-12
    out = {"ok": ok, "topic_diff_deviation": diff_dev,
           "topics_deviation": topic_dev, "passes": passes}
    if verbose:
        print(f"[verify_pass_loop] {'OK' if ok else 'MISMATCH'} -- "
              f"topic_diff deviation {diff_dev:.3e}, "
              f"topics deviation {topic_dev:.3e}")
    if not ok:
        raise AssertionError(
            "the pass loop no longer reproduces a native gensim fit "
            f"(topic_diff deviation {diff_dev:.3e}, topics {topic_dev:.3e}). "
            "gensim's rho schedule or state.numdocs handling has changed; "
            "_fit_gensim's compensations need revisiting before any sweep is "
            "trusted."
        )
    return out
