"""
Multiresolution consensus clustering of samples across the whole K range.

This is the k-agnostic sample clustering behind the StripeSankey cluster-lineage
colouring. It replaces the earlier consensus-JSD route (still in
``clustering.cluster_samples``), which averaged per-k Jensen-Shannon distance
matrices with equal weights.

**The problem with averaging distances across k.** At small K every sample looks
similar to every other -- with two MCs, two random samples share their dominant
MC about half the time -- while at large K they look uniformly far apart. So a
plain average across K is dominated by whichever end of the range happens to be
included, and the answer moves when the K range moves.

**The fix** (after Jeub, Sporns & Fortunato, *Multiresolution Consensus
Clustering in Networks*, Sci Rep 2018): before averaging, subtract the
co-membership expected *by chance* at that K, which is a closed form, and
rescale so every K contributes on the same scale::

    P_k   = theta at K = k, each sample's row normalised to a distribution
    B_k   = P_k @ P_k.T          soft co-membership: P(i and j draw the same MC)
    e_k   = sum_t mean_i(P_k[i,t])**2      the same probability under the null
                                           "every sample has the average profile"
    Q_k   = (B_k - e_k) / (1 - e_k)        chance-corrected co-membership
    Q     = sum_k (1 - e_k) Q_k / sum_k (1 - e_k)

``Q_k`` is the same ``(observed - expected) / (max - expected)`` statistic as
Cohen's kappa and the adjusted Rand index, applied per pair of samples instead
of per pair of partitions. ``Q`` is a **signed affinity**: positive means the
pair is together more often than chance, negative means less.

The ``1 - e_k`` weight is not cosmetic. ``Q_k`` applies a gain of
``1 / (1 - e_k)`` to ``B_k``, which is larger at small k (2.10 at k=2 against
1.21 at k=10 on a 344-sample run), so an unweighted mean would silently give the
coarsest model nearly twice the pull of the finest. Weighting by ``1 - e_k``
cancels that factor exactly.

**Extracting labels.** ``Q`` is signed, so it is not a distance and must not be
handed to a metric clusterer. It is partitioned as a dense signed graph under a
Constant Potts objective::

    maximise  sum_communities sum_{i<j in the same community} (Q[i,j] - tau)

Grouping a pair earns ``Q[i,j]`` and costs ``tau``; keep them together when that
is net positive. **No cluster count is needed**: a cluster of size n contains
n(n-1)/2 pairs, so growing it eventually pulls in negative entries, and the
negative half of ``Q`` is the brake. ``tau = 0`` is meaningful precisely because
of the chance correction -- it reads "group samples that are above chance".

The objective is optimised with ``leidenalg``, whose refinement phase escapes
local optima a plain Louvain sweep gets stuck in.
"""
import warnings

import igraph as ig
import leidenalg as la
import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
from scipy.spatial.distance import squareform


# --------------------------------------------------------------------------
# consensus affinity
# --------------------------------------------------------------------------
def _row_normalise(H, k):
    """Each sample's usage vector -> a distribution summing to 1."""
    H = np.asarray(H, dtype=np.float64)
    if (H < 0).any():
        H = np.clip(H, 0, None)
    s = H.sum(axis=1, keepdims=True)
    zero = (s[:, 0] == 0)
    if zero.any():
        warnings.warn(f"{int(zero.sum())} sample(s) have all-zero usage at k={k}; "
                      "using a uniform distribution for them.")
        H = H.copy()
        H[zero] = 1.0 / H.shape[1]
        s = H.sum(axis=1, keepdims=True)
    return H / s


