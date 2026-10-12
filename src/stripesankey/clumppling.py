"""
A port of Clumppling's mode-detection step, for use on the run axis.

Mode detection is not this workflow's contribution, so this module does not
invent one: it reproduces the published method of

    Liu X, Kopelman NM, Rosenberg NA (2024) Clumppling: cluster matching and
    permutation program with integer linear programming. *Bioinformatics*
    40(1):btad751.

as implemented in ``PopGenClustering/Clumppling`` (v2, ``master``), so that the
modes reported here are the modes that tool reports and can be cited as such.
Function names below match the originals -- ``cost_membership``,
``align_within_k``, ``cost_to_adj``, ``test_comm_struc``, ``detect_communities``,
``find_repr_modes`` -- to keep the port auditable line by line against
``clumppling/core.py``, ``clumppling/utils.py`` and
``clumppling/detectMode/utils.py``.

The method, in order
--------------------
1. **Align every pair of replicates** (``align_within_k``). Clumppling solves a
   small integer program to map one replicate's clusters onto another's. Within
   a single K -- which is the only case mode detection needs -- its constraints
   (each cluster of Q maps to exactly one cluster of P, each cluster of P
   receives at least one) force a *bijection*, so the program is an ordinary
   linear assignment and :func:`scipy.optimize.linear_sum_assignment` returns
   the same optimum without an ILP solver. See :func:`align_pair`.
2. **Score the aligned pair** (eq. 9) with

       cost(P, Q) = ||P - alpha(Q)||_F**2 / (2N)

   which is ``utils.cost_membership``. Costs form a symmetric (R, R) matrix with
   a zero diagonal and entries in [0, 1].
3. **Turn costs into a complete weighted graph** (eq. 13, ``cost_to_adj`` with
   ``norm=True``)::

       u_ij = 1 - (cost_ij - cost_min) / (cost_max - cost_min)

   so the most similar pair of replicates has weight 1 and the least similar
   exactly 0. Nothing is thresholded away; the graph stays complete.
4. **Test whether there is community structure at all** (``test_comm_struc``),
   by a Tracy-Widom test on the extreme eigenvalues of the standardised
   adjacency matrix and of its exponentiated form, at alpha = 0.01 with a
   Bonferroni split over the four statistics. If the test does not reject, every
   replicate is one mode -- Clumppling does not partition a graph that has no
   structure to partition.
5. **Run Louvain** on that graph (``cd_default``), at resolution 1 by default.
   Modes are renumbered by decreasing size, ties by first appearance.
6. **Summarise each mode**: its representative is the replicate with the lowest
   total cost to the rest of its mode (``find_repr_modes``); its ``Cost`` and
   ``Performance`` are the mean of the within-mode cost block and of
   ``G' = 1 - sqrt(cost)``; its average Q is every member aligned onto the
   representative and averaged (eq. 14).

Deviations, all deliberate and all listed
-----------------------------------------
* **The ILP is replaced by a linear assignment.** Equal-K only, where the two
  are provably the same optimisation (see step 1). Different-K alignment, which
  genuinely needs the integer program, is not ported: it belongs to
  alignment-across-K, not to mode detection. :func:`align_pair` raises on
  mismatched K rather than guessing.
* **Louvain comes from ``python-louvain`` directly**, not through ``cdlib``.
  ``cdlib.algorithms.louvain`` is a thin wrapper that calls
  ``community_louvain.best_partition(g, weight="weight", resolution=res,
  randomize=None)``; this module calls exactly that, so the partition is
  identical without the heavier dependency.
* **``random_state`` defaults to 0, not to unseeded.** Louvain is randomised and
  ``python-louvain`` with no seed draws from the global NumPy RNG, which makes a
  run irreproducible; Clumppling added ``--random_seed`` in 2.0.8 for the same
  reason. Pass ``random_state=None`` for the upstream default.
* **Rows are normalised to sum to 1.** Clumppling validates that its ``.Q``
  input already does; NMF or LDA usage matrices do not, and every other module
  here normalises, so this one does too.

Settings: the defaults are not what the authors use here
--------------------------------------------------------
``clumppling_modes`` keeps upstream's defaults (``test_comm=True``,
``res=1.0``), and on eight replicates those return **one mode at every K** --
verified by running the real program end to end, not inferred. The Tracy-Widom
test is asymptotic and has no power at eight nodes: at K = 4 the cost matrix is
a perfect two-block matrix (one run 0.16 from every other, the other seven
identical to 1e-16) and it still does not reject.

That is a property of the defaults at small R, not a flaw in the method, and
Clumppling's authors are ahead of it: their own ``examples/align_1kG.sh``, for
this very dataset and commented "reproduce Pong's results", passes

    --test_comm F --cd_res 1.05

With those settings the program finds 8 / 8 / 7+1 / 8 / 5+3 / 4+4 / 7+1 across
K = 2..8, and this port reproduces that exactly -- mode sizes at every K, costs
and performances to 1e-9 (see ``scripts/validate_clumppling_port.py``). Worth
knowing even so: at K = 6 and K = 7 that still merges pong's two minor modes
(5+3 against pong's 5+2+1; 4+4 against 4+2+2), so "reproduce Pong's results" is
close but not exact on this data.

Requires ``python-louvain``, ``networkx`` and ``TracyWidom`` -- core
dependencies, imported lazily so ``import stripesankey`` stays fast.
"""
from collections import Counter

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

