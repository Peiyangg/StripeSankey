"""
The ``lda_mallet`` backend: MALLET's collapsed Gibbs sampler, run as a
subprocess and stopped once the model it samples has stopped moving.

MALLET is a Java program the caller installs (https://mimno.github.io/Mallet/);
``sweep(implementation="lda_mallet", mallet=...)`` points at its ``bin/mallet``.
Nothing here links against Java: the corpus goes in through ``import-file``,
training is ``train-topics``, and W and H are rebuilt from the sampler's state.

Four MALLET behaviours shape this file (read off the 2021-08 source, and each
checked against a real run on HRD):

1. ``train-topics`` has no convergence test -- ``--num-iterations`` runs that
   many sweeps -- but it logs ``<t> LL/token`` after every 10th sweep.
2. Every output is written after the sweep loop exits, and with
   ``--output-state-interval`` set the final state is not written at all. So
   the run checkpoints its state every ``_CHECKPOINT`` sweeps, each checkpoint
   is rebuilt into W and H as it lands, and the run is killed once it settles.
3. ``state.gz.<t>`` is written at the *top* of iteration t: it is the chain
   after t - 1 sweeps, and it is complete by the time ``<t> LL/token`` -- logged
   after sweep t -- is read. Hence ``n_iter = t - 1``.
4. The ``LL/token`` number is formatted in the JVM's locale: ``-5,50053`` on a
   Belgian machine. The JVM is pinned to ``en_US``, and a number that still
   does not parse stops the fit instead of being misread.

A Gibbs chain does not converge to a point. It converges to a distribution and
keeps sampling from it, so "converged" here means two measured things: the
chain has stopped drifting, and the W handed back is not one noisy draw but the
average of the last ``_AVERAGE`` checkpoints.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile

import numpy as np
import pandas as pd

#: Sweeps between state checkpoints. Every checkpoint is rebuilt into W and H
#: (about 1 s for HRD's 6.5M tokens) and deleted; one is 17 MB gzipped there.
_CHECKPOINT = 50

#: The stop rule's two windows, both 200 sweeps. The likelihood trend is fitted
#: over the last ``_WINDOW`` ``LL/token`` points (10 sweeps each); W's drift
#: compares the newest checkpoint with the one ``_DRIFT_LAG`` checkpoints back.
_WINDOW = 20
_DRIFT_LAG = 4

#: W has stopped moving when it differs from the model 200 sweeps back by no
#: more than this times its difference from the model 50 sweeps back -- i.e.
#: by no more than the chain's own sample-to-sample noise.
_DRIFT = 1.15

#: Consecutive checks that must pass, so one quiet stretch cannot end the run.
_PATIENCE = 2

#: Checkpoints averaged into the W and H returned: 200 sweeps.
_AVERAGE = 5

#: No check before this many sweeps: every fit runs at least this long.
_MIN_SWEEPS = 1500

# Measured on HRD: 27 chains of 2000 sweeps (genus seed 42, ASV seed 42, genus
# seed 7; k=2..10), W saved every 50, each stop compared with the same chain's
# sweep-2000 model, averaged the same way, in units of the chain's own
# stationary noise (how far its tail sits from its end):
#
#   first check   mean stop   worst k   chains > 2x the noise
#        400          887       6.4x          2
#       1000         1196       2.0x          0
#       1500         1585       1.1x          0     <- this
#
# Two things a check from 400 missed. The LL can be flat while W still creeps
# (genus k=9: flat at 400, W moving until ~1000) -- hence the W drift test. And
# a chain can sit in one state for hundreds of sweeps, then jump to a better
# one (ASV k=9: stable 700-1100, jumped at ~1200, LL +1.2% of its total gain):
# no test on the past can see that coming, so the first check is put late.
# Fits beyond 2000 sweeps were not measured. Across all 27 the consensus was
# unchanged whichever rule stopped them.
#
# With checks from 1500, the LL test passes at rel_tol 5e-3: at 2e-3 it failed
# 22% of checks on chains that had long been stationary (73% at genus k=2,
# whose total gain is small, so its noise looks large), and two of 27 would
# have reached max_iter and been flagged without having moved. Averaging 5
# checkpoints halves the noise in W (0.65% -> 0.35% of samples change their top
# LC between draws 250 sweeps apart) at no extra sweeps.

#: Pins the JVM's number format: ``LL/token`` is printed with
#: ``NumberFormat.getInstance()``, which follows the default FORMAT locale.
_JAVA_LOCALE = ("-Duser.language=en -Duser.country=US "
                "-Duser.language.format=en -Duser.country.format=US")

_LL = re.compile(r"^<(\d+)> LL/token: (\S+)")


# --- the corpus -------------------------------------------------------------

def _corpus_dir(base_directory: str) -> str:
    return os.path.join(base_directory, "intermediate", "mallet")


def _read_meta(base_directory: str) -> dict:
    path = os.path.join(_corpus_dir(base_directory), "corpus.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def write_corpus(base_directory: str, X: np.ndarray, digest: str) -> str:
    """
    ``intermediate/mallet/corpus.txt`` -- the feature table as a MALLET
    document file. Skipped when the one there was written from the same
    ``features.csv`` (``digest`` is its SHA-256).

    One line per sample, in row order, each feature repeated ``count`` times.
    The token for column j is ``f<j>``: MALLET's default tokenizer drops or
    splits real feature names (129 of HRD's 953 genera, e.g. ``67-14`` and
    ``SAR324_clade(Marine_group_B)``), and a name may hold whitespace. The
    document name is the row number, since a sample id may hold the spaces or
    commas MALLET's line format splits on.
    """
    d = _corpus_dir(base_directory)
    txt = os.path.join(d, "corpus.txt")
    meta = _read_meta(base_directory)
    if os.path.exists(txt) and meta.get("features_sha256") == digest:
        return txt
    os.makedirs(d, exist_ok=True)
    X = np.asarray(X)
    toks = [f"f{j} " for j in range(X.shape[1])]
    with open(txt, "w") as f:
        for i, row in enumerate(X):
            f.write(f"{i}\tX\t"
                    + "".join(toks[j] * int(row[j]) for j in np.flatnonzero(row)) + "\n")
    with open(os.path.join(d, "corpus.json"), "w") as f:
        json.dump({"features_sha256": digest, "n_docs": int(X.shape[0]),
                   "n_features": int(X.shape[1]), "n_tokens": int(X.sum()),
                   "token": "f<j> is column j of features.csv"}, f, indent=2)
    return txt


def _corpus(base_directory: str, X: np.ndarray, launcher: str, *, verbose: bool) -> str:
    """``intermediate/mallet/corpus.mallet``: ``corpus.txt`` imported once and
    reused by every k and every later sweep, until ``features.csv`` or the
    launcher changes."""
    with open(os.path.join(base_directory, "intermediate", "features.csv"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    txt = write_corpus(base_directory, X, digest)
    out = os.path.join(_corpus_dir(base_directory), "corpus.mallet")
    meta = _read_meta(base_directory)
    done = {"features_sha256": digest, "launcher": launcher}
    if os.path.exists(out) and meta.get("imported") == done:
        return out
    r = subprocess.run(
        [launcher, "import-file", "--input", txt, "--output", out,
         "--keep-sequence", "--preserve-case", "--token-regex", r"\S+"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", env=_env())
    if r.returncode or not os.path.exists(out):
        raise RuntimeError(f"MALLET import-file failed:\n{_explain(r.stdout)}")
    with open(os.path.join(_corpus_dir(base_directory), "corpus.json"), "w") as f:
        json.dump({**meta, "imported": done}, f, indent=2)
    if verbose:
        print(f"[sweep] MALLET corpus: {meta.get('n_tokens', 0):,} tokens -> {out}")
    return out


# --- the launcher and its process -------------------------------------------

def _launcher(mallet) -> str:
    """The ``bin/mallet`` script, from it or from MALLET's own folder."""
    path = os.path.abspath(os.path.expanduser(os.fspath(mallet)))
    if os.path.isdir(path):
        path = os.path.join(path, "bin", "mallet.bat" if os.name == "nt" else "mallet")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"mallet={os.fspath(mallet)!r}: no MALLET launcher there. Pass the path "
            "to bin/mallet inside a MALLET download (https://mimno.github.io/Mallet/).")
    if os.name != "nt" and not os.access(path, os.X_OK):
        raise PermissionError(f"mallet={path!r} is not executable: chmod +x {path}")
    return path


