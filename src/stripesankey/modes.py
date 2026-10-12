"""
Multi-modality: one column per RUN instead of one column per K.

The rest of the workflow varies K and keeps one run per K. This module varies
the *run* and keeps K fixed -- the third of the three problems pong, CLUMPP,
CLUMPAK and Clumppling exist to solve, and the one StripeSankey had not
touched: replicate runs of the same model at the same K do not all land in the
same place. Some converge to one arrangement of ancestry components, some to
another. pong calls those arrangements **modes**; it reports the major mode and
draws the rest as separate barplots.

Why label alignment is not needed here
--------------------------------------
Every one of those tools starts by *aligning* runs: match run a's components to
run b's (CLUMPP/pong solve a Munkres assignment on component similarity,
Clumppling an optimal-transport variant), then compare the aligned matrices.
Alignment is needed because ``H`` is only defined up to a permutation of its
columns, so ``H_a`` and ``H_b`` cannot be compared entry-by-entry.

Co-membership removes the permutation instead of solving for it. For a
row-normalised usage matrix ``P`` (N x K),

    B = P @ P.T          B[i,j] = P(sample i and sample j draw the same MC)

is **invariant** to any permutation of P's columns: ``(PΠ)(PΠ)ᵀ = P Π Πᵀ Pᵀ =
P Pᵀ``. Two runs in the same mode have the same B whatever order their
components came out in, and two runs in different modes do not. So run-to-run
similarity is just the correlation between their B matrices --

    s(a, b) = corr over i != j of ( B_a[i,j], B_b[i,j] )                   (1)

-- no assignment problem, no Munkres, and nothing that breaks when the two runs
have different K. It is also the *same* representation
:mod:`~stripesankey.mr_consensus` already averages across K: ``Q_k = (B_k -
e_k)/(1 - e_k)`` is an affine map of ``B_k``, and Pearson correlation is
invariant to affine maps, so (1) is chance-corrected for free and
``consensus_affinity`` can be handed ``{run_id: H}`` exactly as it is handed
``{k: H_k}``. The ensemble does not care what its members vary.

On pong's own bundled 1000 Genomes Phase 3 example (2426 individuals, ADMIXTURE,
8 replicates at each of K=2..8), (1) thresholded at 0.97 reproduces pong's mode
decomposition exactly at every K -- including the 4/2/2 split at K=7 and the
5/2/1 at K=6 -- without ever aligning a component. See
``scripts/proto_modestripe.py``, which prints that comparison.

What defines a mode
-------------------
0.97 is pong's number, and inheriting it sits badly next to
:mod:`~stripesankey.mr_consensus`, whose whole point is that ``resolution=0``
needs no such number. ``mode_rule`` offers three answers, all of which reproduce
pong at every K of that example:

``"partition"`` (default)
    Two runs share a mode when their **dominant-component partitions are
    identical** -- :func:`partition_agreement` exactly 1. Parameter-free in the
    strong sense: 1.0 is an exact identity, not a tuned cut, so "same mode" is a
    real equivalence relation and there is no chaining ambiguity. It is also the
    criterion the figure draws, since a node is the set of samples whose argmax
    is that component: ARI 1 means *every ribbon between these two columns runs
    flat*. Definition and picture are one object.
``"similarity"``
    pong's rule on statistic (1). Uses the mixture proportions rather than just
    the argmax and tolerates a few samples disagreeing -- at the price of 0.97.
``"consensus"``
    Leiden on :func:`consensus_run_affinity`, i.e. this package's own
    signed-affinity machinery moved to the run axis. Grades runs *relative to
    the ensemble*, so it still finds structure when nothing is near-identical.

Which to use is an empirical question, and
:meth:`ModeAnalysis.separation` is how to settle it: it reports the worst
agreement inside a mode against the best between two. On the 1kg_p3 example
every rule separates with 0.10--0.33 of empty space, so the modes there are not
an artefact of where the cut falls -- which is why three different definitions
agree. On a deliberately noisy synthetic ensemble (two true modes, per-run
jitter large enough that no two runs match exactly) ``"partition"`` degenerates
to R singleton modes and says so with a warning, while ``"similarity"`` and
``"consensus"`` both recover the truth with a gap of 0.98. Exactness is the
default's strength on a clean ensemble and its failure mode on a dirty one.

Cost. ``B`` is never built. Writing ``G_ab = P_aᵀ P_b`` (K x K) and
``d_a = rowwise sum P_a**2``,

    <B_a, B_b>_F = ||G_ab||_F**2          sum_ij B_a  = ||1ᵀP_a||**2
    sum_i B_a[i,i] B_b[i,i] = d_a . d_b

so every term of (1) is O(N K**2), not O(N**2). The 28 pairs at K=7 above take
well under a second on 2426 samples.

What you get that pong does not
-------------------------------
pong answers "how many modes, and which runs are in each". That is
:func:`run_similarity` + :func:`detect_modes` here. The rest of the module
answers the question a reader asks next -- *which samples* are the modes
arguing about:

* :meth:`ModeAnalysis.stripe` draws one StripeSankey column **per run**
  (``by="run"``), ordered so the modes are contiguous. Ribbons are sample flows
  between adjacent runs; colour is the consensus cluster computed over *all*
  runs. Runs inside a mode line up flat; the scramble at a mode boundary is the
  multi-modality, drawn at sample resolution. The crossing-minimising layout
  that already un-crosses ribbons across K un-crosses them across runs too, so
  label switching between replicates is handled by the same mechanism that
  handles it between K -- as a layout problem, not a matching problem.
* ``by="mode"`` collapses each mode to a single column
  (:meth:`ModeAnalysis.mode_usage`), so nothing on the page is a replicate and
  every ribbon is a mode-to-mode disagreement. That is pong's per-mode barplot
  summary redrawn as one connected figure -- and the form to put in a paper,
  since it is M columns wide instead of R.
* Columns are ordered by :meth:`ModeAnalysis.mode_order`, which seriates on
  :func:`mode_similarity` so the modes that agree most sit side by side. Mode
  *ids* stay in pong's descending-size order; ordering is a display concern and
  a bad one is actively misleading -- at K=7 below, size order happens to put
  the two least similar modes (0.734) next to each other, the worst of the
  three arrangements.
* :meth:`ModeAnalysis.instability` scores each sample by how much the modes
  disagree about it, so the handful of samples responsible for a mode split
  can be named rather than just counted.
* :meth:`ModeAnalysis.mode_agreement` gives the ARI between the consensus
  partitions each mode implies -- "the modes differ, but on 3% of the
  partition" is a very different result from "they differ on half of it".
"""
import itertools
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
from scipy.spatial.distance import squareform

from .mr_consensus import (
    _row_normalise,
    cluster_from_affinity,
    coarse_affinity,
    coarse_linkage,
    coarse_sizes,
    coherent_cluster_palette,
    consensus_affinity,
    oklch_to_hex,
    renumber_by_tree_position,
)

__all__ = [
    "load_pong_filemap",
    "run_similarity",
    "detect_modes",
    "partition_agreement",
    "consensus_run_affinity",
    "widest_gap",
    "threshold_scan",
    "mode_similarity",
    "mode_analysis",
    "consensus_from_runs",
    "metadata_palette",
    "modestripe",
    "ModeAnalysis",
]


# --------------------------------------------------------------------------
# input handling
# --------------------------------------------------------------------------
def _as_matrix(H):
    """A run's usage table -> (N, K) ndarray + its sample index, if it has one."""
    if isinstance(H, pd.DataFrame):
        return H.to_numpy(dtype=np.float64), list(H.index.map(str))
    return np.asarray(H, dtype=np.float64), None


def _align_runs(runs, samples=None):
    """
    ``{run_id: (N, K) usage}`` -> ``(ids, P_list, samples)``, all on one index.

    Every run is row-normalised to a distribution. DataFrames are reindexed onto
    a common sample order (their own, or ``samples``); bare arrays are taken to
    be in that order already and are only checked for length.
    """
    ids = list(runs)
    if not ids:
        raise ValueError("no runs given")

    if samples is None:
        for rid in ids:
            if isinstance(runs[rid], pd.DataFrame):
                samples = list(runs[rid].index.map(str))
                break
    P_list = []
    for rid in ids:
        H = runs[rid]
        if isinstance(H, pd.DataFrame):
            idx = H.index.map(str)
            if samples is None:
                samples = list(idx)
            missing = set(samples) - set(idx)
            if missing:
                raise ValueError(f"run {rid!r} is missing {len(missing)} sample(s), "
                                 f"e.g. {sorted(missing)[:3]}")
            H = H.loc[list(samples)]
        arr, _ = _as_matrix(H)
        if samples is not None and arr.shape[0] != len(samples):
            raise ValueError(f"run {rid!r} has {arr.shape[0]} rows, "
                             f"expected {len(samples)}")
        P_list.append(_row_normalise(arr, rid))

    if samples is None:
        samples = [str(i) for i in range(P_list[0].shape[0])]
    return ids, P_list, list(samples)


def load_pong_filemap(filemap, k=None, root=None):
    """
    Read a pong filemap into ``{K: {run_id: DataFrame}}`` (or one K's dict).

    A pong filemap is three tab-separated columns -- run id, K, path to the .Q
    matrix -- with paths relative to the filemap's own directory. This is the
    format pong, CLUMPAK and Clumppling all consume, so anything already set up
    for those tools can be read straight in.

    Args:
        filemap: path to the ``pong_filemap`` file.
        k: return only this K's runs, as ``{run_id: DataFrame}``. ``None``
            (default) returns every K as ``{K: {run_id: DataFrame}}``.
        root: directory the .Q paths are relative to; defaults to the filemap's
            own directory, which is what pong itself assumes.

    Returns:
        Nested dict of sample x MC DataFrames. Rows are named ``i0, i1, ...``
        unless you reindex them -- .Q files carry no sample ids.
    """
    import os

    filemap = os.fspath(filemap)
    root = root or os.path.dirname(os.path.abspath(filemap))
    out = {}
    with open(filemap) as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 3:
                continue
            rid, kk, rel = parts[0], int(parts[1]), parts[2]
            if k is not None and kk != k:
                continue
            arr = np.loadtxt(os.path.join(root, rel))
            arr = np.atleast_2d(arr)
            df = pd.DataFrame(arr,
                              index=[f"i{i}" for i in range(arr.shape[0])],
                              columns=[f"MC{t}" for t in range(arr.shape[1])])
            out.setdefault(kk, {})[rid] = df
    if not out:
        raise ValueError(f"{filemap}: no runs read"
                         + (f" at K={k}" if k is not None else ""))
    return out[k] if k is not None else out