__all__ = [
    "cost_membership",
    "align_pair",
    "align_within_k",
    "cost_to_adj",
    "test_comm_struc",
    "detect_communities",
    "find_repr_modes",
    "clumppling_modes",
]


# --------------------------------------------------------------------------
# step 1-2: pairwise alignment and cost   (clumppling/core.py, utils.py)
# --------------------------------------------------------------------------
def cost_membership(P, Q):
    """``||P - Q||_F**2 / (2N)`` -- ``clumppling.utils.cost_membership``."""
    if P.shape != Q.shape:
        raise ValueError(f"P {P.shape} and Q {Q.shape} must have the same size")
    return float(np.linalg.norm(P - Q, ord="fro") ** 2 / (2 * P.shape[0]))


def align_pair(P, Q):
    """
    Optimally permute ``Q``'s clusters onto ``P``'s -- ``core.align_ILP`` at
    equal K.

    Clumppling minimises ``sum_q D[q, alpha(q)]`` over assignments, with
    ``D = cdist(Q.T, P.T, "sqeuclidean") / N``, subject to each cluster of Q
    taking exactly one cluster of P and each cluster of P receiving at least
    one. With ``K_P == K_Q`` those constraints admit only bijections, so this is
    the linear assignment problem and the Hungarian algorithm attains the ILP's
    optimum exactly.

    Returns:
        ``(idxQ2P, cost)`` -- ``idxQ2P[q]`` is the cluster of ``P`` that
        cluster ``q`` of ``Q`` maps to, and ``cost`` is
        :func:`cost_membership` of ``P`` against the permuted ``Q``.
    """
    if P.ndim != 2 or Q.ndim != 2:
        raise ValueError("P and Q must be 2D")
    if P.shape[0] != Q.shape[0]:
        raise ValueError(f"P and Q disagree on N: {P.shape[0]} vs {Q.shape[0]}")
    if P.shape[1] != Q.shape[1]:
        raise ValueError(
            f"align_pair needs equal K, got {P.shape[1]} and {Q.shape[1]}. "
            "Clumppling's different-K alignment is an integer program and "
            "belongs to alignment-across-K, which this port does not cover.")

    D = cdist(Q.T, P.T, metric="sqeuclidean") / Q.shape[0]
    _rows, cols = linear_sum_assignment(D)
    idxQ2P = list(cols)

    aligned = np.zeros_like(P)                    # core.alignQ_wrtP(merge=True)
    for q_idx, p_idx in enumerate(idxQ2P):
        aligned[:, p_idx] += Q[:, q_idx]
    return idxQ2P, cost_membership(P, aligned)


def align_within_k(Q_list):
    """Every pair aligned and scored -- ``core.align_within_k``.

    Returns ``(cost_mat, alignments)``: the (R, R) symmetric cost matrix
    ``detectMode.construct_cost_mat`` would build, and ``{(i, j): idxQ2P}``
    mapping j's clusters onto i's for ``i < j``.
    """
    n = len(Q_list)
    cost_mat = np.zeros((n, n))
    alignments = {}
    for i in range(n - 1):
        for j in range(i + 1, n):
            idxQ2P, cost = align_pair(Q_list[i], Q_list[j])
            alignments[(i, j)] = idxQ2P
            cost_mat[i, j] = cost_mat[j, i] = cost

    # detectMode.construct_cost_mat's validity checks, kept verbatim
    if not np.all(np.isfinite(cost_mat)):
        raise ValueError("Cost matrix contains non-finite values (NaN or Inf).")
    if np.any(cost_mat < 0):
        raise ValueError("Cost matrix contains negative values.")
    if np.any(cost_mat > 1):
        raise ValueError("Cost matrix contains values above 1.")
    return cost_mat, alignments