def _env() -> dict:
    env = dict(os.environ)
    env["JAVA_TOOL_OPTIONS"] = f"{env.get('JAVA_TOOL_OPTIONS', '')} {_JAVA_LOCALE}".strip()
    return env


def _explain(output: str) -> str:
    """The part of a failed MALLET run worth reading, plus what usually fixes it."""
    tail = "\n".join(output.strip().splitlines()[-15:])
    if any(m in output for m in ("command not found", "No Java runtime",
                                 "Unable to locate a Java Runtime")):
        hint = "MALLET needs Java on PATH (any JRE/JDK 8 or newer)."
    elif "Could not find or load main class" in output:
        hint = ("MALLET is not built there: a source checkout has no class/ or "
                "lib/. Download the release instead.")
    elif "OutOfMemoryError" in output:
        hint = ("the JVM ran out of heap. MALLET's launcher reads MALLET_MEMORY "
                "(default 1g): set os.environ['MALLET_MEMORY'] = '4g' and rerun.")
    else:
        hint = ""
    return f"{tail}\n\n{hint}".rstrip()


def _start(argv):
    kw = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
              encoding="utf-8", errors="replace", env=_env())
    # Its own process group: bin/mallet is a shell script that runs java as a
    # CHILD, so terminating the script alone leaves the JVM running.
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(argv, **kw)