# --------------------------------------------------------------------------
# (1) alignment-free run similarity
# --------------------------------------------------------------------------
def _moments(P):
    """The O(N K**2) sufficient statistics of ``B = P Pᵀ``.

    ``d`` is B's diagonal, ``s_off`` the sum of its off-diagonal entries and
    ``ip_self`` the sum of their squares -- everything (1) needs from a run on
    its own, so the pair loop only has to add the one cross term.
    """
    d = np.einsum("ij,ij->i", P, P)            # diag(B)
    G = P.T @ P                                # K x K
    s_off = float(P.sum(0) @ P.sum(0)) - float(d.sum())
    ip_self = float((G * G).sum()) - float(d @ d)
    return d, s_off, ip_self


def run_similarity(runs, samples=None):
    """
    Alignment-free run-to-run similarity: eq. (1) of this module.

    ``+1`` = the two runs induce the same soft partition of the samples,
    whatever order their components came out in. ``0`` = unrelated. Because
    Pearson correlation is invariant to the affine map ``B -> (B - e)/(1 - e)``,
    this is the correlation of the *chance-corrected* co-memberships
    :func:`~stripesankey.mr_consensus.consensus_affinity` averages, not of the
    raw ones.

    Nothing here requires the runs to share a K: ``B`` is N x N for any K, so a
    K=6 run and a K=7 run are directly comparable. Mixing K is unusual (the
    matched question is normally asked at fixed K) but it is not an error.

    Args:
        runs: ``{run_id: (N, K) usage}`` -- DataFrames (index = sample id) or
            arrays already on a common sample order. Row-normalised internally.
        samples: optional common sample order to reindex DataFrames onto.

    Returns:
        (R, R) DataFrame, symmetric, 1.0 on the diagonal, indexed by run id in
        the order ``runs`` was given.
    """
    ids, P_list, _ = _align_runs(runs, samples)
    R = len(ids)
    N = P_list[0].shape[0]
    if N < 2:
        raise ValueError("run similarity needs at least 2 samples")
    M = N * (N - 1)

    mom = [_moments(P) for P in P_list]
    mean = [s_off / M for _d, s_off, _ip in mom]
    var = [max(ip / M - mu * mu, 0.0) for (_d, _s, ip), mu in zip(mom, mean)]

    S = np.eye(R)
    for a in range(R):
        for b in range(a + 1, R):
            G = P_list[a].T @ P_list[b]
            ip = float((G * G).sum()) - float(mom[a][0] @ mom[b][0])
            cov = ip / M - mean[a] * mean[b]
            den = np.sqrt(var[a] * var[b])
            S[a, b] = S[b, a] = 0.0 if den == 0 else float(np.clip(cov / den, -1.0, 1.0))
    return pd.DataFrame(S, index=ids, columns=ids)


# --------------------------------------------------------------------------
# (2) modes
# --------------------------------------------------------------------------
def partition_agreement(runs, samples=None):
    """
    (R, R) adjusted Rand index between the runs' **dominant-component
    partitions** -- the statistic behind ``mode_rule="partition"``.

    Assign every sample to its largest component (``argmax`` of its usage row)
    and you have a hard partition into at most K groups, defined only up to a
    relabelling of the groups -- exactly the ambiguity the ARI is built to
    ignore. Two runs score **exactly 1.0** when every sample lands in the same
    group in both, whatever integers those groups were given.

    Why this is the statistic worth thresholding at 1. The dominant component
    is what the StripeSankey draws: a node is the set of samples whose argmax is
    that component, and a ribbon that runs flat between two columns is a sample
    whose argmax did not change. So ``ARI == 1`` says precisely *"every ribbon
    between these two columns runs flat"* -- the mode definition and the picture
    are the same object, rather than two statistics that happen to agree.

    And ``1.0`` is not a tuned cut-off but an exact identity, which makes "same
    mode" a genuine equivalence relation (reflexive, symmetric, **transitive**),
    so unlike a similarity cut there is no chaining ambiguity to resolve. On
    pong's 1kg_p3 example the cut is not close: at every K the pairs sit either
    at exactly 1.0 or below 0.90, with 0.10--0.33 of empty space between.

    Args:
        runs: ``{run_id: (N, K) usage}``; K may differ between runs.
        samples: common sample order to reindex DataFrames onto.

    Returns:
        (R, R) DataFrame, symmetric, 1.0 on the diagonal.
    """
    from sklearn.metrics import adjusted_rand_score

    ids, P_list, _ = _align_runs(runs, samples)
    hard = [P.argmax(axis=1) for P in P_list]
    R = len(ids)
    A = np.eye(R)
    for a in range(R):
        for b in range(a + 1, R):
            A[a, b] = A[b, a] = float(adjusted_rand_score(hard[a], hard[b]))
    return pd.DataFrame(A, index=ids, columns=ids)


def consensus_run_affinity(S, min_spread=1e-6):
    """
    Chance-correct a run similarity against its own mean -> a **signed** affinity.

    The direct port of :func:`~stripesankey.mr_consensus.consensus_affinity`'s
    idea to the run axis, and the reason it needs its own function: the null is
    different. For samples, "chance" is *every sample has the average profile*,
    which gives co-membership ``e_k`` somewhere below 1. For runs the matching
    null is *every run is the average run*, and that gives similarity exactly
    **1** -- two fits of the same model to the same data have no reason to
    differ. So the correction is anchored at the other end::

        Q_run[a,b] = (s[a,b] - s_bar) / (1 - s_bar)

    with ``s_bar`` the mean off-diagonal similarity. Same
    ``(observed - expected) / (max - expected)`` form, same signed output:
    positive means "more alike than the typical pair of runs in this ensemble",
    negative means less. That makes
    :func:`~stripesankey.mr_consensus.cluster_from_affinity` meaningful on
    runs, with no cluster count and no 0.97.

    What it does **not** inherit is ``resolution=0``'s privileged status. For
    samples, zero reads "together more often than chance" against a real null.
    Here the reference is the ensemble's own mean, so zero reads "more alike
    than average", which is a *relative* claim: on 1kg_p3 at K=7 it merges two
    modes whose similarity (0.903) merely beats the ensemble mean (0.873),
    while pong asks for near-identity. ``resolution`` around 0.25 -- "at least a
    quarter of the way from the typical pair to an exact match" -- reproduces
    pong at every K there. Use this rule when nothing in the ensemble is
    near-identical and an absolute cut would return R singletons; use
    ``mode_rule="partition"`` when it is clean.

    Args:
        S: (R, R) similarity, e.g. from :func:`run_similarity`.
        min_spread: if ``1 - s_bar`` falls below this the ensemble is unimodal
            to numerical precision and the rescaling would amplify float noise
            into imaginary modes, so ``None`` is returned. The default sits well
            above the ~1e-8 float floor of these correlations and far below any
            real mode gap (0.1 upward on this data).

    Returns:
        ``(Q_run, s_bar)`` -- (R, R) signed ndarray with a zero diagonal, or
        ``(None, s_bar)`` when the ensemble is degenerate.
    """
    A = np.asarray(S, dtype=np.float64)
    n = A.shape[0]
    if n < 2:
        return None, 1.0
    iu = np.triu_indices(n, k=1)
    s_bar = float(A[iu].mean())
    if 1.0 - s_bar < min_spread:
        return None, s_bar
    Q = (A - s_bar) / (1.0 - s_bar)
    Q = (Q + Q.T) / 2.0
    np.fill_diagonal(Q, 0.0)
    return Q, s_bar


def widest_gap(A, min_gap=0.05):
    """
    Where the observed agreements leave the most room for a cut.

    A clique rule's answer is **piecewise constant** in its threshold: only the
    values actually present in ``A`` can change the grouping, so every cut inside
    one empty interval gives the identical answer. Picking a threshold is
    therefore not picking a number, it is picking which of those intervals --
    which *plateau* -- to sit on (:func:`threshold_scan` lists them). This picks
    the widest one and returns its midpoint, so the cut sits as far as possible
    from any value that could move it.

    The parameter does not disappear, it moves somewhere far less sensitive.
    ``threshold=0.95`` asserts *where* the line is and breaks as soon as a
    dataset's agreements sit elsewhere; ``min_gap`` asserts only *how convincing*
    a separation has to be before it counts as one, and the answer then stops
    moving when the data shift and moves only when the structure genuinely
    weakens.

    Args:
        A: (R, R) agreement, e.g. :func:`partition_agreement`.
        min_gap: the widest interval must be at least this wide, or the runs are
            declared one mode. This is the guard against splitting on noise: a
            genuinely unimodal but noisy ensemble still has a widest gap, it is
            just a small one. The default sits above the within-mode jitter of a
            noisy ensemble (~0.01--0.03 in testing) and well below a real mode
            boundary (0.10--0.33 on the 1kg_p3 example).

    Returns:
        ``(threshold, gap)``. ``threshold`` is ``None`` when no interval clears
        ``min_gap``, i.e. there is nothing to split.
    """
    A = np.asarray(A, dtype=np.float64)
    n = A.shape[0]
    if n < 2:
        return None, 0.0
    iu = np.triu_indices(n, k=1)
    vals = np.unique(A[iu])[::-1]            # descending, deduplicated
    if vals.size < 2:
        return None, 0.0
    gaps = vals[:-1] - vals[1:]
    i = int(np.argmax(gaps))
    if float(gaps[i]) < min_gap:
        return None, float(gaps[i])
    return float((vals[i] + vals[i + 1]) / 2.0), float(gaps[i])