def _per_k_terms(usage_matrices):
    """Yield ``(k, P_k, B_k, e_k, Q_k)`` for each k, in ascending k order."""
    ks = sorted(usage_matrices)
    n_rows = {usage_matrices[k].shape[0] for k in ks}
    if len(n_rows) != 1:
        raise ValueError(f"usage matrices disagree on N: {sorted(n_rows)}")
    for k in ks:
        P = _row_normalise(usage_matrices[k], k)
        B = P @ P.T
        m = P.mean(axis=0)
        e = float((m ** 2).sum())
        if e >= 1.0:                       # degenerate: a single MC carries everything
            raise ValueError(f"e_k = {e:.4f} >= 1 at k={k}; cannot rescale.")
        Q = (B - e) / (1.0 - e)
        yield k, P, B, e, Q


def _off_diag_sd(Q):
    """Spread of the off-diagonal entries of one ``Q_k``."""
    iu = np.triu_indices(Q.shape[0], k=1)
    return float(Q[iu].std())


def consensus_affinity(usage_matrices):
    """
    Signed consensus affinity ``Q`` (N, N) from ``{k: H_k}``.

    Args:
        usage_matrices: ``{k: ndarray (N, k)}`` -- sample x MC usage, one entry
            per K, non-negative, with the same N rows in the same order for
            every K. DataFrames work too, e.g. ``load_W(base)``.

    Returns:
        ``Q`` (N, N) float64, symmetric, zero diagonal, signed. Positive =
        together more than chance, negative = less than chance. Given
        DataFrames, a DataFrame indexed by sample on both axes, which
        :func:`affinity_heatmap` takes as it is.

    The diagonal is zeroed deliberately: ``B_k[i,i]`` is sample i's own MC
    purity (the Simpson concentration of its profile), which varies for reasons
    unrelated to clustering and would otherwise dominate any colour scale.
    """
    acc = None
    wsum = 0.0
    for _k, _P, _B, e, Q in _per_k_terms(usage_matrices):
        w = 1.0 - e
        acc = (Q * w) if acc is None else (acc + Q * w)
        wsum += w
    Q = acc / wsum

    Q = (Q + Q.T) / 2.0                    # kill float asymmetry
    np.fill_diagonal(Q, 0.0)
    first = next(iter(usage_matrices.values()))
    if isinstance(first, pd.DataFrame):
        return pd.DataFrame(Q, index=first.index, columns=first.index)
    return Q


def consensus_diagnostics(usage_matrices):
    """
    Per-k sanity table for the consensus affinity.

    ``e_k`` should fall as K grows -- that is the bias being removed -- and stay
    at or above ``1/k``, with equality only when the MCs are perfectly balanced.
    ``mean_Q_k`` should sit at ~0 for every K: the average pair is at chance,
    which is what makes ``resolution=0`` meaningful downstream.

    ``diag_Q_k`` is **not** ~1. It tracks ``mean_purity``, since for soft usage
    ``B_k[i,i] = sum_t P[i,t]**2`` is a concentration, reaching 1 only for a
    one-hot profile. What must hold is ``diag_Q_k <= 1``.

    Returns:
        DataFrame indexed by k.
    """
    rows = []
    for k, P, B, e, Q in _per_k_terms(usage_matrices):
        off = ~np.eye(B.shape[0], dtype=bool)
        rows.append({
            'k': k,
            'e_k': e,
            '1/k': 1.0 / k,
            'mean_B_k': float(B[off].mean()),
            'mean_Q_k': float(Q[off].mean()),
            'min_Q_k': float(Q[off].min()),
            'max_Q_k': float(Q[off].max()),
            'sd_Q_k': _off_diag_sd(Q),
            'diag_Q_k': float(np.diag(Q).mean()),
            'mean_purity': float((P ** 2).sum(axis=1).mean()),
            'avg_weight': 1.0 / (1.0 - e),
        })
    return pd.DataFrame(rows).set_index('k')


# --------------------------------------------------------------------------
# clustering: signed Constant Potts
# --------------------------------------------------------------------------
def cpm_objective(Q, labels, resolution=0.0):
    """Total within-community ``sum(Q[i,j] - tau)`` over unordered pairs."""
    labels = np.asarray(labels)
    total = 0.0
    for c in np.unique(labels):
        idx = np.flatnonzero(labels == c)
        if idx.size < 2:
            continue
        sub = Q[np.ix_(idx, idx)]
        n = idx.size
        total += (sub.sum() - np.trace(sub)) / 2.0 - resolution * n * (n - 1) / 2.0
    return float(total)