# --------------------------------------------------------------------------
# step 3: costs -> a complete weighted graph   (detectMode/utils.py)
# --------------------------------------------------------------------------
def cost_to_adj(cost_mat, norm=True):
    """``detectMode.cost_to_adj``: eq. 13, with self-loops set to 1."""
    cost_mat = np.asarray(cost_mat, dtype=np.float64)
    if norm:
        mask = ~np.eye(cost_mat.shape[0], dtype=bool)
        cost_min = np.min(cost_mat[mask])
        cost_max = np.max(cost_mat[mask])
        adj_mat = 1 - (cost_mat - cost_min) / (cost_max - cost_min)
    else:
        adj_mat = 1 - cost_mat
    np.fill_diagonal(adj_mat, 1)
    return adj_mat


# --------------------------------------------------------------------------
# step 4: is there community structure at all?   (detectMode/utils.py)
# --------------------------------------------------------------------------
def _standardize_matrix(W):
    """``detectMode.standardize_matrix``: z-score the off-diagonal, zero the rest."""
    non_diag_idx = np.where(~np.eye(W.shape[0], dtype=bool))
    non_diag_w = W[non_diag_idx]
    out = np.zeros(W.shape)
    out[non_diag_idx] = (non_diag_w - non_diag_w.mean()) / non_diag_w.std()
    return out


def _normalize_matrix(W):
    """``detectMode.normalize_matrix``: divide by sqrt(n)."""
    return W / np.sqrt(W.shape[0])


def _exponentiate_matrix(W, t):
    """``detectMode.exponentiate_matrix``: ``exp(t * W)`` off the diagonal."""
    non_diag_idx = np.where(~np.eye(W.shape[0], dtype=bool))
    out = np.zeros(W.shape)
    out[non_diag_idx] = np.exp(W[non_diag_idx] * t)
    return out


def test_comm_struc(W, alpha=0.01):
    """
    ``detectMode.test_comm_struc``: Tracy-Widom test for community structure.

    A graph with no community structure has its extreme eigenvalues, after
    standardising and scaling by ``1/sqrt(n)``, inside the Tracy-Widom
    (beta = 1) interval. Four statistics are checked -- the largest and smallest
    eigenvalue of the standardised adjacency ``T`` and of its exponentiated form
    ``Te`` (``t = 1/2``) -- against the ``alpha/4`` interval, a Bonferroni split.
    Structure is declared when **any** of the four falls outside.

    Returns True if the graph has community structure worth partitioning.
    """
    from TracyWidom import TracyWidom

    W = np.asarray(W, dtype=np.float64)
    if W.ndim != 2 or W.shape[0] != W.shape[1]:
        raise ValueError("Input matrix W must be square (2D NumPy array).")

    T = _normalize_matrix(_standardize_matrix(W))
    Te = _normalize_matrix(_standardize_matrix(_exponentiate_matrix(W, t=1 / 2)))

    x = np.linspace(-10, 10, 1001)
    cdf = TracyWidom(beta=1).cdf(x)
    CI_max = x[np.where(cdf > (1 - alpha / 4))[0][0]]
    CI_min = x[np.where(cdf < alpha / 4)[0][-1]]

    def extremes(M):
        ev = np.linalg.eig(M)[0]
        ev = ev.real if np.iscomplexobj(ev) else ev   # symmetric input -> real
        return ev.max(), ev.min()

    eig_T_max, eig_T_min = extremes(T)
    eig_Te_max, eig_Te_min = extremes(Te)

    s = (int(eig_T_max < CI_max) + int(eig_T_min > CI_min)
         + int(eig_Te_max < CI_max) + int(eig_Te_min > CI_min))
    return s != 4


# --------------------------------------------------------------------------
# step 5: Louvain   (core.cd_default, core.detect_communities)
# --------------------------------------------------------------------------
def cd_default(adj_mat, res=1.0, random_state=0):
    """``core.cd_default`` for ``method="louvain"``.

    ``cdlib.algorithms.louvain(G, resolution=res)`` is a wrapper around
    ``community_louvain.best_partition(g, weight="weight", resolution=res,
    randomize=None)``; this calls that directly. Self-loops are removed first,
    as upstream does.
    """
    import community.community_louvain as community_louvain
    import networkx as nx

    G = nx.from_numpy_array(np.asarray(adj_mat, dtype=np.float64))
    G.remove_edges_from(nx.selfloop_edges(G))
    part = community_louvain.best_partition(
        G, weight="weight", resolution=float(res), random_state=random_state)
    return [part[i] for i in range(adj_mat.shape[0])]