def threshold_scan(A):
    """
    Every distinct answer a clique rule can give, and the threshold range that
    produces it -- the table to read when "how far should I lower it?" is the
    question.

    Because the answer only changes at a value present in ``A``, this is the
    complete story: a handful of rows, each a plateau. A wide plateau means the
    grouping is robust and the exact threshold is irrelevant inside it; a table
    of narrow plateaus means the ensemble has no clean mode structure and any
    single number would be reporting the cut, not the data.

    Args:
        A: (R, R) agreement, e.g. :func:`partition_agreement`.

    Returns:
        DataFrame, finest grouping first: ``lo``/``hi`` bound the plateau as the
        half-open interval ``lo < threshold <= hi``, ``width`` is ``hi - lo``
        (how much room that answer has), plus ``n_modes`` and ``sizes``. The
        bottom row has ``lo = NaN``: every run merges for any threshold at or
        below it, so it extends downward without bound.
    """
    A = np.asarray(A, dtype=np.float64)
    if A.shape[0] < 2:
        return pd.DataFrame(columns=["lo", "hi", "width", "n_modes", "sizes"])
    frame = pd.DataFrame(A)
    iu = np.triu_indices(A.shape[0], k=1)
    vals = np.unique(A[iu])[::-1]                 # descending, deduplicated

    # The grouping only changes at an observed value: for lo < t <= hi exactly
    # the pairs at or above `hi` are joined. Evaluating at `hi` itself is exact,
    # no midpoint needed.
    spans = [(float(vals[i + 1]), float(vals[i])) for i in range(len(vals) - 1)]
    spans.append((np.nan, float(vals[-1])))

    rows = []
    for lo, hi in spans:
        m = detect_modes(frame, threshold=hi)
        sizes = tuple(sorted(m.value_counts().tolist(), reverse=True))
        if rows and rows[-1]["_sizes"] == sizes:
            rows[-1]["lo"] = lo                   # same answer: extend downward
            continue
        rows.append({"lo": lo, "hi": hi, "_sizes": sizes,
                     "n_modes": len(sizes),
                     "sizes": "/".join(map(str, sizes))})
    out = pd.DataFrame(rows)
    out["width"] = out["hi"] - out["lo"]
    return out[["lo", "hi", "width", "n_modes", "sizes"]]


def detect_modes(S, threshold=0.97, *, method="clique", min_spread=1e-6,
                 min_gap=0.05, random_state=0):
    """
    Group runs into modes.

    Args:
        S: (R, R) agreement between runs -- :func:`run_similarity` (soft
            co-membership correlation) or :func:`partition_agreement` (ARI of
            the dominant partitions).
        threshold: how much two runs must agree to share a mode. With
            ``method="clique"`` this is an absolute cut on ``S``: ``0.97`` is
            pong's, ``1.0`` with :func:`partition_agreement` means exact
            identity of the partitions. Pass ``"gap"`` to let the data place it
            -- :func:`widest_gap` puts the cut in the widest interval the
            observed agreements leave empty, which is the most defensible
            non-exact choice (see :func:`threshold_scan` for why the exact number
            rarely matters). With ``method="consensus"`` it is
            instead the Constant Potts resolution applied to
            :func:`consensus_run_affinity` -- 0 means "more alike than the
            average pair", ~0.25 reproduces pong on 1kg_p3.
        method: ``"clique"`` (default) -- maximal sets whose members ALL clear
            ``threshold``. This is pong's rule (v1.5 §2.2: disjoint cliques at
            similarity >= 0.97) with its Munkres-matched Jaccard replaced.
            Complete linkage cut at ``1 - threshold`` *is* that rule, since
            complete linkage's merge height is a group's **diameter**, so a
            group survives only if every pair inside it clears the cut; average
            linkage would let one very similar pair drag in a run that fails
            against the others. ``"consensus"`` -- Leiden on the chance-corrected
            signed affinity, i.e. the same machinery the sample clustering uses.
        min_spread: ``method="consensus"`` only; see
            :func:`consensus_run_affinity`. A degenerate (unimodal) ensemble
            returns a single mode rather than noise-driven splits.
        random_state: seeds Leiden for ``method="consensus"``.

    Returns:
        Series of mode ids indexed by run id, ``0`` = the **major mode** (most
        runs; ties broken by higher mean within-mode agreement).
    """
    ids = list(S.index)
    R = len(ids)
    if R == 1:
        return pd.Series([0], index=ids, name="mode")

    if isinstance(threshold, str):
        if threshold != "gap":
            raise ValueError(f"detect_modes(threshold={threshold!r}): expected a "
                             "number or 'gap'")
        if method != "clique":
            raise ValueError("threshold='gap' applies to method='clique'; the "
                             "consensus rule\'s threshold is a CPM resolution, "
                             "not a cut on S.")
        threshold, _gap = widest_gap(S, min_gap=min_gap)
        if threshold is None:                 # nothing clears min_gap -> one mode
            return pd.Series(np.zeros(R, dtype=int), index=ids, name="mode")

    if method == "consensus":
        Q, _s_bar = consensus_run_affinity(S, min_spread=min_spread)
        raw = (np.zeros(R, dtype=int) if Q is None else
               cluster_from_affinity(Q, resolution=threshold,
                                     noise_threshold=None,
                                     random_state=random_state))
    elif method == "clique":
        D = 1.0 - S.to_numpy()
        np.fill_diagonal(D, 0.0)
        D = np.clip((D + D.T) / 2.0, 0.0, None)
        Z = sch.linkage(squareform(D, checks=False), method="complete")
        # threshold=1.0 asks for exact equality; give fcluster a hair of room so
        # a merge at height 0 is still inside the cut.
        raw = sch.fcluster(Z, t=max(1.0 - threshold, 1e-9), criterion="distance")
    else:
        raise ValueError(f"detect_modes(method={method!r}): expected "
                         "'clique' or 'consensus'")

    def within(members):
        if len(members) < 2:
            return 1.0
        sub = S.to_numpy()[np.ix_(members, members)]
        iu = np.triu_indices(len(members), k=1)
        return float(sub[iu].mean())

    groups = [np.flatnonzero(raw == c) for c in np.unique(raw)]
    groups.sort(key=lambda g: (-len(g), -within(g)))
    out = {}
    for new_id, g in enumerate(groups):
        for i in g:
            out[ids[i]] = new_id
    return pd.Series([out[r] for r in ids], index=ids, name="mode")


def _representative(S, members, tol=1e-9):
    """The medoid run of a mode -- highest mean similarity to its own mode.

    Inside a mode every pair is >= ``threshold`` similar, so the medoid is
    close to a tie by construction: across the major modes of the 1kg_p3
    example the spread of medoid scores runs from 1e-12 (K=2) to 1e-5 (K=8).
    Ties within ``tol`` go to the first run in the given order, so the label is
    stable when the input dict is reordered. Where this picks a different run
    from pong's representative it is picking a different member of the *same*
    mode, separated by that much -- "the representative" is not a well-defined
    thing to disagree about, only the mode is.
    """
    if len(members) == 1:
        return members[0]
    sub = S.loc[members, members].to_numpy()
    mean = (sub.sum(axis=1) - np.diag(sub)) / (len(members) - 1)
    return members[int(np.flatnonzero(mean >= mean.max() - tol)[0])]


def mode_similarity(S, modes):
    """Block-average :func:`run_similarity` by mode -> an (M, M) table.

    Off-diagonal ``[a, b]`` is the mean run similarity between the two modes;
    the diagonal is the mean *within* a mode (1.0 for a singleton). It is the
    same statistic as ``S``, averaged over a block instead of read off a pair --
    the mode-level analogue of
    :func:`~stripesankey.mr_consensus.coarse_affinity`.
    """
    ids = sorted(int(m) for m in set(modes.tolist()))
    idx = {m: list(modes[modes == m].index) for m in ids}
    out = np.eye(len(ids))
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if i > j:
                continue
            if a == b:
                sub = S.loc[idx[a], idx[a]].to_numpy()
                n = len(idx[a])
                val = 1.0 if n < 2 else float(
                    (sub.sum() - np.trace(sub)) / (n * (n - 1)))
            else:
                val = float(S.loc[idx[a], idx[b]].to_numpy().mean())
            out[i, j] = out[j, i] = val
    return pd.DataFrame(out, index=ids, columns=ids)


def _seriate(M, anchor=0):
    """Order modes so that adjacent COLUMNS are the most similar modes.

    Mode ids are assigned by size (id 0 = pong's major mode), and drawing them
    in that order is an arbitrary choice that can be actively bad: at K=7 of the
    1kg_p3 example it happens to place the two *least* similar modes (0.734)
    side by side, which is the worst of the three arrangements. Every ribbon
    that crosses a mode boundary is a sample the two modes place differently, so
    ordering columns by similarity is the same "minimise crossings" objective
    the barycentre layout already serves inside a column.

    Maximises the total similarity of adjacent pairs (the standard seriation /
    open-TSP objective -- every boundary contributes crossings, so the sum is
    what matters), breaking ties on the worst single boundary and then on
    putting ``anchor`` (the major mode) as far left as possible. Exhaustive up
    to 7 modes, average-linkage leaf order beyond that.
    """
    ids = list(M.index)
    n = len(ids)
    if n <= 2:
        return ids
    A = M.to_numpy()
    a_pos = ids.index(anchor) if anchor in ids else 0
    if n <= 7:
        best, key = None, None
        for perm in itertools.permutations(range(n)):
            adj = [A[perm[i], perm[i + 1]] for i in range(n - 1)]
            k = (sum(adj), min(adj), -perm.index(a_pos))
            if key is None or k > key:
                key, best = k, perm
        return [ids[i] for i in best]

    D = 1.0 - A
    np.fill_diagonal(D, 0.0)
    D = np.clip((D + D.T) / 2.0, 0.0, None)
    Z = sch.linkage(squareform(D, checks=False), method="average")
    order = [ids[i] for i in sch.dendrogram(Z, no_plot=True)["leaves"]]
    if order.index(anchor) > (n - 1) / 2:     # keep the major mode on the left
        order = order[::-1]
    return order