def _leiden_signed_cpm(Q, resolution, random_state, n_iterations=2):
    """Signed Constant Potts via leidenalg, as a two-layer multiplex.

    leidenalg will not take negative edge weights, so the standard signed
    formulation is used: split ``Q`` into its positive and negative parts and
    optimise them as two layers with weights ``+1`` and ``-1``. Resolution goes
    on the positive layer only -- putting it on both would subtract tau twice.
    """
    P = np.clip(Q, 0, None)
    N = np.clip(-Q, 0, None)
    np.fill_diagonal(P, 0.0)
    np.fill_diagonal(N, 0.0)
    gp = ig.Graph.Weighted_Adjacency(P.tolist(), mode="undirected",
                                     attr="weight", loops=False)
    gn = ig.Graph.Weighted_Adjacency(N.tolist(), mode="undirected",
                                     attr="weight", loops=False)
    part_p = la.CPMVertexPartition(gp, weights="weight",
                                   resolution_parameter=float(resolution))
    part_n = la.CPMVertexPartition(gn, weights="weight", resolution_parameter=0.0)
    opt = la.Optimiser()
    opt.set_rng_seed(int(random_state))
    opt.optimise_partition_multiplex([part_p, part_n], layer_weights=[1, -1],
                                     n_iterations=n_iterations)
    return np.asarray(part_p.membership)


def cluster_from_affinity(Q, resolution=0.0, noise_threshold=0.0,
                          random_state=0, verbose=False):
    """
    Cluster a signed affinity matrix with a Constant Potts objective.

    No cluster count is required: ``resolution`` (tau) sets how much better than
    chance a pair must be to be worth grouping. ``0.0`` means "better than
    chance", a real threshold only because ``Q`` was debiased.

    Args:
        Q: (N, N) signed affinity from :func:`consensus_affinity`.
        resolution: tau. Higher -> more, smaller clusters. Default 0.0.
        noise_threshold: a sample whose mean affinity to the rest of its own
            cluster is <= this becomes ``-1``. ``None`` disables noise labelling.
        random_state: seeds the optimiser, which is order-dependent.
        verbose: print the number of communities and the objective reached.

    Returns:
        ``labels`` (N,) int, ``-1`` = noise, others contiguous from 0 and sorted
        by descending cluster size.
    """
    Q = np.asarray(Q, dtype=np.float64)
    if Q.ndim != 2 or Q.shape[0] != Q.shape[1]:
        raise ValueError(f"Q must be square, got {Q.shape}")
    n = Q.shape[0]

    labels = _leiden_signed_cpm(Q, resolution, random_state)
    if verbose:
        print(f"  leiden: {len(np.unique(labels))} communities, "
              f"objective {cpm_objective(Q, labels, resolution):.3f}")
    if noise_threshold is not None:
        labels = _mark_noise(Q, labels, noise_threshold)
    labels = _renumber_by_size(labels)
    _warn_degenerate(labels, n)
    return labels


def _mark_noise(Q, labels, threshold):
    """Weak members of their own cluster -> -1."""
    labels = np.asarray(labels).copy()
    for c in np.unique(labels):
        idx = np.flatnonzero(labels == c)
        if idx.size == 1:                 # a singleton has no cluster to belong to
            labels[idx] = -1
            continue
        sub = Q[np.ix_(idx, idx)]
        s = (sub.sum(axis=1) - np.diag(sub)) / (idx.size - 1)
        labels[idx[s <= threshold]] = -1
    return labels


