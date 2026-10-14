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
import pickle
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from . import mallet as _mallet
from .cache import _ks_on_disk, _report_convergence, load_W
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
    """The built-in NMF backend: a ``(k, seed) -> estimator`` factory, the
    same shape as a user-supplied ``implementation``."""

    #: cvanmf's single decomposition: GKL loss, multiplicative updates,
    #: nndsvdar init, no regularisation. `max_iter` is a ceiling, not a cost:
    #: sklearn stops as soon as the loss settles (`tol`). Measured need on HRD
    #: at k=2..4: 50-360 iterations. It is not overridable -- `fit_params`
    #: covers gensim only -- which is why it is set this high.
    PARAMS = dict(beta_loss="kullback-leibler", solver="mu", init="nndsvdar",
                  max_iter=10000, alpha_W=0.0, alpha_H=0.0, l1_ratio=0.0)

    def __call__(self, k, seed):
        from sklearn.decomposition import NMF
        return NMF(n_components=k, random_state=seed, **self.PARAMS)


_W: dict = {}          # per-worker payload, set by _init_worker


def _init_pool_worker(features_values, index, columns, backend, params):
    _init_worker(features_values, index, columns, backend, params)
    if backend == "lda_mallet":
        # Pool workers only: with workers=1 this is the caller's process, not
        # ours to rewire.
        _mallet._exit_on_sigterm()


def _init_worker(features_values, index, columns, backend, params):
    _W["X"] = np.asarray(features_values)
    _W["index"] = list(index)
    _W["columns"] = [str(c) for c in columns]
    _W["backend"] = backend
    _W["params"] = params
    if params.get("factory") is not None:
        # Pickled by value in the parent -- see `sweep`.
        _W["params"] = {**params, "factory": pickle.loads(params["factory"])}
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
    if _W["backend"] == "lda_gensim":
        W, H, diag = _fit_gensim(k, seed, _W["params"])
    elif _W["backend"] == "lda_mallet":
        W, H, diag = _mallet._fit_mallet(k, seed, _W["params"], _W["X"])
    else:
        W, H, diag = _fit_sklearn(k, seed, _W["params"])
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
#: soon as the run settles. Measured need across the real tables tried: 35-332
#: passes (HRD at k=2..4: 35-98). 1000 is about three times the most any of
#: them needed, while costing only what the data actually asks for.
#:
#: Neither is assumed to have been enough -- both are measured per run and
#: reported (see `convergence_report`). Override via **fit_params if you must.
_FIT_BUDGET = {"max_passes": 1000, "iterations": 5000,
               "alpha": "auto", "eta": "auto"}

#: MALLET's budget. `max_iter` is the ceiling on Gibbs sweeps, not their cost:
#: the run stops as soon as the model has settled (see `mallet._fit_mallet`),
#: which is checked from sweep 1500 on. Measured on HRD at k=2..10: 1550-1950
#: sweeps across 27 fits, so 3000 leaves 1500 sweeps of headroom past the first
#: check. The rest are MALLET's own flags with the old
#: pipeline's values: `alpha` is MALLET's SumAlpha, and `optimize_interval=10`
#: re-estimates alpha and beta every 10 sweeps once `optimize_burn_in` have run.
_MALLET_BUDGET = {"max_iter": 3000, "alpha": 5.0, "beta": 0.01,
                  "optimize_interval": 10, "optimize_burn_in": 200}

#: Default `rel_tol` per backend: each is a ratio of a different quantity.
_REL_TOL = {"lda_gensim": 1e-3, "lda_mallet": 5e-3}


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
    if diag.get("ll_series"):
        ddir = os.path.join(res, "diagnostics")
        os.makedirs(ddir, exist_ok=True)
        pd.Series(diag.pop("ll_series"), name="ll_per_token"
                  ).rename_axis("iteration").to_csv(os.path.join(ddir, f"ll_{k}.csv"))
    diag.update({"k": k, "seed": seed})
    diags.append(diag)
    if verbose:
        steps = (f"{diag['passes_run']} passes" if "passes_run" in diag
                 else f"{diag['n_iter']} iterations" if diag.get("n_iter") is not None
                 else "-")
        print(f"  k={k:>3}  {diag['seconds']:6.1f}s  {steps}  "
              f"{'settled' if diag.get('converged') else 'NOT settled'}", flush=True)