def _align_to(P_ref, P):
    """Permute ``P``'s components onto ``P_ref``'s by a K x K assignment.

    Only ever used **inside** a mode, and that is the point. Finding modes needs
    no alignment (see this module's header); averaging the runs of one mode does,
    because an average over differently-ordered columns is meaningless. Inside a
    mode the assignment is trivially well posed -- the runs are the same
    partition by construction, at similarity >= ``threshold`` -- so the hard part
    of what CLUMPP/pong use Munkres for never arises here. Alignment is used
    where it is easy, not where it is load-bearing.

    Returns ``(P_permuted, cost)`` where ``cost`` is the mean absolute
    disagreement per entry after permuting; ~0 confirms the mode is real.
    """
    from scipy.optimize import linear_sum_assignment

    if P_ref.shape != P.shape:
        raise ValueError(f"cannot align {P.shape} onto {P_ref.shape}")
    _, col = linear_sum_assignment(-(P_ref.T @ P))    # maximise matched overlap
    out = P[:, col]
    return out, float(np.abs(out - P_ref).mean())


# --------------------------------------------------------------------------
# (3) the analysis object
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# colouring a figure by something other than the consensus clusters
# --------------------------------------------------------------------------
def metadata_palette(values, *, order=None, groups=None, group_order=None,
                     colors=None, title=None, hue0=25.0, arc=230.0,
                     light=(0.76, 0.46), chroma=(0.085, 0.175)):
    """
    A categorical metadata field -> everything a StripeSankey needs to be
    coloured by it instead of by the consensus clusters.

    The consensus colouring answers "which samples does this ensemble keep
    together"; this answers "where do the groups I already know about end up",
    which is the other half of reading a mode split -- on pong's 1000 Genomes
    example it is what turns "the modes disagree about 300 samples" into "the
    modes disagree about the admixed American populations".

    ``groups`` is what makes a many-category field readable. Colouring 26
    populations with 26 unrelated hues asks a reader to hold 26 arbitrary
    pairings in mind; nesting them in their 5 super-populations gives each
    super-population one hue and steps lightness within it, so a band is placed
    to a continent at a glance and to a population on a second look. The legend
    is drawn as that two-level tree for the same reason.

    Args:
        values: sample-indexed Series of the field to colour by.
        order: its categories in legend order, top to bottom -- the stacking
            order of the bands too, since the two must agree. Defaults to
            ``group_order`` then sorted within each group, or plain sorted.
            Categories missing from the data are dropped; categories missing
            from ``order`` are appended, so a canonical list (pong's
            ``pop_order.txt``) can be passed as-is against any subset.
        groups: sample-indexed Series nesting the categories (region for
            population). Each category must sit in exactly one group.
        group_order: the groups in legend order; defaults to first appearance
            in ``order``.
        colors: ``{category: "#rrggbb"}`` overriding the generated palette for
            those categories.
        title: the legend heading, e.g. ``"Population"``. Defaults to the
            Series name.
        hue0, arc: the OKLCH hue sweep the groups (or, ungrouped, the
            categories) are spread over -- the widget's own red-to-blue arc,
            stopped before it wraps back to red.
        light, chroma: ``(first, last)`` of the within-group ramp.

    Returns:
        ``{"clusters", "cluster_colors", "cluster_order", "cluster_legend",
        "categories"}`` -- the first four hand straight to
        ``StripeSankeyInline`` (or to :meth:`ModeAnalysis.stripe`'s
        ``colorby``), ``categories`` is the category each integer id means.
    """
    from .cluster_dendrogram import dendrogram_layout

    values = pd.Series(values)
    values = values[values.notna()]
    if values.empty:
        raise ValueError("metadata_palette: no non-null values to colour by")
    values.index = values.index.map(str)
    vals = values.astype(str)
    present = set(vals.unique())

    # -- categories, and the group each one sits in ------------------------
    cat_group = None
    if groups is not None:
        groups = pd.Series(groups)
        groups.index = groups.index.map(str)
        g = groups.reindex(vals.index).astype(str)
        pairs = pd.DataFrame({"cat": vals, "grp": g}).drop_duplicates()
        dup = pairs["cat"].value_counts()
        bad = list(dup[dup > 1].index)
        if bad:
            raise ValueError(f"metadata_palette: {bad[:5]} sit in more than one "
                             f"group; a category must nest in exactly one.")
        cat_group = dict(zip(pairs["cat"], pairs["grp"]))

    if order is None:
        if cat_group is None:
            order = sorted(present)
        else:
            gs = group_order or sorted({cat_group[c] for c in present})
            order = [c for grp in gs
                     for c in sorted(c for c in present if cat_group[c] == grp)]
    else:
        order = [str(c) for c in order]
        order = [c for c in order if c in present]
        order += sorted(present - set(order))
    cats = list(order)
    cid = {c: i for i, c in enumerate(cats)}

    if cat_group is None:                     # every category its own group
        cat_group = {c: c for c in cats}
        gorder = cats[:]
    else:
        gorder = [str(x) for x in group_order] if group_order else []
        gorder = [g for g in gorder if g in set(cat_group.values())]
        for c in cats:                        # groups in order of first use
            if cat_group[c] not in gorder:
                gorder.append(cat_group[c])

    # -- palette: hue per group, lightness within it -----------------------
    members = {g: [c for c in cats if cat_group[c] == g] for g in gorder}
    pal = {}
    ng = len(gorder)
    for gi, grp in enumerate(gorder):
        h = hue0 + (arc * gi / (ng - 1) if ng > 1 else arc / 2)
        mem = members[grp]
        for mi, c in enumerate(mem):
            t = mi / (len(mem) - 1) if len(mem) > 1 else 0.0
            L = light[0] + (light[1] - light[0]) * t
            C = chroma[0] + (chroma[1] - chroma[0]) * t
            pal[cid[c]] = oklch_to_hex(f"oklch({L:.3f} {C:.3f} {h:.1f})")
    for c, hexv in (colors or {}).items():
        if str(c) in cid:
            pal[cid[str(c)]] = str(hexv)

    # -- legend: leaves merge into their group, groups into the root -------
    # A linkage built by hand rather than from a distance: the hierarchy here
    # is given (a population IS in a super-population), not inferred, and
    # faking a distance matrix to recover a tree already known would only
    # add a way for the drawn tree to disagree with the real one.
    n = len(cats)
    legend = {}
    if n > 1:
        Z, nid = [], n
        roots, sizes = [], {}
        for grp in gorder:
            mem = [cid[c] for c in members[grp]]
            node, size = mem[0], 1
            for nxt in mem[1:]:
                Z.append([node, nxt, 1.0, size + 1])
                node, size = nid, size + 1
                nid += 1
            roots.append(node)
            sizes[node] = size
        node, size = roots[0], sizes.get(roots[0], 1)
        for nxt in roots[1:]:
            Z.append([node, nxt, 2.0, size + sizes.get(nxt, 1)])
            size += sizes.get(nxt, 1)
            node = nid
            nid += 1
        counts = vals.value_counts()
        legend = dendrogram_layout(
            np.asarray(Z, dtype=float), list(range(n)), colors=pal,
            labels={cid[c]: c for c in cats},
            sizes={cid[c]: int(counts.get(c, 0)) for c in cats})
        legend["title"] = str(title if title is not None
                              else (values.name or "Category"))
        # The bands stack in the order the legend ENDS UP drawing its leaves,
        # read back from the layout rather than assumed, so the two agree even
        # if scipy orders a tie differently from the list built above.
        stack = [int(l["id"]) for l in sorted(legend["leaves"],
                                              key=lambda d: d["x"])]
    else:
        stack = [0]

    return {
        "clusters": {s: cid[c] for s, c in vals.items()},
        "cluster_colors": pal,
        "cluster_order": stack,
        "cluster_legend": legend,
        "categories": cats,
    }