def _renumber_by_size(labels):
    """Contiguous 0..N-1 ordered by descending size; noise stays -1.

    Matches ``clustering._renumber``'s convention so these labels are drop-in
    for the StripeSankey widget.
    """
    labels = np.asarray(labels).astype(int)
    vals, counts = np.unique(labels[labels != -1], return_counts=True)
    order = vals[np.argsort(-counts, kind='stable')]
    remap = {v: i for i, v in enumerate(order)}
    return np.array([remap.get(v, -1) for v in labels], dtype=int)


def _warn_degenerate(labels, n):
    """A single giant cluster or all singletons means tau is wrong."""
    real = labels[labels != -1]
    n_cl = len(np.unique(real))
    if n_cl == 0:
        warnings.warn("every sample was labelled noise -- lower noise_threshold "
                      "or resolution.")
    elif n_cl == 1 and real.size > 0.9 * n:
        warnings.warn("one giant cluster holds >90% of samples -- raise resolution.")
    elif n_cl > 0 and real.size / n_cl < 2:
        warnings.warn(f"{n_cl} clusters averaging <2 samples -- lower resolution.")


# --------------------------------------------------------------------------
# coarsening Q to cluster level, and colouring FROM it
# --------------------------------------------------------------------------
# The StripeSankey's own cluster colours (`__clusterLineage` in
# stripesankey.py, ported to Python as `volume_stripesankey.cluster_lineage`)
# come from an unrelated, ad-hoc cosine distance over concatenated per-K
# usage vectors, with none of `consensus_affinity`'s chance-correction and no
# guarantee of agreeing with the statistic that actually produced the
# clusters. The functions below answer "which clusters are close to which"
# using the SAME Q Leiden already partitioned: block-average it by cluster
# (PAGA-style, Wolf et al. 2019) to get a small (C, C) affinity, then either
# run an ordinary hierarchical clustering on it or paint an OKLCH hue ramp
# along its leaf order -- a palette that can be handed to
# `StripeSankeyInline`/`k_evaluation` via `cluster_colors=` so the ribbons
# agree with it too, instead of inventing a third distance.

def coarse_affinity(Q, labels):
    """Block-average a sample-level affinity ``Q`` by cluster.

    Off-diagonal ``[a, b]`` = mean ``Q[i, j]`` over ``i`` in cluster a, ``j``
    in cluster b (a != b) -- the same signed, chance-corrected quantity,
    averaged over a block instead of a single pair. Diagonal ``[a, a]`` =
    mean ``Q[i, j]`` over ``i != j`` both in a: the cluster's own cohesion,
    on the identical scale as the off-diagonal entries. Noise (``-1``) is
    dropped.

    Args:
        Q: (N, N) signed affinity from :func:`consensus_affinity`.
        labels: (N,) consensus cluster ids, ``-1`` = noise.

    Returns:
        (C, C) DataFrame indexed and columned by the sorted cluster ids.
    """
    Q = np.asarray(Q)
    labels = np.asarray(labels)
    ids = sorted(int(c) for c in set(labels.tolist()) if c != -1)
    idx = {c: np.flatnonzero(labels == c) for c in ids}

    C = len(ids)
    out = np.zeros((C, C))
    for a_i, a in enumerate(ids):
        for b_i, b in enumerate(ids):
            if a_i > b_i:
                continue
            ia, ib = idx[a], idx[b]
            if a == b:
                sub = Q[np.ix_(ia, ia)]
                n = ia.size
                val = (sub.sum() - np.trace(sub)) / max(n * (n - 1), 1)
            else:
                val = Q[np.ix_(ia, ib)].mean()
            out[a_i, b_i] = out[b_i, a_i] = val
    return pd.DataFrame(out, index=ids, columns=ids)


def coarse_sizes(labels):
    """Cluster sizes, indexed the same way as :func:`coarse_affinity`."""
    labels = np.asarray(labels)
    ids = sorted(int(c) for c in set(labels.tolist()) if c != -1)
    return pd.Series({c: int((labels == c).sum()) for c in ids}, name="n")