def _stop(proc) -> None:
    """Kill the launcher and the JVM under it, and reap them."""
    if proc.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if os.name != "nt":
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    if proc.stdout:
        proc.stdout.close()


# --- reading the chain ------------------------------------------------------

def _ll_value(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        pass
    try:                       # a comma decimal or U+2212 minus got through
        return float(text.replace("−", "-").replace(",", "."))
    except ValueError:
        raise ValueError(f"cannot read MALLET's LL/token value {text!r}") from None


def _ll_ratio(ll: list[float], window: int = _WINDOW) -> float:
    """``LL/token`` gained over the last ``window`` points, per this run's total
    gain so far -- scale-free, as ``rel_tol`` is for gensim. The gain is the
    least-squares slope times the window, so one noisy point cannot fake it."""
    total = ll[-1] - ll[0]
    if len(ll) < window or not total > 0:
        return float("inf")
    slope = np.polyfit(np.arange(window), np.asarray(ll[-window:]), 1)[0]
    return float(abs(slope) * (window - 1) / total)


def _rebuild(state: str, X: np.ndarray, k: int, *, check: bool):
    """
    ``(W, H)`` from a state file, smoothed exactly as MALLET's own outputs::

        W[d, t] = (n_dt + alpha_t) / (n_d + sum(alpha))   == --output-doc-topics
        H[t, j] = (n_tj + beta)    / (n_t + V * beta)     == --topic-word-weights-file

    with ``alpha`` and ``beta`` read from the state's header, since
    optimisation moves them. With ``check``, also confirms that the state's own
    doc x feature counts ARE the input table, which certifies the document
    order, the token mapping and that nothing was dropped on import.
    """
    with gzip.open(state, "rt") as f:
        f.readline()
        alpha = np.array(f.readline().split(":", 1)[1].split(), dtype=float)
        beta = float(f.readline().split(":", 1)[1])
    N, V = X.shape
    if alpha.size != k:
        raise AssertionError(f"state has {alpha.size} topics, expected {k}")
    ndt = np.zeros(N * k, dtype=np.int64)
    ntj = np.zeros(k * V, dtype=np.int64)
    back = np.zeros(N * V, dtype=np.int64) if check else None
    # #doc source pos typeindex type topic; chunked so memory stays flat on a
    # corpus far larger than HRD's 6.5M tokens.
    for chunk in pd.read_csv(state, sep=" ", header=None, skiprows=3,
                             usecols=[0, 4, 5], names=["doc", "type", "topic"],
                             dtype={"doc": np.int64, "type": "category",
                                    "topic": np.int64},
                             keep_default_na=False, chunksize=2_000_000,
                             compression="gzip"):     # named state.gz.<t>: not inferable
        cats = chunk["type"].cat.categories
        j_of = np.array([int(c[1:]) if c[:1] == "f" and c[1:].isdigit() else -1
                         for c in cats], dtype=np.int64)
        j = j_of[chunk["type"].cat.codes.to_numpy()]
        doc, top = chunk["doc"].to_numpy(), chunk["topic"].to_numpy()
        if (j < 0).any() or (j >= V).any() or (doc >= N).any():
            raise AssertionError("the MALLET state holds tokens or documents that "
                                 "are not in features.csv")
        ndt += np.bincount(doc * k + top, minlength=N * k)
        ntj += np.bincount(top * V + j, minlength=k * V)
        if check:
            back += np.bincount(doc * V + j, minlength=N * V)
    if check and not np.array_equal(back.reshape(N, V), np.asarray(X, dtype=np.int64)):
        raise AssertionError(
            "the MALLET state does not reproduce features.csv: documents were "
            "reordered or tokens were lost on import")
    ndt, ntj = ndt.reshape(N, k), ntj.reshape(k, V)
    W = (ndt + alpha) / (ndt.sum(1, keepdims=True) + alpha.sum())
    H = (ntj + beta) / (ntj.sum(1, keepdims=True) + V * beta)
    return W, H


def _order(W: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """The column order of ``W`` that best matches ``ref``'s LCs. One chain
    rarely relabels after burn-in, but averaging must not depend on it."""
    from scipy.optimize import linear_sum_assignment

    r, c = linear_sum_assignment(np.abs(W[:, :, None] - ref[:, None, :]).sum(0))
    order = np.empty(W.shape[1], dtype=int)
    order[c] = r
    return order


def _align(W: np.ndarray, H: np.ndarray, ref: np.ndarray):
    o = _order(W, ref)
    return W[:, o], H[o]


def _tv(Wa: np.ndarray, Wb: np.ndarray) -> float:
    """Mean total-variation distance between two samples' W, LCs matched."""
    return float(0.5 * np.abs(Wb[:, _order(Wb, Wa)] - Wa).sum(1).mean())


def _drift(snaps: dict) -> float:
    """``TV(W_t, W_t-200) / TV(W_t, W_t-50)``: ~1 once W only jitters, larger
    while it is still moving somewhere."""
    ts = sorted(snaps)
    if len(ts) <= _DRIFT_LAG:
        return float("inf")
    now = snaps[ts[-1]][0]
    near, far = _tv(now, snaps[ts[-2]][0]), _tv(now, snaps[ts[-1 - _DRIFT_LAG]][0])
    if near == 0:
        return 1.0 if far == 0 else float("inf")
    return far / near


# --- one fit ----------------------------------------------------------------

_terminating = False


def _exit_on_sigterm() -> None:
    """
    For a pool worker: make SIGTERM kill this worker's MALLET JVM, then exit.

    The default SIGTERM ends the process without running ``finally``, and the
    JVM -- in a session of its own, see :func:`_start` -- samples on to
    ``max_iter``. Raised as SystemExit it unwinds through ``_fit_mallet``'s
    cleanup instead; but ProcessPoolExecutor catches a task's SystemExit as a
    result and keeps the worker waiting for more work, so the cleanup then
    exits the process itself.
    """
    def handler(*_):
        global _terminating
        _terminating = True
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, handler)


def _fit_mallet(k: int, seed: int, params: dict, X: np.ndarray):
    """
    One MALLET fit at ``k``, stopped once the model has settled.

    At every checkpoint from ``floor`` on, two things must hold, for
    ``_PATIENCE`` checks in a row: ``LL/token`` gained less than ``rel_tol`` of
    the run's total over the last 200 sweeps, and W has stopped drifting
    (:func:`_drift` at most ``_DRIFT``). ``floor`` is ``_MIN_SWEEPS``, or later
    if ``optimize_burn_in`` is set that high: alpha and beta are frozen until
    then, so the likelihood can sit flat and climb again once optimisation
    starts, and the window must be clear of it.

    Returns the average of the last ``_AVERAGE`` checkpoints, at the stop or
    at ``max_iter``, whichever comes first.
    """
    cap = int(params["max_iter"])
    every = min(_CHECKPOINT, cap)
    burn = int(params["optimize_burn_in"]) if int(params["optimize_interval"]) else 0
    floor = max(burn + 10 * _WINDOW, _MIN_SWEEPS)
    # The checks and the average need the last 200 sweeps; earlier
    # checkpoints are deleted unread, keeping only the newest in case the run
    # ends (a small max_iter) before any of them is needed.
    first = floor - every * _DRIFT_LAG
    tmp = tempfile.mkdtemp(prefix=f"stripesankey-mallet-k{k}-")
    state = os.path.join(tmp, "state.gz")
    argv = [params["mallet"], "train-topics", "--input", params["corpus"],
            "--num-topics", str(k), "--num-iterations", str(cap),
            "--random-seed", str(seed), "--num-threads", "1",
            "--alpha", str(params["alpha"]), "--beta", str(params["beta"]),
            "--optimize-interval", str(params["optimize_interval"]),
            "--optimize-burn-in", str(params["optimize_burn_in"]),
            "--show-topics-interval", "0",
            "--output-state", state, "--output-state-interval", str(every)]
    its, ll, snaps = [], [], {}
    ratio = drift = float("inf")
    passed, stop_at, pending = 0, None, None
    log_path = os.path.join(params["logdir"], f"mallet_{k}.log")

    def take(t):
        """Rebuild checkpoint t into the window of snapshots, then delete it."""
        f = f"{state}.{t}"
        snaps[t] = _rebuild(f, X, k, check=not snaps)
        os.remove(f)
        for old in sorted(snaps)[:-_AVERAGE]:
            del snaps[old]

    try:
        proc = _start(argv)
        try:
            with open(log_path, "w") as log:
                for line in proc.stdout:
                    log.write(line)
                    m = _LL.match(line)
                    if not m:
                        continue
                    t = int(m.group(1))
                    its.append(t)
                    ll.append(_ll_value(m.group(2)))
                    if t % every:
                        continue
                    # state.<t> is complete: it was written before sweep t.
                    if pending is not None:
                        with contextlib.suppress(FileNotFoundError):
                            os.remove(f"{state}.{pending}")
                        pending = None
                    if t < first:
                        pending = t
                        continue
                    take(t)
                    if t < floor:
                        continue
                    ratio, drift = _ll_ratio(ll), _drift(snaps)
                    passed = passed + 1 if (ratio < params["rel_tol"]
                                            and drift <= _DRIFT) else 0
                    if passed >= _PATIENCE:
                        stop_at = t
                        break
            if stop_at is None and proc.wait() != 0:
                with open(log_path) as f:
                    raise RuntimeError(f"MALLET train-topics failed at k={k}:\n"
                                       f"{_explain(f.read())}")
        finally:
            _stop(proc)
        if stop_at is None:
            # Ran to the cap: take whatever is still on disk -- the newest
            # unread checkpoint, and one whose LL line never came (a cap that
            # is not a multiple of 10).
            for t in sorted(int(f.rsplit(".", 1)[1]) for f in os.listdir(tmp)
                            if f.startswith("state.gz.")):
                take(t)
            if not snaps:
                raise RuntimeError(f"MALLET wrote no state at k={k}; see {log_path}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if _terminating:
            os._exit(143)

    last = max(snaps)
    ref = snaps[last][0]
    pairs = [_align(W, H, ref) for W, H in snaps.values()]
    W = np.mean([w for w, _ in pairs], axis=0)
    H = np.mean([h for _, h in pairs], axis=0)
    at = [v for t, v in zip(its, ll) if t <= last]
    finite = lambda x: None if not np.isfinite(x) else float(x)  # noqa: E731
    diag = {
        "converged": stop_at is not None,
        "n_iter": last - 1,
        "max_iter": cap,
        "ll_ratio": finite(ratio),
        "w_drift": finite(drift),
        "averaged": len(snaps),
        "ll_final": at[-1] if at else None,
        "perplexity": float(np.exp(-at[-1])) if at else None,
        "ll_series": dict(zip(its, ll)),
    }
    return W, H, diag