@dataclass
class ModeAnalysis:
    """Result of :func:`mode_analysis`. Attributes are plain pandas/numpy."""

    runs: dict                      # {run_id: (N, K) DataFrame}, as given
    samples: list                   # the common sample order, length N
    similarity: pd.DataFrame        # (R, R) soft co-membership run similarity
    agreement: pd.DataFrame         # (R, R) the statistic the mode rule used
    modes: pd.Series                # run_id -> mode id, 0 = major mode
    k: object = None                # the K these runs share, or None if mixed
    mode_rule: str = "partition"    # which statistic defined the modes
    threshold: float = 1.0
    rule_detail: object = None      # the mode rule's own output, when it has one
    cluster_kwargs: dict = field(default_factory=dict)   # for the lazy consensus
    _mode_Q: dict = field(default_factory=dict, repr=False)
    _mode_labels: dict = field(default_factory=dict, repr=False)
    _mode_sim: object = field(default=None, repr=False)
    _part_agree: object = field(default=None, repr=False)
    _consensus: object = field(default=None, repr=False)

    # -- the sample-level consensus (lazy) --------------------------------
    # Finding and ordering modes never touches it: `summary`, `separation`,
    # `mode_order` and `run_order` all read only the (R, R) run statistics,
    # which cost milliseconds. The (N, N) affinity and its Leiden partition
    # cost seconds to minutes, so they are built on first access instead of
    # up front -- that is what makes sweeping every K x every mode rule (21
    # analyses on the 1kg_p3 example) a few seconds rather than a few minutes.
    def _ensure_consensus(self):
        if self._consensus is None:
            kw = dict(self.cluster_kwargs)
            palette_kwargs = kw.pop("palette_kwargs", {})
            ids, P_list, _ = _align_runs(self.runs, self.samples)
            Q = consensus_affinity(dict(zip(ids, P_list)))
            labels = cluster_from_affinity(
                Q, resolution=kw.get("resolution", 0.0),
                noise_threshold=kw.get("noise_threshold", 0.0),
                random_state=kw.get("random_state", 0),
                verbose=kw.get("verbose", False))
            if kw.get("order_by_tree", True):
                labels = renumber_by_tree_position(Q, labels)
            self._consensus = (Q, labels,
                               coherent_cluster_palette(Q, labels, **palette_kwargs))
        return self._consensus

    @property
    def Q(self):
        """(N, N) signed consensus affinity over ALL runs. Built on first use."""
        return self._ensure_consensus()[0]

    @property
    def labels(self):
        """(N,) consensus cluster per sample, ``-1`` = noise. Built on first use."""
        return self._ensure_consensus()[1]

    @property
    def colors(self):
        """``{cluster id: "#rrggbb"}`` from the same ``Q``. Built on first use."""
        return self._ensure_consensus()[2]

    # -- ordering ---------------------------------------------------------
    @property
    def n_modes(self):
        return int(self.modes.nunique())

    @property
    def mode_similarity(self):
        """(M, M) mode-level similarity -- :func:`mode_similarity` on this run
        similarity and these modes. Cached."""
        if self._mode_sim is None:
            self._mode_sim = mode_similarity(self.similarity, self.modes)
        return self._mode_sim

    @property
    def partition_agreement(self):
        """(R, R) ARI between the runs' dominant partitions -- exactly what the
        ribbons draw. Cached; identical to :attr:`agreement` when
        ``mode_rule="partition"``."""
        if self._part_agree is None:
            self._part_agree = (self.agreement if self.mode_rule == "partition"
                                else partition_agreement(self.runs, self.samples))
        return self._part_agree

    def separation(self):
        """
        Is the mode rule actually deciding something, or splitting hairs?

        Reports the worst agreement found *inside* a mode against the best found
        *between* two modes, on whichever statistic :attr:`mode_rule` used. The
        gap between them is the room the cut had. A wide gap (on pong's 1kg_p3
        example the partition rule leaves 0.10--0.33 of empty space at every K)
        means the answer would survive any cut-off in that range and the
        threshold is doing no work. A gap near zero means the modes are an
        artefact of where the cut happened to fall, and the split should not be
        reported as if it were structure.

        Returns:
            Series: ``n_modes``, ``worst_within``, ``best_between``, ``gap``.
            ``worst_within`` is NaN when every mode is a single run,
            ``best_between`` when there is only one mode.
        """
        A = self.agreement.to_numpy()
        m = self.modes.reindex(self.agreement.index).to_numpy()
        same = m[:, None] == m[None, :]
        iu = np.triu_indices(len(m), k=1)
        within = A[iu][same[iu]]
        between = A[iu][~same[iu]]
        w = float(within.min()) if within.size else np.nan
        b = float(between.max()) if between.size else np.nan
        return pd.Series({
            "n_modes": self.n_modes,
            "worst_within": w,
            "best_between": b,
            "gap": (w - b) if (within.size and between.size) else np.nan,
        }, name=self.mode_rule)

    def representative(self, mode_id):
        """The run that stands for one mode.

        A mode rule that picks its own representative wins: with
        ``mode_rule="clumppling"`` this is its ``find_repr_modes`` (the member
        with the lowest total *alignment cost* to the rest of its mode), not the
        medoid of this package's soft similarity. The two disagree -- at K=7 of
        the 1kg_p3 example Clumppling picks ``k7r5`` where the soft medoid is
        ``k7r7`` -- and since the representative is the reference every other
        member is permuted onto, using the wrong one would make
        :meth:`mode_usage` and the reported statistics describe a different
        alignment from the one the cited method performed.
        """
        if self.rule_detail and "representatives" in self.rule_detail:
            return self.rule_detail["representatives"][int(mode_id)]
        members = list(self.modes[self.modes == int(mode_id)].index)
        return _representative(self.similarity, members)

    def mode_role(self, mode_id):
        """``"major"``, ``"minor"`` or ``"only"`` -- what kind of mode this is.

        :func:`detect_modes` numbers the modes by descending run count, so id 0
        is the one pong calls the *major mode* and every other id is a minor
        one. ``"only"`` is the unimodal case: with a single mode there is no
        minor mode for "major" to be contrasted with, and saying so would
        wrongly imply the ensemble split.
        """
        if self.n_modes == 1:
            return "only"
        return "major" if int(mode_id) == 0 else "minor"

    def mode_caption(self, mode_id, collapse="representative"):
        """One line of provenance for a mode column: role, evidence, source run.

        What a reader of a mode-axis figure needs in order to weigh the column
        in front of them -- whether it is the ensemble's majority answer, how
        many of the replicates back it, and which single run was collapsed down
        to draw it (:meth:`mode_usage` permutes the rest of the mode onto that
        run, so it is the one whose component numbering the column shows). Used
        as the ``column_sublabels`` text by :meth:`stripe`.
        """
        mode_id = int(mode_id)
        n = int((self.modes == mode_id).sum())
        R = len(self.modes)
        src = (f"rep. {self.representative(mode_id)}"
               if collapse == "representative" else f"mean of {n}")
        return (f"{self.mode_role(mode_id)} mode \u00b7 {src} \u00b7 "
                f"{n} of {R} runs")

    def mode_order(self, by="similarity"):
        """
        The left-to-right order to draw the modes in.

        Args:
            by: ``"similarity"`` (default) -- seriate on :attr:`mode_similarity`
                so adjacent columns are the modes that agree most, which is what
                keeps ribbon crossings at a boundary meaningful rather than
                incidental. ``"size"`` -- mode id order, i.e. descending run
                count, pong's own ordering. ``"ari"`` -- seriate on
                :meth:`mode_agreement` instead: orders by how much the modes'
                *hard partitions* differ rather than their soft co-memberships.
                The two can disagree (at K=7 of 1kg_p3 they do), and ``"ari"``
                is the one the ribbons literally draw, since a ribbon follows
                each sample's dominant component. It costs nothing extra --
                :attr:`partition_agreement` is an ``argmax`` plus a pairwise
                ARI, not a Leiden run.

        Returns:
            list of mode ids.
        """
        if by == "size":
            return sorted(int(m) for m in set(self.modes.tolist()))
        if by == "similarity":
            return _seriate(self.mode_similarity)
        if by == "ari":
            return _seriate(mode_similarity(self.partition_agreement,
                                            self.modes))
        raise ValueError(f"mode_order(by={by!r}): expected "
                         "'similarity', 'size' or 'ari'")

    def run_order(self, by="similarity", representative_first=True):
        """
        Run ids grouped by mode -- the column order :meth:`stripe` draws in, so
        mode boundaries are the only places the ribbons are allowed to scramble.

        Args:
            by: how to order the modes; see :meth:`mode_order`.
            representative_first: put each mode's medoid run at the left of its
                block, so the column pong would have shown for that mode is the
                one nearest the previous boundary.
        """
        order = []
        for m in self.mode_order(by=by):
            members = list(self.modes[self.modes == m].index)
            if representative_first and len(members) > 1:
                rep = self.representative(m)
                members = [rep] + [r for r in members if r != rep]
            order.extend(members)
        return order

    # -- tables -----------------------------------------------------------
    def summary(self):
        """One row per mode: size, within-mode similarity, representative run.

        The same table pong prints in ``result_summary.txt``, so the two can be
        compared line for line.
        """
        S, A = self.similarity, self.agreement
        rows = []
        for m in sorted(self.modes.unique()):
            members = list(self.modes[self.modes == m].index)
            sub = S.loc[members, members].to_numpy()
            asub = A.loc[members, members].to_numpy()
            iu = np.triu_indices(len(members), k=1)
            others = list(self.modes[self.modes != m].index)
            rows.append({
                "mode": int(m),
                "role": self.mode_role(m),
                "n_runs": len(members),
                "runs": " ".join(members),
                "representative": self.representative(m),
                "sim_within": float(sub[iu].mean()) if len(members) > 1 else np.nan,
                "sim_to_others": (float(S.loc[members, others].to_numpy().mean())
                                  if others else np.nan),
                f"{self.mode_rule}_within": (float(asub[iu].min())
                                             if len(members) > 1 else np.nan),
                f"{self.mode_rule}_to_others": (
                    float(A.loc[members, others].to_numpy().max())
                    if others else np.nan),
            })
        return pd.DataFrame(rows).set_index("mode")

    def cluster_table(self):
        """One row per consensus cluster: size and its own cohesion in ``Q``."""
        Cq = coarse_affinity(self.Q, self.labels)
        sizes = coarse_sizes(self.labels)
        df = pd.DataFrame({"n": sizes, "cohesion": pd.Series(np.diag(Cq), index=Cq.index)})
        df.index.name = "cluster"
        n_noise = int((np.asarray(self.labels) == -1).sum())
        if n_noise:
            df.loc[-1] = [n_noise, np.nan]
        return df

    # -- per-mode consensus ----------------------------------------------
    def mode_Q(self, mode_id):
        """The consensus affinity built from one mode's runs only.

        ``self.Q`` pools every run and so shows what survives the disagreement;
        this shows what a single mode on its own claims. Cached.
        """
        mode_id = int(mode_id)
        if mode_id not in self._mode_Q:
            members = list(self.modes[self.modes == mode_id].index)
            sub = {r: self.runs[r] for r in members}
            ids, P_list, _ = _align_runs(sub, self.samples)
            self._mode_Q[mode_id] = consensus_affinity(dict(zip(ids, P_list)))
        return self._mode_Q[mode_id]

    def mode_labels(self, mode_id, **kw):
        """Consensus clusters this mode alone would give.

        Cached on ``(mode_id, kw)``: Leiden on a dense N x N signed graph is by
        far the most expensive step here, and :meth:`mode_agreement` asks for
        every mode's labels, so an uncached call would repeat that work for each
        caller.
        """
        key = (int(mode_id), tuple(sorted(kw.items())))
        if key not in self._mode_labels:
            self._mode_labels[key] = cluster_from_affinity(
                self.mode_Q(mode_id), **kw)
        return self._mode_labels[key]

    def mode_agreement(self, **kw):
        """
        (M, M) DataFrame of adjusted Rand index between the partitions each mode
        implies on its own.

        This is the number that says whether a mode split matters. Two modes can
        differ enough to fail a 0.97 similarity cut and still agree on 97% of
        the partition -- pong reports the split either way, this says how much
        of the answer actually moves.
        """
        from sklearn.metrics import adjusted_rand_score

        ms = sorted(self.modes.unique())
        lab = {m: self.mode_labels(m, **kw) for m in ms}
        A = np.eye(len(ms))
        for i, a in enumerate(ms):
            for j, b in enumerate(ms):
                if i < j:
                    A[i, j] = A[j, i] = adjusted_rand_score(lab[a], lab[b])
        return pd.DataFrame(A, index=[f"M{m}" for m in ms], columns=[f"M{m}" for m in ms])

    def instability(self, normalise=True):
        """
        Per-sample score: how much the modes disagree about **this** sample.

        For every pair of modes, the mean absolute difference between the two
        modes' affinity rows for sample i, weighted by the two modes' run
        counts. High = this sample's relationships change depending on which
        mode a run landed in; ~0 = every mode places it the same way and the
        split is about other samples entirely.

        Args:
            normalise: divide by the largest score, so the top sample is 1.0.
                Set False to keep the raw affinity units.

        Returns:
            Series indexed by sample id, descending. All-zero (with a warning-free
            return) when there is only one mode.
        """
        ms = sorted(self.modes.unique())
        n = len(self.samples)
        if len(ms) < 2:
            return pd.Series(np.zeros(n), index=self.samples,
                             name="instability")
        sizes = {m: int((self.modes == m).sum()) for m in ms}
        acc = np.zeros(n)
        wsum = 0.0
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                w = sizes[a] * sizes[b]
                acc += w * np.abs(self.mode_Q(a) - self.mode_Q(b)).mean(axis=1)
                wsum += w
        score = acc / wsum
        if normalise and score.max() > 0:
            score = score / score.max()
        return pd.Series(score, index=self.samples,
                         name="instability").sort_values(ascending=False)

    # -- collapsing a mode to one column ----------------------------------
    def mode_usage(self, mode_id, collapse="representative"):
        """
        One (N, K) usage matrix standing for a whole mode.

        Args:
            mode_id: which mode.
            collapse: ``"representative"`` (default) -- the mode's medoid run,
                unchanged. This is pong's choice, and it involves no alignment
                at all: the numbers drawn are a real run's numbers.
                ``"mean"`` -- every run in the mode permuted onto the
                representative's component order (:func:`_align_to`) and
                averaged. Smoother, and the permutation is unambiguous *because*
                the runs are already one mode, but the column is then a
                construct rather than a run anyone fitted.

        Returns:
            DataFrame (N x K), sample index, ``MC0..`` columns.
        """
        members = list(self.modes[self.modes == int(mode_id)].index)
        rep = self.representative(mode_id)
        ids, P_list, samples = _align_runs(
            {r: self.runs[r] for r in ([rep] + [m for m in members if m != rep])},
            self.samples)
        P = P_list[0]
        if collapse == "mean" and len(P_list) > 1:
            P = np.mean([P_list[0]] + [_align_to(P_list[0], Q)[0]
                                       for Q in P_list[1:]], axis=0)
        elif collapse not in ("mean", "representative"):
            raise ValueError(f"collapse={collapse!r}: expected "
                             "'representative' or 'mean'")
        return pd.DataFrame(P, index=samples,
                            columns=[f"MC{t}" for t in range(P.shape[1])])

    def collapse_report(self):
        """
        Per-run check on the within-mode alignment ``collapse="mean"`` relies on.

        ``residual`` is the mean absolute per-entry disagreement with the mode's
        representative after permuting components onto it. Near zero is the
        claim "this really is one mode" made numerically; a large value means
        ``threshold`` is too loose and a run was put in a mode it does not
        belong to.
        """
        rows = []
        for m in sorted(self.modes.unique()):
            members = list(self.modes[self.modes == m].index)
            rep = self.representative(m)
            ids, P_list, _ = _align_runs(
                {r: self.runs[r] for r in ([rep] + [x for x in members if x != rep])},
                self.samples)
            for rid, P in zip(ids, P_list):
                rows.append({"mode": int(m), "run": rid, "representative": rid == rep,
                             "residual": 0.0 if rid == rep
                             else _align_to(P_list[0], P)[1]})
        return pd.DataFrame(rows).set_index(["mode", "run"])

    # -- visualisation ----------------------------------------------------
    def payload(self, by="run", *, order=None, mode_order="similarity",
                collapse="representative", label_modes=True, clusters=None):
        """
        The ``sankey_data`` dict for a run-axis or mode-axis StripeSankey.

        The widget indexes its columns by integer, so column *i* is handed to it
        as pseudo-K ``i + 1`` and given its real name back through
        ``column_labels`` -- the axis is the only thing that changes. Every other
        part of the cluster-lineage renderer (census nodes, count-accurate
        ribbons, crossing-minimised ordering, OKLCH lineage) is the one in use
        for the K axis, and the consensus clusters colouring it are the same
        ``self.labels`` in both views, so the two are directly comparable.

        Args:
            by: ``"run"`` -- one column per run, grouped by mode.
                ``"mode"`` -- one column per mode, each collapsed by
                ``collapse``. The mode view is pong's summary (its per-mode
                barplots) redrawn as a Sankey, so every ribbon in it is a real
                mode-to-mode disagreement rather than a replicate.
            order: explicit column order (run ids, or mode ids when
                ``by="mode"``); overrides ``mode_order``.
            mode_order: how to order the modes; see :meth:`mode_order`.
            collapse: ``by="mode"`` only; see :meth:`mode_usage`.
            label_modes: append the mode id to a run-axis column heading.
            clusters: ``{sample id: int}`` to colour by instead of
                :attr:`labels`. Anything but ``None`` also means the sample
                consensus is never built, which is the expensive part of this
                class -- a metadata colouring does not need it.

        Returns:
            ``(sankey_data, column_labels, column_sublabels)``. The third is the
            small grey qualifier line under each heading -- for ``by="mode"``
            :meth:`mode_caption`, which names the mode's role (major / minor),
            the run it was collapsed from and how many replicates back it; for
            ``by="run"``, that run's mode role and whether it is the medoid.
        """
        if by not in ("run", "mode"):
            raise ValueError(f"payload(by={by!r}): expected 'run' or 'mode'")

        if by == "run":
            cols = list(order or self.run_order(by=mode_order))
            ids, P_list, samples = _align_runs({r: self.runs[r] for r in cols},
                                               self.samples)
            heads = [f"{r} · M{int(self.modes[r])}" if label_modes else str(r)
                     for r in ids]
            reps = {self.representative(m) for m in set(self.modes.tolist())}
            subs = [self.mode_role(self.modes[r])
                    + (" mode · representative" if r in reps else " mode")
                    for r in ids]
        else:
            cols = [int(m) for m in (order or self.mode_order(by=mode_order))]
            frames = [self.mode_usage(m, collapse=collapse) for m in cols]
            samples = list(frames[0].index)
            P_list = [f.to_numpy() for f in frames]
            ids = [f"M{m}" for m in cols]
            # One column per mode, so the K every column shares goes on the
            # heading -- a figure of a single K is read on its own -- and what
            # separates the columns, which mode and backed by what, goes under it.
            kk = "" if self.k is None else f"K = {self.k} · "
            heads = [f"{kk}M{m}" for m in cols]
            subs = [self.mode_caption(m, collapse=collapse) for m in cols]

        theta, labels, sublabels = {}, {}, {}
        for col, (P, head, sub) in enumerate(zip(P_list, heads, subs), start=1):
            theta[str(col)] = {s: [float(v) for v in row]
                               for s, row in zip(samples, P)}
            labels[str(col)] = head
            sublabels[str(col)] = sub
        return {
            "theta": theta,
            "k_range": list(range(1, len(P_list) + 1)),
            "clusters": ({
                "sample_to_cluster": {str(s): int(c) for s, c in clusters.items()},
                "n_clusters": int(len({int(c) for c in clusters.values()
                                       if int(c) != -1})),
            } if clusters is not None else {
                "sample_to_cluster": {s: int(c) for s, c in zip(samples, self.labels)},
                "n_clusters": int(len({int(c) for c in self.labels if c != -1})),
            }),
            "metadata": {
                "total_samples": len(samples),
                "axis": by,
                "k": self.k,
                "columns": ids,
                "modes": {r: int(self.modes[r]) for r in self.modes.index},
                "collapse": collapse if by == "mode" else None,
                "representatives": {int(m): self.representative(m)
                                    for m in sorted(set(self.modes.tolist()))},
                "roles": {int(m): self.mode_role(m)
                          for m in sorted(set(self.modes.tolist()))},
            },
        }, labels, sublabels

    def stripe(self, by="run", *, order=None, mode_order="similarity",
               collapse="representative", metadata_df=None, hover_field=None,
               width=1400, height=760, save_path=None, legend=True,
               label_modes=True, sublabels=True, colorby=None, **kwargs):
        """
        The prototype figure: one StripeSankey column per run, or per mode.

        ``by="run"`` -- read it left to right. Inside a mode the ribbons run
        flat: replicate runs place every sample the same way, and the only thing
        that changed is which integer each component was given, which the layout
        absorbs silently. At a mode boundary a block of ribbons crosses -- those
        samples, named by :meth:`instability`, are what the modes disagree
        about. This view shows the evidence: how many runs back each mode, and
        that the flat stretches really are flat.

        ``by="mode"`` -- the same figure with each mode collapsed to one column,
        so every ribbon is a mode-to-mode disagreement and nothing on the page is
        a replicate. This is pong's per-mode barplot summary redrawn as one
        connected figure, and it is the publication form: R columns become M.

        Columns are ordered by :meth:`mode_order` (``"similarity"`` by default,
        so the modes that agree most sit side by side) rather than by run count.

        Args:
            by: ``"run"`` or ``"mode"``; see :meth:`payload`.
            order: explicit column order, overriding ``mode_order``.
            mode_order: ``"similarity"`` (default), ``"size"`` or ``"ari"``.
            collapse: ``by="mode"`` only -- ``"representative"`` (default) or
                ``"mean"``; see :meth:`mode_usage`.
            metadata_df: sample-indexed metadata for hover composition.
            hover_field: metadata column(s) to break down on hover.
            colorby: colour the bands by a metadata field instead of by the
                consensus clusters -- a column name of ``metadata_df``, or a
                ready-made :func:`metadata_palette` dict when the categories
                need an order, a nesting or a palette of their own. The
                geometry is untouched (it is a pure function of the runs), so
                the two colourings of one K are the same figure twice and can
                be read against each other. Building the sample consensus is
                skipped entirely on this path.
            legend: draw the consensus-cluster dendrogram in the left column,
                built from the same ``Q`` the colours come from. With
                ``colorby`` it is that field's own legend instead.
            sublabels: print the qualifier line under each column heading --
                :meth:`mode_caption` on the mode axis ("minor mode · rep.
                k6r1 · 2 of 8 runs"), the run's mode role on the run axis.
                ``False`` restores the one-line headings.
            save_path: also write a self-contained interactive .html here.
            **kwargs: forwarded to ``StripeSankeyInline``. ``layout_effort``
                is the useful one here: how hard the layout searches for a
                stack order with fewer ribbon crossings. 1.0 (the default,
                tens of ms) already gets the run axis down to no crossings at
                all on 1kg_p3; 0 falls back to the plain forward barycentre
                pass; 10-20 is for a figure being exported once.

        Returns:
            ``StripeSankeyInline``. Display it in marimo via
            ``mo.ui.anywidget(...)``.
        """
        from .stripesankey import StripeSankeyInline, save_widget_html

        pal = None
        if colorby is not None:
            if isinstance(colorby, dict):
                pal = colorby
            else:
                if metadata_df is None:
                    raise ValueError(f"stripe(colorby={colorby!r}) needs "
                                     "metadata_df to read that column from.")
                if colorby not in metadata_df.columns:
                    raise KeyError(f"stripe(colorby={colorby!r}): not a column "
                                   f"of metadata_df ({list(metadata_df.columns)})")
                pal = metadata_palette(metadata_df[colorby], title=str(colorby))

        data, column_labels, column_sublabels = self.payload(
            by, order=order, mode_order=mode_order, collapse=collapse,
            label_modes=label_modes,
            clusters=(pal["clusters"] if pal else None))
        opts = dict(sankey_data=data, mode="cluster_prox",
                    width=width, height=height,
                    cluster_colors=(pal["cluster_colors"] if pal else self.colors),
                    column_labels=column_labels,
                    column_sublabels=(column_sublabels if sublabels else {}))
        if pal:
            opts["cluster_order"] = pal["cluster_order"]
            if legend and pal["cluster_legend"]:
                opts["cluster_legend"] = pal["cluster_legend"]
        elif legend and len(self.colors) > 1:
            from .cluster_dendrogram import dendrogram_layout
            Cq = coarse_affinity(self.Q, self.labels)
            opts["cluster_legend"] = dendrogram_layout(
                coarse_linkage(Cq), list(Cq.index),
                colors=self.colors, sizes=coarse_sizes(self.labels).to_dict())
        if metadata_df is not None:
            md = metadata_df.copy()
            md.index = md.index.map(str)
            opts["metadata"] = {s: {c: _jsonable(v) for c, v in row.items()}
                                for s, row in md.iterrows()}
        if hover_field is not None:
            opts["hover_field"] = hover_field
        opts.update(kwargs)

        w = StripeSankeyInline(**opts)
        if save_path:
            save_widget_html(w, save_path)
        return w


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    return str(v)