def coarse_distance(Cq):
    """Distance = ``Cq.max() - Cq`` (off-diagonal), higher affinity ->
    smaller distance. The one continuous, symmetric distance both
    :func:`coarse_linkage` (for its dendrogram) and :func:`lineage_palette`
    (for its hue spacing) build on, so the tree and the colours painted onto
    it never disagree about what "close" means.
    """
    vals = Cq.to_numpy().copy()
    np.fill_diagonal(vals, np.nan)
    dmax = np.nanmax(vals)
    D = dmax - Cq.to_numpy()
    np.fill_diagonal(D, 0.0)
    D = (D + D.T) / 2
    return pd.DataFrame(D, index=Cq.index, columns=Cq.columns)


def coarse_linkage(Cq, method="average"):
    """Average-linkage dendrogram on the SAME chance-corrected ``Cq``.

    Distance = :func:`coarse_distance`, so the hierarchy comes from
    literally the object Leiden partitioned.
    """
    D = coarse_distance(Cq)
    return sch.linkage(squareform(D.to_numpy(), checks=False), method=method)


def leaf_plot_order(Z, leaf_ids):
    """The LEFT-TO-RIGHT cluster order scipy's own dendrogram layout picks
    for ``Z``, exposed standalone so :func:`lineage_palette` can be built
    without drawing anything.
    """
    n = len(leaf_ids)
    dn = sch.dendrogram(Z, no_plot=True, labels=[str(i) for i in range(n)])
    return [leaf_ids[int(s)] for s in dn["ivl"]]


def renumber_by_tree_position(Q, labels):
    """Relabel clusters by their LEFT-TO-RIGHT position in their own
    coherent tree, instead of :func:`cluster_from_affinity`'s default
    (descending size).

    Two clusters that are neighbours in :func:`coarse_linkage`'s dendrogram
    -- i.e. that Q itself says are the most alike -- get adjacent ids after
    this (leaf 0 of the tree becomes cluster 0, leaf 1 becomes cluster 1,
    ...), so the id itself carries a little of the relationship the
    dendrogram shows, instead of being an arbitrary size-rank accident. This
    is a relabelling only: which samples share a cluster is unchanged, only
    the integer naming it is.

    Args:
        Q: (N, N) signed affinity from :func:`consensus_affinity` -- the
            SAME Q ``labels`` was cut from.
        labels: (N,) cluster ids, ``-1`` = noise.

    Returns:
        (N,) int array, same shape as ``labels``, ``-1`` preserved.
    """
    labels = np.asarray(labels)
    ids = sorted(int(c) for c in set(labels.tolist()) if c != -1)
    if len(ids) <= 1:
        return labels.copy()      # nothing to order -- coarse_linkage needs >= 2
    Cq = coarse_affinity(Q, labels)
    Z = coarse_linkage(Cq)
    order = leaf_plot_order(Z, list(Cq.index))
    remap = {old: new for new, old in enumerate(order)}
    return np.array([remap.get(int(c), -1) for c in labels])


def oklch_to_hex(oklch):
    """``"oklch(L C H)"`` -> ``"#rrggbb"``.

    Bjorn Ottosson's OKLab <-> linear-sRGB matrices (the same ones d3-color /
    CSS Color 4 use), so this renders as the same colour a browser paints for
    that same CSS string. Needed because :func:`lineage_palette`'s output
    feeds matplotlib (`scripts/affinity_network.py`) as well as SVG `fill`,
    and only the latter understands `oklch()` natively -- converting once
    here, rather than leaving each consumer to interpret the string its own
    way, is what keeps the StripeSankey, its dendrogram legend and the
    affinity-network plot pixel-identical instead of merely "the same idea".
    """
    import math

    l_str, c_str, h_str = oklch.removeprefix("oklch(").removesuffix(")").split()
    L, C, H = float(l_str), float(c_str), float(h_str)
    hr = math.radians(H)
    a, b = C * math.cos(hr), C * math.sin(hr)

    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3

    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def gamma(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    r, g, bl = (max(0.0, min(1.0, gamma(c))) for c in (r, g, bl))
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(bl * 255))