def detect_communities(cost_mat, test_comm=True, res=1.0,
                       min_threshold=1e-4, max_threshold=1e-2, random_state=0,
                       report=None):
    """
    ``core.detect_communities`` -- the whole decision, including its shortcuts.

    Before any community detection, Clumppling settles the easy cases outright:
    one replicate is one mode; two replicates are one mode or two by
    ``min_threshold`` alone; if the *largest* cost is below ``min_threshold``
    every replicate agrees and there is one mode; if the *smallest* is above
    ``max_threshold`` none agree and every replicate is its own. Only in between
    does it build the graph, test it for structure, and run Louvain.

    Args:
        report: optional dict, filled in with ``route`` (which branch decided)
            and ``has_comm_struc`` (the Tracy-Widom verdict, or None if the
            test was skipped or never reached). The Tracy-Widom test is
            asymptotic and has little power at small R -- on this workflow's
            1kg_p3 example, R = 8 replicates per K, it reports "no structure"
            at every K even where the cost matrix is a perfect two-block matrix,
            and only starts rejecting at R >= 16. Knowing which branch produced
            a single mode is therefore not a detail.

    Returns a list of community labels, renumbered by decreasing size with ties
    broken by first appearance.
    """
    rep = {} if report is None else report
    rep.setdefault("has_comm_struc", None)
    cost_mat = np.asarray(cost_mat, dtype=np.float64)
    n_nodes = cost_mat.shape[0]
    if n_nodes == 0:
        raise ValueError("Cost matrix is empty.")
    if n_nodes == 1:
        rep["route"] = "single replicate"
        return [0]

    mask = ~np.eye(n_nodes, dtype=bool)
    cost_min = float(np.min(cost_mat[mask]))
    cost_max = float(np.max(cost_mat[mask]))

    if n_nodes == 2:
        rep["route"] = "two replicates, min_threshold"
        return [0, 0] if cost_mat[0, 1] < min_threshold else [0, 1]
    if cost_max < min_threshold:
        rep["route"] = "all costs below min_threshold"
        return [0] * n_nodes
    if cost_min > max_threshold:
        rep["route"] = "all costs above max_threshold"
        return list(range(n_nodes))

    adj_mat = cost_to_adj(cost_mat, norm=True)
    if test_comm:
        rep["has_comm_struc"] = test_comm_struc(adj_mat, alpha=0.01)
        if not rep["has_comm_struc"]:
            rep["route"] = "Tracy-Widom test found no community structure"
            return [0] * n_nodes

    rep["route"] = f"Louvain at resolution {res}"
    communities = cd_default(adj_mat, res=res, random_state=random_state)
    if not communities:
        return list(range(n_nodes))

    counts = Counter(communities)
    order = sorted(counts.keys(), key=lambda x: (-counts[x], communities.index(x)))
    mapping = {old: new for new, old in enumerate(order)}
    return [mapping[c] for c in communities]


# --------------------------------------------------------------------------
# step 6: summarising a mode   (core.find_repr_modes, utils.C2Gprime)
# --------------------------------------------------------------------------
def find_repr_modes(modes, cost_mat):
    """``core.find_repr_modes``: per mode, the member with the lowest total cost
    to the rest of its mode."""
    cost_mat = np.asarray(cost_mat)
    out = []
    for members in modes:
        if len(members) == 1:
            out.append(members[0])
            continue
        idx = np.asarray(members)
        sub = cost_mat[idx, :][:, idx]
        out.append(members[int(np.argmin(sub.sum(axis=0)))])
    return out


def C2Gprime(C):
    """``utils.C2Gprime``: ``G' = 1 - sqrt(cost)``, Clumppling's similarity."""
    return 1 - np.sqrt(np.asarray(C, dtype=np.float64))


def _avg_tril(A):
    """``utils.avg_tril``: mean of the strict lower triangle."""
    A = np.asarray(A, dtype=np.float64)
    iu = np.tril_indices(A.shape[0], k=-1)
    return float(A[iu].mean()) if iu[0].size else 0.0