# --------------------------------------------------------------------------
# (4) the one-call entry point
# --------------------------------------------------------------------------
def consensus_from_runs(runs, samples=None, *, resolution=0.0,
                        noise_threshold=0.0, random_state=0,
                        order_by_tree=True, **palette_kwargs):
    """
    The sample-level consensus, computed from **any** set of runs and returned
    on its own.

    :func:`mode_analysis` computes this internally from the runs it was given,
    which means the answer depends on *which ensemble you handed it* -- and it
    should, since "what is stable" is only a question about a particular set of
    models. That does make two figures disagree when they were built from
    different ensembles, which is a presentation problem rather than a
    statistical one. On the 1kg_p3 example:

    ======================================== ========= ==========
    ensemble                                  members   clusters
    ======================================== ========= ==========
    one representative run per K (K=2..8)         7          4
    the 8 replicate runs at K=4                   8          4
    the 8 replicate runs at K=6 or K=7            8          5
    the full grid, 7 K x 8 runs                  56          4
    ======================================== ========= ==========

    The full grid agrees with the per-K route almost exactly (ARI 0.999); the
    single-K run ensembles are the outliers (ARI ~0.95 against either), because
    they resolve one extra cluster -- the 64 near-unadmixed PEL/MXL -- that
    pooling across K washes out, there being no Native American component at all
    at K = 2 or 3.

    Pass the result to ``mode_analysis(..., clusters=...)`` when several figures
    should share one labelling and one palette.

    Args:
        runs: ``{run_id: (N, K) usage}``. K may differ between runs; the
            chance correction handles that, which is the whole point of
            :func:`~stripesankey.mr_consensus.consensus_affinity`.
        samples: common sample order to reindex DataFrames onto.
        resolution, noise_threshold, random_state, order_by_tree,
        **palette_kwargs: as in :func:`mode_analysis`.

    Returns:
        ``{"Q", "labels", "colors", "samples"}``.
    """
    ids, P_list, samples = _align_runs(runs, samples)
    Q = consensus_affinity(dict(zip(ids, P_list)))
    labels = cluster_from_affinity(Q, resolution=resolution,
                                   noise_threshold=noise_threshold,
                                   random_state=random_state, verbose=False)
    if order_by_tree:
        labels = renumber_by_tree_position(Q, labels)
    return {"Q": Q, "labels": labels, "samples": samples,
            "colors": coherent_cluster_palette(Q, labels, **palette_kwargs)}