def lineage_palette(D, leaf_order, hue0=25.0, arc=230.0, L=0.630, C=0.160,
                    spread=0.35):
    """OKLCH hue-lineage palette from a leaf order + pairwise distance.

    Same recipe as the StripeSankey's own colour ramp -- walk the leaf
    order, accumulate the ACTUAL distance between neighbours, spread hue
    proportionally to how far apart the tree really put them (``hue0=25,
    arc=230`` is that widget's own red-to-blue arc, chosen there to avoid
    the hue wrapping back around to red) -- but fed `D` from
    :func:`coarse_distance` instead of an ad-hoc, non-chance-corrected
    cosine distance.

    ``spread`` is a deliberate departure from the StripeSankey's own default
    (0.0, pure distance). Chance-corrected Cq can put two clusters almost
    exactly the same distance apart, and pure-distance hue spacing then
    assigns them the SAME colour -- a real bug for a legend, not a
    stylistic quibble, and the reason two clusters Leiden treated as
    genuinely distinct communities must not become visually
    indistinguishable. ``spread`` blends in the plain rank (evenly spaced):
    ``pos = spread*rank + (1-spread)*distance``. ``0.35`` separates every
    leaf on both the HRD and 1kg_p3 runs this was checked against while
    still weighting real distance over rank 2:1.

    Args:
        D: (C, C) DataFrame from :func:`coarse_distance`.
        leaf_order: cluster ids in LEFT-TO-RIGHT order, e.g. from
            :func:`leaf_plot_order`.

    Returns:
        ``{cluster_id: "oklch(L C H)"}``.
    """
    n = len(leaf_order)
    if n <= 1:
        return {c: f"oklch({L:.3f} {C:.3f} {hue0:.1f})" for c in leaf_order}
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + float(D.loc[leaf_order[i - 1], leaf_order[i]]))
    span = cum[-1] or 1.0
    last = n - 1
    out = {}
    for i, cid in enumerate(leaf_order):
        td = cum[i] / span
        tr = i / last if last else 0.5
        pos = spread * tr + (1 - spread) * td
        out[cid] = f"oklch({L:.3f} {C:.3f} {hue0 + pos * arc:.1f})"
    return out


def coherent_cluster_palette(Q, labels, *, method="average", **palette_kwargs):
    """One call: ``Q`` + cluster labels -> a hex palette, hand-off ready for
    ``StripeSankeyInline``/``k_evaluation``'s ``cluster_colors=``, a
    ``ClusterDendrogram``'s ``colors=``, or a matplotlib plot -- the same
    hex string in all three, since it is computed once here.

    Runs the whole coarsen-and-colour recipe (:func:`coarse_affinity` ->
    :func:`coarse_linkage` -> :func:`leaf_plot_order` -> :func:`coarse_distance`
    -> :func:`lineage_palette` -> :func:`oklch_to_hex`) so call sites that
    only want the end result don't have to repeat those five steps.

    Args:
        Q: (N, N) signed affinity from :func:`consensus_affinity`.
        labels: (N,) consensus cluster ids, ``-1`` = noise.
        method: linkage method for :func:`coarse_linkage`.
        **palette_kwargs: forwarded to :func:`lineage_palette` (``hue0``,
            ``arc``, ``L``, ``C``, ``spread``).

    Returns:
        ``{cluster_id: "#rrggbb"}``.
    """
    Cq = coarse_affinity(Q, labels)
    Z = coarse_linkage(Cq, method=method)
    order = leaf_plot_order(Z, list(Cq.index))
    oklch = lineage_palette(coarse_distance(Cq), order, **palette_kwargs)
    return {c: oklch_to_hex(h) for c, h in oklch.items()}