def sweep(base_directory: str,
          k_range: Iterable[int] | None = None,
          *,
          implementation: str | Callable = "lda_gensim",
          mallet: str | os.PathLike | None = None,
          random_state: int = 42,
          rel_tol: float | None = None,
          resolution: float = 0.0,
          noise_threshold: float = 0.0,
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

    A k whose ``results/W/W_{k}.csv`` already exists is not refitted, so
    ``sweep(base)`` with no ``k_range`` fits nothing and only computes the
    consensus over the W tables on disk. That is how a sweep fitted elsewhere
    -- in R, with ADMIXTURE, by pong -- gets its consensus: save each W as
    ``results/W/W_{k}.csv`` (rows = samples, the same samples in the same
    order at every k) and call ``sweep(base)``. ``prepare()`` is only needed
    when there is something to fit.

    Args:
        base_directory: the folder ``prepare()`` wrote to; read and written.
        k_range: the k values to fit. Default: the k values already in
            ``results/W/``, so nothing is fitted.
        implementation: ``'lda_gensim'``, ``'lda_mallet'``, ``'nmf'``, or a
            callable ``(k, seed) -> estimator`` satisfying sklearn's
            decomposition protocol (``fit_transform() -> W``,
            ``.components_ -> H``), which is the same convention this package
            uses. Any callable works -- a ``def`` in a notebook cell, a lambda,
            a closure -- because it is sent to the worker processes by value.
            Checked before any work is submitted.
        mallet: for ``implementation='lda_mallet'`` only, and required by it:
            MALLET's ``bin/mallet`` launcher, or the MALLET folder holding it.
            MALLET is not bundled -- download it from
            https://mimno.github.io/Mallet/ -- and needs Java on ``PATH``.
        random_state: the seed. One fit per k means this fixes the result.
            MALLET reads a seed of 0 as "seed from the clock", so
            ``lda_mallet`` takes 1 to 2**31 - 1.
        rel_tol: when a fit counts as settled; default per backend.

            ``lda_gensim`` (1e-3): its final ``topic diff`` is below
            ``rel_tol`` of its own peak -- scale-free, because the raw value
            depends on vocabulary size.

            ``lda_mallet`` (5e-3): ``LL/token`` gained over the last 200
            sweeps is below ``rel_tol`` of what the run has gained in total,
            AND W has stopped drifting -- it is no further from the model 200
            sweeps back than from the one 50 sweeps back, give or take 15%.
            A Gibbs chain never stops moving, so this is "only the chain's own
            noise is left". Checked every 50 sweeps from sweep 1500 on, so
            every fit runs at least 1500 sweeps: a chain can sit in one state
            for hundreds of sweeps and then jump to a better one, which no
            test on its past can foresee. Two checks in a row must pass. The W
            and H saved are the average of the last 200 sweeps (5
            checkpoints), not a single draw.

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
        resolution, noise_threshold: the consensus clustering, passed to
            :func:`cluster_from_affinity`. Higher ``resolution`` gives more,
            smaller clusters; a sample whose mean affinity to its own cluster
            is at most ``noise_threshold`` is labelled ``-1``. Nothing is
            refitted to change them: ``sweep(base, resolution=0.1)``.
        workers: processes to fit with (default: ``min(cpu_count, 10)``).
            ``workers=1`` fits in-process with no pool at all, which is the way
            out of any context where ``spawn`` cannot re-import the calling
            module -- a REPL, a piped script, some notebook setups.
        force: refit k values already on disk.
        **fit_params: override the fitting budget -- ``lda_gensim``:
            ``max_passes``, ``iterations``, ``alpha``, ``eta``; ``lda_mallet``:
            ``max_iter``, ``alpha``, ``beta``, ``optimize_interval``,
            ``optimize_burn_in``. You should not need to. The limits are
            ceilings with an early exit, so they are set high and each fit
            takes only as long as it needs; whether a ceiling was reached is
            measured, not assumed.

    .. important::
       Fits run in a process pool, and on macOS and Windows that means
       ``spawn``: each worker re-imports the calling module. A script that
       calls ``sweep()`` at import time therefore spawns workers that call it
       again, forever. Put the call behind ``if __name__ == "__main__":``.

    Returns the ``run_info`` dict.
    """
    res = os.path.join(base_directory, "results")
    on_disk = _ks_on_disk(base_directory)
    if k_range is None:
        if not on_disk:
            raise FileNotFoundError(
                f"no W tables in {res}/W. Pass k_range to fit them, or save a "
                "sweep fitted elsewhere there as W_<k>.csv, one file per k.")
        k_list = on_disk
    else:
        k_list = sorted(set(int(k) for k in k_range))

    if callable(implementation):
        backend, factory, label = "callable", implementation, getattr(
            implementation, "__name__", "callable")
    elif implementation == "lda_gensim":
        backend, factory, label = "lda_gensim", None, "lda_gensim"
    elif implementation == "lda_mallet":
        backend, factory, label = "lda_mallet", None, "lda_mallet"
    elif implementation == "nmf":
        backend, factory, label = "callable", _NMF(), "nmf"
    else:
        raise ValueError(
            f"implementation={implementation!r}: expected 'lda_gensim', "
            "'lda_mallet', 'nmf', or a callable (k, seed) -> estimator"
        )
    if backend == "lda_mallet":
        if mallet is None:
            raise TypeError("implementation='lda_mallet' needs mallet=: the path "
                            "to MALLET's bin/mallet (https://mimno.github.io/Mallet/)")
        mallet = _mallet._launcher(mallet)
        if not (isinstance(random_state, (int, np.integer))
                and 1 <= random_state <= 2**31 - 1):
            raise ValueError(
                f"random_state={random_state!r}: lda_mallet needs an integer in "
                "1..2**31-1. MALLET reads 0 as 'seed from the clock', which would "
                "make the sweep unrepeatable.")
    elif mallet is not None:
        raise TypeError(f"mallet= is only used by implementation='lda_mallet', "
                        f"not {label!r}")

    if factory is not None:
        # Sent to the workers BY VALUE. Plain pickle sends a function by name,
        # and one defined in a notebook lives in a `__main__` that a spawned
        # worker does not have: it passed a pickle round-trip here and then
        # broke the pool. cloudpickle sends the code itself. Fail here, with a
        # sentence that says what to do, rather than inside multiprocessing.
        import cloudpickle
        try:
            factory = cloudpickle.dumps(factory)
        except Exception as exc:
            raise TypeError(
                f"implementation={label!r} cannot be sent to a worker process "
                f"({exc}). Whatever the function refers to has to be "
                "picklable: create open files, locks or connections inside it."
            ) from exc

    defaults = _MALLET_BUDGET if backend == "lda_mallet" else _FIT_BUDGET
    unknown = set(fit_params) - set(defaults)
    if unknown:
        raise TypeError(f"unexpected fit_params {sorted(unknown)}; "
                        f"overridable: {sorted(defaults)}")
    budget = {**defaults, **fit_params}
    if rel_tol is None:
        rel_tol = _REL_TOL.get(backend, _REL_TOL["lda_gensim"])
    params = {**budget, "rel_tol": rel_tol, "factory": factory}

    todo = k_list if force else [k for k in k_list if k not in on_disk]
    if todo:
        try:
            manifest = load_manifest(base_directory)
            features = load_features(base_directory)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"no W table for k={todo}, and nothing to fit one from: "
                f"{base_directory} has no intermediate/ -- run prepare() first."
            ) from None
        for sub in ("W", "H"):
            os.makedirs(os.path.join(res, sub), exist_ok=True)
        if backend == "lda_mallet":
            # Once, here, before any worker exists: every k reads the same
            # imported corpus, and it is reused until features.csv changes.
            logdir = os.path.join(res, "diagnostics")
            os.makedirs(logdir, exist_ok=True)
            params.update(mallet=mallet, logdir=logdir, corpus=_mallet._corpus(
                base_directory, features.to_numpy(), mallet, verbose=verbose))
    if verbose:
        skipped = sorted(set(k_list) - set(todo))
        if todo:
            print(f"[sweep] {label}: k={k_list} -> {len(todo)} fit(s)"
                  + (f" ({skipped} already on disk, skipped)" if skipped else ""))
        else:
            print(f"[sweep] k={k_list}: every W is on disk, nothing to fit")

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
            max_workers=workers, initializer=_init_pool_worker,
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
    from .api import _check

    Ws = load_W(base_directory, k_list)
    # The check the figures make, made before anything is written: W tables
    # saved from elsewhere are where a reordered sample index comes from, and
    # the consensus pairs samples by row position.
    _check(Ws)
    index = next(iter(Ws.values())).index
    Q = mrc.consensus_affinity({k: df.to_numpy() for k, df in Ws.items()})
    labels = np.asarray(mrc.cluster_from_affinity(
        Q, resolution=resolution, noise_threshold=noise_threshold))
    # Q itself is not stored: it is N x N (47 MB at 2,400 samples) and
    # recomputable from W in a second. The labels are what the figures read.
    consensus = {
        "k_pooled": sorted(Ws),
        "resolution": resolution,
        "noise_threshold": noise_threshold,
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
                           "max_iter", "ll_ratio", "w_drift", "averaged",
                           "ll_final", "perplexity", "reconstruction_err",
                           "seconds") if d.get(q) is not None}
            for d in diags}

    # Coherence needs the feature table, which a sweep fitted elsewhere does
    # not come with -- and the figures need only W.
    metrics = None
    if os.path.exists(os.path.join(base_directory, "intermediate", "features.csv")):
        metrics = _representative_metrics(base_directory, k_list, conv,
                                          verbose=verbose)

    if todo:
        run_info = {
            "implementation": label,
            "level": manifest.get("level"),
            "k_list": k_list,
            "random_state": random_state,
            "params": {**budget, "rel_tol": rel_tol,
                       **({"mallet": mallet} if backend == "lda_mallet" else {})},
            "left_axis": ("perplexity" if backend in ("lda_gensim", "lda_mallet")
                          else "reconstruction_err"),
        }
    else:
        run_info = {"k_list": k_list}
    run_info.update({
        "convergence": conv,
        "seconds": round(time.perf_counter() - t0, 1),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    info_path = os.path.join(res, "run_info.json")
    old = json.load(open(info_path)) if os.path.exists(info_path) and not force else {}
    # With nothing fitted here, the run that wrote the W tables on disk still
    # describes them, so its record stands; tables saved from elsewhere have
    # no record, and are marked as such.
    run_info = {"implementation": "external", **old, **run_info,
                "convergence": {**(old.get("convergence") or {}), **conv}}
    with open(info_path, "w") as f:
        json.dump(run_info, f, indent=2)
    if metrics is not None:
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