# --------------------------------------------------------------------------
# the one call this workflow uses
# --------------------------------------------------------------------------
def _prepare(runs, samples=None):
    """``{run_id: usage}`` -> ``(ids, [row-normalised (N, K) arrays], samples)``.

    Deliberately local rather than reusing :func:`~stripesankey.modes._align_runs`,
    which does the same job: this module has to be loadable **on its own**, with
    nothing but numpy/scipy/pandas, so that
    ``scripts/validate_clumppling_port.py`` can import it by file path into an
    environment that has the real Clumppling but not this package's other
    dependencies. A port whose fidelity cannot be checked outside its own
    package is a port on trust.
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
            if samples is None:
                samples = list(H.index.map(str))
            missing = set(samples) - set(H.index.map(str))
            if missing:
                raise ValueError(f"run {rid!r} is missing {len(missing)} sample(s)")
            H = H.loc[list(samples)]
        arr = np.asarray(H, dtype=np.float64)
        if samples is not None and arr.shape[0] != len(samples):
            raise ValueError(f"run {rid!r} has {arr.shape[0]} rows, "
                             f"expected {len(samples)}")
        arr = np.clip(arr, 0, None)
        P_list.append(arr / arr.sum(axis=1, keepdims=True))
    if samples is None:
        samples = [str(i) for i in range(P_list[0].shape[0])]
    return ids, P_list, list(samples)



def clumppling_modes(runs, samples=None, *, res=1.0, test_comm=True,
                     min_threshold=1e-4, max_threshold=1e-2, random_state=0):
    """
    Clumppling's mode decomposition of a set of replicate runs at one K.

    Args:
        runs: ``{run_id: (N, K) usage}`` -- DataFrames (index = sample id) or
            arrays on a common sample order. Row-normalised internally.
        samples: common sample order to reindex DataFrames onto.
        res: Louvain resolution (Clumppling's ``--cd_res``, default 1.0).
        test_comm: run the Tracy-Widom structure test first (``--test_comm``).
        min_threshold, max_threshold: Clumppling's ``--comm_min`` / ``--comm_max``
            shortcuts; see :func:`detect_communities`.
        random_state: seeds Louvain. ``None`` reproduces Clumppling's own
            unseeded default, which is not reproducible run to run.

    Returns:
        dict with

        * ``modes`` -- Series, run id -> mode id (0 = largest mode)
        * ``cost`` -- (R, R) DataFrame of aligned pairwise costs
        * ``gprime`` -- (R, R) DataFrame of ``1 - sqrt(cost)``, the similarity
        * ``representatives`` -- ``{mode id: run id}``
        * ``mode_stats`` -- the table Clumppling writes to ``mode_stats.txt``:
          ``Mode``, ``Representative``, ``Size``, ``Cost``, ``Performance``
        * ``avg_Q`` -- ``{mode id: (N, K) DataFrame}``, each mode's members
          aligned onto its representative and averaged (eq. 14)
        * ``report`` -- ``{"route", "has_comm_struc"}``, which branch of
          :func:`detect_communities` decided and what the Tracy-Widom test said
    """
    ids, P_list, samples = _prepare(runs, samples)
    widths = {P.shape[1] for P in P_list}
    if len(widths) != 1:
        raise ValueError(f"Clumppling mode detection is within one K; got "
                         f"K = {sorted(widths)}")

    cost_mat, alignments = align_within_k(P_list)
    report = {}
    communities = detect_communities(
        cost_mat, test_comm=test_comm, res=res, min_threshold=min_threshold,
        max_threshold=max_threshold, random_state=random_state, report=report)
    modes = [[j for j, c in enumerate(communities) if c == i]
             for i in range(max(communities) + 1)]
    reps = find_repr_modes(modes, cost_mat)

    stats, avg_Q = [], {}
    for m, (members, i_ref) in enumerate(zip(modes, reps)):
        sub = cost_mat[np.ix_(members, members)]
        stats.append({
            "Mode": f"M{m}",
            "Representative": ids[i_ref],
            "Size": len(members),
            "Cost": 0.0 if len(members) == 1 else _avg_tril(sub),
            "Performance": 1.0 if len(members) == 1 else _avg_tril(C2Gprime(sub)),
        })
        ref = P_list[i_ref]
        acc = np.zeros_like(ref)
        for r in members:
            if r == i_ref:
                acc += ref
            else:
                idxQ2P, _ = align_pair(ref, P_list[r])
                aligned = np.zeros_like(ref)
                for q_idx, p_idx in enumerate(idxQ2P):
                    aligned[:, p_idx] += P_list[r][:, q_idx]
                acc += aligned
        avg_Q[m] = pd.DataFrame(acc / len(members), index=samples,
                                columns=[f"MC{t}" for t in range(ref.shape[1])])

    return {
        "modes": pd.Series(communities, index=ids, name="mode"),
        "cost": pd.DataFrame(cost_mat, index=ids, columns=ids),
        "gprime": pd.DataFrame(C2Gprime(cost_mat), index=ids, columns=ids),
        "representatives": {m: ids[i] for m, i in enumerate(reps)},
        "mode_stats": pd.DataFrame(stats).set_index("Mode"),
        "avg_Q": avg_Q,
        "report": report,
    }