_RULE_DEFAULT_THRESHOLD = {"partition": 1.0, "similarity": 0.97,
                           "consensus": 0.25, "clumppling": 1.0}


def mode_analysis(runs, *, samples=None, k=None, mode_rule="partition",
                  threshold=None, min_gap=0.05, test_comm=True,
                  clusters=None, cluster=True, resolution=0.0,
                  noise_threshold=0.0, random_state=0, order_by_tree=True,
                  verbose=True, **palette_kwargs):
    """
    Replicate runs at one K -> modes, consensus clusters, and a run-axis figure.

    Runs the whole route in one call: :func:`run_similarity` (alignment-free) ->
    :func:`detect_modes` (pong's clique rule) ->
    :func:`~stripesankey.mr_consensus.consensus_affinity` over every run ->
    Leiden on the signed affinity -> an OKLCH palette from that same affinity.
    The consensus is taken over *all* runs, not just the major mode, so the
    clusters it reports are the ones every mode agrees on; use
    :meth:`ModeAnalysis.mode_Q` for what one mode says on its own.

    Args:
        runs: ``{run_id: (N, K) usage}`` -- sample x MC DataFrames (index =
            sample id) or arrays on a common sample order. Typically every
            replicate at one K; :func:`load_pong_filemap` returns exactly this.
        samples: common sample order to reindex onto.
        k: the K these runs share, recorded for labelling. Inferred when every
            run has the same width.
        mode_rule: what defines a mode.

            * ``"partition"`` (default) -- two runs share a mode when their
              **dominant-component partitions are identical**, i.e.
              :func:`partition_agreement` is exactly 1. Parameter-free: 1.0 is
              an exact identity, not a tuned cut-off, so "same mode" is a real
              equivalence relation. It is also the criterion the figure draws --
              ARI 1 means every ribbon between those two columns runs flat --
              and it reproduces pong's mode decomposition at all seven K of the
              1kg_p3 example with 0.10--0.33 of empty space around the cut
              (:meth:`ModeAnalysis.separation`).
            * ``"similarity"`` -- pong's own rule: cliques at
              :func:`run_similarity` >= 0.97. Uses the soft usage rather than
              just the argmax, and tolerates a handful of samples disagreeing,
              at the price of a magic number.
            * ``"consensus"`` -- Leiden on :func:`consensus_run_affinity`, the
              same signed-affinity machinery the sample clustering uses. Grades
              runs *relative to this ensemble* rather than absolutely, so it
              still finds structure when nothing is near-identical and the other
              two rules would return R singleton modes.
            * ``"clumppling"`` -- the published method, ported in
              :mod:`~stripesankey.clumppling`: align each pair of replicates,
              score them by ``||P - alpha(Q)||_F**2 / (2N)``, build a complete
              graph of normalised similarities, test it for community structure
              with a Tracy-Widom test, then partition it with Louvain. Use it
              when the modes should be ones a reviewer can look up rather than
              ones this workflow defined. **Its defaults are wrong for a small
              ensemble, and its authors know it.** The Tracy-Widom pre-test is
              asymptotic: on the 1kg_p3 example (R = 8 per K) it reports no
              structure at any K -- even where the cost matrix is a perfect
              two-block matrix -- so the whole range collapses to one mode.
              Clumppling's own ``examples/align_1kG.sh``, for this same dataset,
              therefore passes ``--test_comm F --cd_res 1.05``; with those
              settings (``test_comm=False, threshold=1.05`` here) it finds
              8 / 8 / 7+1 / 8 / 5+3 / 4+4 / 7+1, which this port reproduces
              exactly. Even then it merges pong's two minor modes at K = 6 and
              K = 7. :attr:`ModeAnalysis.rule_detail` carries the full
              Clumppling output (cost matrix, ``mode_stats``, per-mode average
              Q, and which branch decided).

        threshold: how strict that rule is; ``None`` (default) takes the rule's
            own default -- 1.0, 0.97, 0.25 and 1.0 respectively. For
            ``"clumppling"`` it is the Louvain resolution. For ``"consensus"``
            it is the Constant Potts resolution, not a similarity cut.

            Pass ``"gap"`` (clique rules only) to let the data place the cut:
            :func:`widest_gap` puts it in the widest interval the observed
            agreements leave empty. This is the setting for a noisy ensemble.
            ``mode_rule="partition"`` with ``threshold=1.0`` demands exact
            identity and returns R singleton modes the moment replicates stop
            matching sample-for-sample; lowering it to a **fixed** number is
            fragile in both directions -- on synthetic ensembles with two true
            modes of three runs each, 0.95 recovers the truth at per-run jitter
            0.005, misses it entirely at 0.03 and 0.08, and *invents* a split on
            a unimodal-but-noisy ensemble. ``"gap"`` gets all four right,
            because "close enough" is not a fixed distance: it depends on how
            noisy the ensemble is, which is exactly what the gap measures.
            :func:`threshold_scan` shows every answer available and the
            threshold range that gives it.
        test_comm: ``mode_rule="clumppling"`` only -- run its Tracy-Widom
            community-structure pre-test before Louvain (Clumppling's own
            default). ``False`` goes straight to Louvain, which is what makes
            the rule usable at small R.
        min_gap: with ``threshold="gap"``, the smallest interval that counts as
            a real separation; below it the runs are one mode. The residual
            parameter, and a far less sensitive one than a cut location -- it
            fixes how convincing a separation must be, not where the line is,
            so the answer moves only when the structure genuinely weakens.
        resolution: Constant Potts tau for the sample clustering. ``0.0`` =
            "group samples that co-occur above chance" -- meaningful only
            because the affinity is chance-corrected.
        noise_threshold: samples weakly attached to their own cluster become
            ``-1``.
        order_by_tree: number clusters by their position in their own
            dendrogram rather than by size, so neighbouring ids are
            neighbouring clusters.
        clusters: use this sample labelling instead of computing one from these
            runs -- either the dict :func:`consensus_from_runs` returns, or a
            bare label array/Series on ``samples``. The consensus is a property
            of the ensemble it was computed from, so the run-axis figure at one
            K and the K-axis figure over K=2..8 do **not** otherwise show the
            same clusters (4 against 5 on the 1kg_p3 example). Pass a shared
            labelling here when several figures must agree; leave it ``None`` to
            let each answer for its own ensemble.
        cluster: build the (N, N) sample-level consensus now (default). ``False``
            defers it to the first use of :attr:`~ModeAnalysis.Q`,
            :attr:`~ModeAnalysis.labels`, :attr:`~ModeAnalysis.colors` or
            :meth:`~ModeAnalysis.stripe` -- it controls *when*, never *whether*.
            Finding and ordering modes never needs it, so a sweep over many K or
            several ``mode_rule`` values should pass ``False`` and skip a Leiden
            run on N nodes per analysis. Forced on by ``verbose``, which prints
            the cluster count.
        verbose: print the mode table as it is found.
        **palette_kwargs: forwarded to
            :func:`~stripesankey.mr_consensus.lineage_palette`.

    Returns:
        :class:`ModeAnalysis`.
    """
    ids, P_list, samples = _align_runs(runs, samples)
    if k is None:
        widths = {P.shape[1] for P in P_list}
        k = int(widths.pop()) if len(widths) == 1 else None

    if mode_rule not in _RULE_DEFAULT_THRESHOLD:
        raise ValueError(f"mode_analysis(mode_rule={mode_rule!r}): expected one "
                         f"of {sorted(_RULE_DEFAULT_THRESHOLD)}")
    if threshold is None:
        threshold = _RULE_DEFAULT_THRESHOLD[mode_rule]

    P_by_id = dict(zip(ids, P_list))
    S = run_similarity(P_by_id, samples=samples)
    rule_detail = None

    if mode_rule == "clumppling":
        from .clumppling import clumppling_modes
        if threshold == "gap":
            raise ValueError("threshold='gap' is a cut on an agreement matrix; "
                             "the clumppling rule's threshold is a Louvain "
                             "resolution. Pass a number (its default is 1.0).")
        rule_detail = clumppling_modes(P_by_id, samples=samples,
                                       res=float(threshold), test_comm=test_comm,
                                       random_state=random_state)
        modes = rule_detail["modes"]
        # G' = 1 - sqrt(cost) is Clumppling's OWN similarity (its "Performance"
        # column), so `agreement`, `summary` and `separation` all read the
        # statistic the rule used rather than a second one invented here.
        A = rule_detail["gprime"]
    else:
        A = (partition_agreement(P_by_id, samples=samples)
             if mode_rule == "partition" else S)
        modes = detect_modes(A, threshold=threshold, min_gap=min_gap,
                             method="consensus" if mode_rule == "consensus" else "clique",
                             random_state=random_state)
        if threshold == "gap":                # record what the data actually chose
            threshold, _gap = widest_gap(A, min_gap=min_gap)
            threshold = "gap (no split)" if threshold is None else round(threshold, 4)

    ma = ModeAnalysis(runs={r: runs[r] for r in ids}, samples=samples,
                      similarity=S, agreement=A, modes=modes, k=k,
                      mode_rule=mode_rule, threshold=threshold,
                      rule_detail=rule_detail,
                      cluster_kwargs=dict(resolution=resolution,
                                          noise_threshold=noise_threshold,
                                          random_state=random_state,
                                          order_by_tree=order_by_tree,
                                          verbose=verbose,
                                          palette_kwargs=palette_kwargs))
    if clusters is not None:
        if isinstance(clusters, dict):
            ma._consensus = (clusters.get("Q"), np.asarray(clusters["labels"]),
                             clusters.get("colors") or {})
        else:
            lab = np.asarray(getattr(clusters, "to_numpy", lambda: clusters)())
            if lab.shape[0] != len(samples):
                raise ValueError(f"clusters has {lab.shape[0]} labels, expected "
                                 f"{len(samples)}")
            ma._consensus = (None, lab, {})
    elif cluster:
        ma._ensure_consensus()
    if (mode_rule == "clumppling" and ma.n_modes == 1 and len(ids) > 2
            and rule_detail["report"].get("has_comm_struc") is False):
        warnings.warn(
            f"clumppling: the Tracy-Widom pre-test found no community structure "
            f"among {len(ids)} replicates, so every run is one mode. That test "
            f"is asymptotic and has little power at small R -- on the 1kg_p3 "
            f"example it says the same at every K even where the cost matrix is "
            f"a perfect two-block matrix, and only starts rejecting at R = 16. "
            f"Run more replicates, or pass test_comm=False to go straight to "
            f"Louvain.")
    if mode_rule == "partition" and ma.n_modes == len(ids) > 1:
        warnings.warn(
            "every run became its own mode: no two runs agree on the dominant "
            "partition exactly. That is the honest answer for a noisy ensemble, "
            "but if you want near-identity rather than identity use "
            "mode_rule='similarity', or mode_rule='consensus' to grade runs "
            "relative to each other instead of absolutely.")
    if verbose:
        labels, colors = ma.labels, ma.colors     # forces the consensus
        n_noise = int((labels == -1).sum())
        cut = (rule_detail["report"].get("route", "clumppling")
               if mode_rule == "clumppling" else
               "dominant partitions identical" if mode_rule == "partition"
               and ma.threshold == 1.0 else
               f"{mode_rule} >= {ma.threshold}" if mode_rule != "consensus"
               else f"signed-affinity Leiden at tau = {ma.threshold}")
        print(f"K={k}: {len(ids)} runs -> {ma.n_modes} mode(s) [{cut}]")
        print(ma.summary().to_string())
        _sep = ma.separation()
        if ma.n_modes > 1:
            print(f"separation: worst within {_sep['worst_within']:.4f} vs best "
                  f"between {_sep['best_between']:.4f} -> gap {_sep['gap']:.4f}")
        print(f"consensus over all runs: {len(colors)} cluster(s)"
              + (f", {n_noise} sample(s) noise" if n_noise else ""))
    return ma


def modestripe(runs, by="run", *, samples=None, k=None, mode_rule="partition",
               threshold=None, mode_order="similarity", collapse="representative",
               metadata_df=None, hover_field=None, colorby=None, save_path=None,
               width=1400, height=760, verbose=True, **kwargs):
    """
    One call, one figure: replicate runs in, run- or mode-axis StripeSankey out.

    The run-axis counterpart of :func:`~stripesankey.hardstripe` --
    :func:`mode_analysis` followed by :meth:`ModeAnalysis.stripe`, for when the
    analysis object itself is not wanted. Returns ``(widget, ModeAnalysis)`` so
    the tables are still reachable.

    Args:
        by: ``"run"`` (one column per run) or ``"mode"`` (one per mode).
        mode_order, collapse, colorby: see :meth:`ModeAnalysis.stripe`.
    """
    ma = mode_analysis(runs, samples=samples, k=k, mode_rule=mode_rule,
                       threshold=threshold, verbose=verbose)
    w = ma.stripe(by, mode_order=mode_order, collapse=collapse,
                  metadata_df=metadata_df, hover_field=hover_field,
                  colorby=colorby, width=width, height=height,
                  save_path=save_path, **kwargs)
    return w, ma
