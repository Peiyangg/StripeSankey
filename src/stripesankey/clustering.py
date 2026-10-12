"""
Global (k-agnostic) sample clustering for the StripeSankey cluster-lineage view.

Both routes produce the same thing: one label per sample (``-1`` = noise), the
``sample_to_cluster`` map the widget's ``cluster_prox`` (OKLCH lineage) encoding
needs.

Soft path (sample x MC distributions, i.e. theta)
-------------------------------------------------
:func:`consensus_clusters` -- **the current method.** Multiresolution consensus:
subtract the chance-level co-membership at each K before averaging across K, then
partition the resulting signed affinity under a Constant Potts objective. See
:mod:`~stripesankey.mr_consensus` for the method and why the correction matters.

:func:`cluster_samples` -- **superseded, kept for reference.** The original
consensus Jensen-Shannon route: per-K JSD distance matrices averaged with equal
weights, average linkage, flat cut. Nothing in the workflow calls it any more;
it is retained so old results stay reproducible.

Hard path (an ensemble of hard label columns)
---------------------------------------------
:func:`consensus_hard_labels` -- used by :func:`~stripesankey.hardstripe`.
Default backend is probabilistic consensus clustering (:mod:`~stripesankey.pcc`),
which models the co-association counts as Binomial rather than treating them as
arbitrary distances; ``method="coassociation"`` selects the older PLSCAN /
average-linkage route.
"""
import os
import glob

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon, squareform
import scipy.cluster.hierarchy as sch


def _jsd_distance_matrix(theta):
    """Pairwise Jensen-Shannon distance matrix. `theta`: samples (rows) x MCs."""
    n = theta.shape[0]
    D = np.zeros((n, n))
    with np.errstate(invalid='ignore'):   # jensenshannon sqrt of ~0 -> handled below
        for i in range(n):
            for j in range(i + 1, n):
                d = jensenshannon(theta[i], theta[j])
                if not np.isfinite(d):
                    d = 0.0
                D[i, j] = D[j, i] = d
    return D


def load_theta_by_k(base_directory, k_list=None):
    """
    Load ``MC_Sample_probabilities{k}.csv`` (MC x sample) as theta per k.

    Returns {k: DataFrame(MC x sample)} for every K found (or in ``k_list``).
    """
    mc_dir = os.path.join(base_directory, 'results', 'MC_Sample')
    out = {}
    for path in sorted(glob.glob(os.path.join(mc_dir, 'MC_Sample_probabilities*.csv'))):
        stem = os.path.basename(path)
        digits = ''.join(ch for ch in stem if ch.isdigit())
        if not digits:
            continue
        k = int(digits)
        if k_list is not None and k not in k_list:
            continue
        out[k] = pd.read_csv(path, index_col=0)   # MC x sample
    return out


def _consensus_linkage(theta_by_k, verbose=True):
    """Average per-k JSD matrices into a consensus distance + average linkage."""
    k_values = sorted(theta_by_k.keys())
    samples = theta_by_k[k_values[0]].columns.tolist()
    if verbose:
        print(f"Computing consensus JSD across k={k_values} ...")

    mats = []
    for k in k_values:
        theta = theta_by_k[k].T.values          # samples x MCs
        mats.append(_jsd_distance_matrix(theta))
    consensus = np.mean(mats, axis=0)           # equal weights across k

    linkage = sch.linkage(squareform(consensus, checks=False), method='average')
    if verbose:
        print(f"  consensus distance range "
              f"[{consensus.min():.4f}, {consensus.max():.4f}]; linkage built")
    return consensus, linkage, samples


def _flat_clusters(linkage, n, min_cluster_size, n_clusters, distance_threshold):
    """
    Flat labels (-1 = noise) from the average-linkage tree.

    Uses fast-hdbscan EOM when available; otherwise a scipy cut (by
    ``n_clusters`` or ``distance_threshold``, default = 70% of max merge height),
    then relabels clusters smaller than ``min_cluster_size`` to noise.
    """
    # Faithful path — fast-hdbscan EOM (optional dependency)
    try:
        from fast_hdbscan.cluster_trees import (
            condense_tree, extract_eom_clusters,
            cluster_tree_from_condensed_tree, get_cluster_label_vector,
        )
        ct = condense_tree(linkage, min_cluster_size=min_cluster_size)
        sel = extract_eom_clusters(
            ct, cluster_tree_from_condensed_tree(ct), allow_single_cluster=False)
        labels = get_cluster_label_vector(ct, sel, 0.0, n_samples=n)
        return _renumber(np.asarray(labels))
    except Exception:
        pass  # fall back to scipy

    # scipy cut
    if n_clusters is not None:
        raw = sch.fcluster(linkage, t=n_clusters, criterion='maxclust')
    else:
        if distance_threshold is None:
            distance_threshold = 0.7 * float(linkage[:, 2].max())
        raw = sch.fcluster(linkage, t=distance_threshold, criterion='distance')

    # small clusters -> noise, then renumber 0..N-1
    labels = raw.astype(int).copy()
    vals, counts = np.unique(labels, return_counts=True)
    for v, c in zip(vals, counts):
        if c < min_cluster_size:
            labels[labels == v] = -1
    return _renumber(labels)


def _renumber(labels):
    """Renumber non-noise labels to a contiguous 0..N-1 (noise stays -1)."""
    labels = np.asarray(labels).astype(int)
    uniq = sorted(v for v in set(labels.tolist()) if v != -1)
    remap = {v: i for i, v in enumerate(uniq)}
    return np.array([remap.get(v, -1) for v in labels], dtype=int)


def cluster_samples(base_directory=None, theta_by_k=None, *, k_list=None,
                    min_cluster_size=15, n_clusters=None, distance_threshold=None,
                    verbose=True):
    """
    Global (k-agnostic) consensus JSD clustering of samples.

    .. note::
       **Superseded by** :func:`consensus_clusters`, which corrects the
       co-membership expected by chance at each K before averaging. Averaging
       raw JSD matrices with equal weights lets whichever end of the K range is
       included dominate the answer: at small K every pair looks similar, at
       large K uniformly distant. Nothing in the workflow calls this function
       any more; it is kept so earlier results stay reproducible.

    Provide either ``base_directory`` (reads MC_Sample_probabilities{k}.csv) or a
    ``theta_by_k`` dict {k: DataFrame(MC x sample)}.

    Args:
        base_directory (str, optional): folder training() wrote to.
        theta_by_k (dict, optional): {k: DataFrame(MC x sample)}; overrides disk.
        k_list (list, optional): restrict to these K when reading from disk.
        min_cluster_size (int): clusters smaller than this become noise (-1).
        n_clusters (int, optional): scipy fallback — force this many clusters.
        distance_threshold (float, optional): scipy fallback — cut height.
        verbose (bool): print progress.

    Returns:
        dict: {
          'sample_to_cluster': {sample_id: int label, -1 = noise},
          'samples': [...ordered...],
          'linkage': ndarray (scipy linkage),
          'consensus_distance': ndarray,
          'n_clusters': int, 'n_noise': int,
        }
    """
    if theta_by_k is None:
        if base_directory is None:
            raise ValueError("Provide either base_directory or theta_by_k.")
        theta_by_k = load_theta_by_k(base_directory, k_list=k_list)
    if not theta_by_k:
        raise FileNotFoundError("No MC_Sample_probabilities*.csv found. Run training() first.")

    consensus, linkage, samples = _consensus_linkage(theta_by_k, verbose=verbose)
    labels = _flat_clusters(linkage, len(samples), min_cluster_size,
                            n_clusters, distance_threshold)

    sample_to_cluster = {str(s): int(c) for s, c in zip(samples, labels)}
    n_cl = len(set(int(c) for c in labels if c != -1))
    n_noise = int((labels == -1).sum())
    if verbose:
        print(f"✓ Global clustering: {n_cl} clusters, {n_noise} noise "
              f"({n_noise/len(samples)*100:.0f}%) over {len(samples)} samples")

    return {
        'sample_to_cluster': sample_to_cluster,
        'samples': [str(s) for s in samples],
        'linkage': linkage,
        'consensus_distance': consensus,
        'n_clusters': n_cl,
        'n_noise': n_noise,
    }


# ============================================================================
# Multiresolution consensus -- the current soft-clustering route.
# ============================================================================


def _usage_from_theta(theta_by_k):
    """``{k: DataFrame(MC x sample)}`` -> ``({k: ndarray(sample x MC)}, samples)``.

    The k-agnostic method needs every K to describe the same samples in the same
    row order, so the sample axis of the first K is taken as canonical and every
    other K is reindexed onto it.
    """
    k_values = sorted(theta_by_k)
    samples = [str(s) for s in theta_by_k[k_values[0]].columns]
    usage = {}
    for k in k_values:
        df = theta_by_k[k]
        df = df.rename(columns=lambda c: str(c))
        missing = [s for s in samples if s not in df.columns]
        if missing:
            raise ValueError(
                f"K={k} is missing {len(missing)} sample(s) present at "
                f"K={k_values[0]} (e.g. {missing[:3]}); every K must cover the "
                "same samples.")
        usage[k] = df[samples].T.to_numpy(dtype=float)   # samples x MC
    return usage, samples


def consensus_clusters(base_directory=None, theta_by_k=None, *, k_list=None,
                       resolution=0.0, noise_threshold=0.0, random_state=0,
                       verbose=True):
    """
    Global (k-agnostic) multiresolution consensus clustering of samples.

    The current default. Unlike :func:`cluster_samples` it removes the
    co-membership expected by chance at each K *before* averaging across K, so
    the result does not drift when the K range changes. See
    :mod:`~stripesankey.mr_consensus`.

    Provide either ``base_directory`` (reads MC_Sample_probabilities{k}.csv) or a
    ``theta_by_k`` dict {k: DataFrame(MC x sample)}.

    Args:
        base_directory (str, optional): folder ``training()`` wrote to.
        theta_by_k (dict, optional): {k: DataFrame(MC x sample)}; overrides disk.
        k_list (list, optional): restrict to these K when reading from disk.
        resolution (float): tau, how far above chance a pair must be to be worth
            grouping. ``0.0`` = "above chance", which is a real threshold here
            because the affinity is chance-corrected. Higher -> more, tighter
            clusters. **There is no cluster-count argument**; the count falls out
            of the data.
        noise_threshold (float): a sample whose mean affinity to the rest of its
            own cluster is <= this becomes ``-1``. ``None`` disables it.
        random_state (int): seeds the community-detection optimiser.
        verbose (bool): print a short summary.

    Returns:
        dict: {
          'sample_to_cluster': {sample_id: int label, -1 = noise},
          'samples': [...ordered...],
          'affinity': ndarray (N, N) signed consensus affinity Q,
          'diagnostics': DataFrame, the per-k sanity table,
          'n_clusters': int, 'n_noise': int,
        }

        The ``linkage`` / ``consensus_distance`` keys of :func:`cluster_samples`
        have no analogue here -- this is graph partitioning, not hierarchical
        clustering, so there is no tree. ``affinity`` is the object those two
        are replaced by.
    """
    from . import mr_consensus as _mrc

    if theta_by_k is None:
        if base_directory is None:
            raise ValueError("Provide either base_directory or theta_by_k.")
        theta_by_k = load_theta_by_k(base_directory, k_list=k_list)
    if not theta_by_k:
        raise FileNotFoundError(
            "No MC_Sample_probabilities*.csv found. Run training() first.")
    if len(theta_by_k) < 2:
        raise ValueError(
            f"Multiresolution consensus needs at least 2 values of K, got "
            f"{sorted(theta_by_k)}. Use cluster_samples() for a single K.")

    usage, samples = _usage_from_theta(theta_by_k)
    if verbose:
        print(f"Multiresolution consensus across k={sorted(usage)} "
              f"({len(samples)} samples) ...")

    Q = _mrc.consensus_affinity(usage)
    labels = _mrc.cluster_from_affinity(
        Q, resolution=resolution, noise_threshold=noise_threshold,
        random_state=random_state)
    # Relabel by position in the clusters' own coherent dendrogram (the SAME
    # Q, block-averaged -- see mr_consensus.coarse_linkage /
    # lineage_palette) rather than leaving cluster_from_affinity's
    # descending-size order as final: two clusters Q says are most alike end
    # up with adjacent ids, so the StripeSankey legend, LEfSe's cluster
    # column and every other consumer of these ids inherit that ordering for
    # free, instead of it being a coincidence of size rank.
    labels = _mrc.renumber_by_tree_position(Q, labels)

    n_cl = len(set(int(c) for c in labels if c != -1))
    n_noise = int((np.asarray(labels) == -1).sum())
    if verbose:
        print(f"✓ Global clustering: {n_cl} clusters, {n_noise} noise "
              f"({n_noise / max(len(samples), 1) * 100:.0f}%) over "
              f"{len(samples)} samples")

    return {
        'sample_to_cluster': {s: int(c) for s, c in zip(samples, labels)},
        'samples': samples,
        'affinity': Q,
        'diagnostics': _mrc.consensus_diagnostics(usage),
        'n_clusters': n_cl,
        'n_noise': n_noise,
    }


# ============================================================================
# Hard-clustering consensus (for the standalone hard-label StripeSankey).
#
# The soft path above needs a per-k probability distribution (theta) to build a
# JSD distance. HARD clustering labels have no distribution -- each sample is
# just an integer/label per column -- so JSD does not apply. The ensemble
# equivalent for hard partitions is the CO-ASSOCIATION (a.k.a. consensus)
# matrix: M[i,j] = fraction of the label columns in which samples i and j land
# in the same cluster; distance = 1 - M. That distance then feeds the SAME
# machinery (flat clustering + optional density selection).
#
# Cluster extraction, in preference order:
#   1. PLSCAN (fast_plscan, Python >= 3.10) on the precomputed co-association
#      distance -- the requested backend; automatic multiscale resolution.
#   2. scipy fallback: average-linkage on the co-association distance + a flat
#      cut (by n_clusters or distance_threshold), then small clusters -> noise.
# ============================================================================


def _norm_label(v):
    """Normalise one hard label to a stable string category.

    NaN -> "NA", -1 -> "noise" (each becomes its own node/category downstream),
    integer-valued floats -> plain int string ("2.0" -> "2").
    """
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    try:
        if pd.isna(v):
            return "NA"
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and float(v).is_integer():
        v = int(v)
    s = str(v)
    return "noise" if s in ("-1", "-1.0") else s


def normalize_hard_labels(labels_df):
    """Return ``labels_df`` with a string index and every value normalised.

    Values become stable string categories (see :func:`_norm_label`): NaN->"NA",
    -1->"noise". Column order (the level order of the Sankey) is preserved.
    """
    if not isinstance(labels_df, pd.DataFrame):
        raise TypeError("clustering_labels must be a pandas DataFrame "
                        "(index = sample id, columns = ordered levels)")
    if labels_df.shape[1] < 1:
        raise ValueError("clustering_labels needs at least one label column")
    df = labels_df.copy()
    df.index = df.index.map(str)
    return df.map(_norm_label)


def _coassociation_distance(labels_df):
    """1 - co-association distance from normalised hard labels.

    ``D[i,j]`` = fraction of columns in which samples i and j have a DIFFERENT
    label (so identical partitions -> 0, never-together -> 1). Missing ("NA") and
    noise ("noise") are ordinary categories here: two samples both "NA" count as
    agreeing (they share the missing category), matching how they are drawn as
    their own shared node.
    """
    L = labels_df.to_numpy(dtype=object)
    n, m = L.shape
    D = np.zeros((n, n), dtype=float)
    for c in range(m):
        col = L[:, c]
        diff = (col[:, None] != col[None, :])   # n x n bool
        D += diff
    D /= max(m, 1)
    np.fill_diagonal(D, 0.0)
    return D


def _plscan_consensus(D, min_samples, verbose=True):
    """PLSCAN on a precomputed co-association distance; None if unavailable."""
    try:
        from fast_plscan import PLSCAN
    except Exception:
        return None
    try:
        clusterer = PLSCAN(min_samples=min_samples, metric="precomputed").fit(D)
        layers = clusterer.cluster_layers(max_peaks=1)
        if not layers:
            return None
        # most persistent clustering is the first layer -> (size, labels, probs)
        _size, labels, _probs = layers[0]
        if verbose:
            print(f"  PLSCAN: most-persistent layer at min_cluster_size={_size}")
        return _renumber(np.asarray(labels, dtype=int))
    except Exception as e:   # any PLSCAN failure -> caller falls back to scipy
        if verbose:
            print(f"  PLSCAN unavailable/failed ({e}); using scipy fallback")
        return None


def _scipy_consensus(D, min_samples, n_clusters, distance_threshold):
    """Average-linkage cut on the co-association distance (scipy fallback)."""
    n = D.shape[0]
    if n < 3:
        return np.zeros(n, dtype=int)
    linkage = sch.linkage(squareform(D, checks=False), method='average')
    if n_clusters is not None:
        raw = sch.fcluster(linkage, t=n_clusters, criterion='maxclust')
    else:
        if distance_threshold is None:
            distance_threshold = 0.7 * float(linkage[:, 2].max())
        raw = sch.fcluster(linkage, t=distance_threshold, criterion='distance')
    labels = raw.astype(int).copy()
    vals, counts = np.unique(labels, return_counts=True)
    for v, c in zip(vals, counts):
        if c < min_samples:
            labels[labels == v] = -1
    return _renumber(labels)


def _pcc_consensus(labels_df, K, layer_weights, random_state, verbose=True):
    """Probabilistic consensus clustering on the hard label columns.

    The co-association matrix holds *counts of Bernoulli events*, not arbitrary
    similarities, and PCC keeps that reading: it models
    ``P[i and j co-clustered] = y_i . y_j`` with ``y_i`` a soft membership on the
    simplex, and fits by maximum likelihood. ``K`` is an upper bound rather than
    a target -- unused clusters converge to zero mass -- so the method does its
    own model selection and no cluster count has to be supplied.

    On a real 344-sample x 9-level ensemble this fits the co-association evidence
    far better than the ``"coassociation"`` route -- 37.3k against 92.3k on PCC's
    own least-squares objective, in 6 clusters rather than 13.

    **Known failure mode.** The optimiser is greedy coordinate descent from a
    near-uniform start, and it gets stuck when the co-association matrix is close
    to binary -- i.e. when the levels agree almost perfectly and one hard
    partition already reproduces ``O``. On a synthetic ensemble of that shape it
    settled at roughly twice the objective of a partition that can be written
    down by hand, identically across 16 restarts (4 ``init_noise`` levels x 4
    seeds), so restarting does not rescue it. Real ensembles produce graded
    co-association and do not hit this. If the levels of an input agree almost
    exactly, prefer ``method="coassociation"``.
    """
    from . import pcc as _pcc

    n = len(labels_df)
    columns = [labels_df[c].to_numpy() for c in labels_df.columns]
    O, W, e_k = _pcc.observed_from_hard(columns, layer_weights=layer_weights)
    fit = _pcc.pcc(O, W, K=int(min(K, max(n, 2))), random_state=random_state)
    if verbose:
        print(f"  PCC: K={min(K, n)} upper bound -> {fit['used']} clusters carry "
              f"mass, {fit['n_clusters']} survive argmax "
              f"(chance co-membership per level: {np.round(e_k, 3).tolist()})")
    return _renumber(np.asarray(fit["labels"], dtype=int))


def consensus_hard_labels(labels_df, *, method="pcc", min_samples=5,
                          n_clusters=None, distance_threshold=None,
                          pcc_max_clusters=20, layer_weights="one_minus_e",
                          random_state=0, verbose=True):
    """Global consensus cluster per sample from an ensemble of HARD labels.

    Args:
        labels_df (DataFrame): index = sample id, columns = ordered levels
            (e.g. k-means at k=2,3,4). Values are hard labels; NaN and -1 are
            handled as the "NA" / "noise" categories.
        method (str): ``"pcc"`` (default) fits probabilistic consensus
            clustering -- see :func:`_pcc_consensus` and :mod:`~stripesankey.pcc`.
            ``"coassociation"`` is the older route: build the co-association
            distance and cut it with PLSCAN (fast_plscan, Py>=3.10) when
            available, otherwise a scipy average-linkage cut.
        min_samples (int): ``"coassociation"`` only -- PLSCAN ``min_samples``,
            and the scipy fallback's minimum cluster size (smaller -> noise).
        n_clusters (int, optional): ``"coassociation"`` scipy fallback only.
        distance_threshold (float, optional): ``"coassociation"`` scipy fallback
            only -- cut height (default = 70% of the maximum merge height).
        pcc_max_clusters (int): ``"pcc"`` only -- the upper bound ``K``. Set it
            comfortably above any plausible answer; unused clusters decay to zero
            mass, so this is not a target.
        layer_weights: ``"pcc"`` only. ``"one_minus_e"`` (default) weights each
            level by ``1 - e_k`` so a coarse level, which co-clusters most pairs
            by chance, does not drown out a fine one -- the same correction the
            soft path applies. ``None`` reproduces plain evidence accumulation.
        random_state (int): ``"pcc"`` only -- seeds the optimiser.
        verbose (bool): print a short summary.

    Returns:
        pandas.Series: consensus cluster label per sample (index = sample id,
        int), named ``"consensus"``. ``-1`` = noise, which only
        ``"coassociation"`` produces -- PCC assigns every sample to a cluster.
    """
    if method not in ("pcc", "coassociation"):
        raise ValueError(f"method must be 'pcc' or 'coassociation', got {method!r}")

    df = normalize_hard_labels(labels_df)
    n = len(df)

    if method == "pcc":
        if verbose:
            print(f"Consensus over {df.shape[1]} label columns, {n} samples (PCC)")
        labels = _pcc_consensus(df, pcc_max_clusters, layer_weights,
                                random_state, verbose=verbose)
    else:
        D = _coassociation_distance(df)
        if verbose:
            print(f"Consensus over {df.shape[1]} label columns, {n} samples; "
                  f"co-association distance range [{D.min():.3f}, {D.max():.3f}]")
        labels = _plscan_consensus(D, min_samples, verbose=verbose)
        if labels is None:
            labels = _scipy_consensus(D, min_samples, n_clusters, distance_threshold)

    n_cl = len(set(int(c) for c in labels if c != -1))
    n_noise = int((np.asarray(labels) == -1).sum())
    if verbose:
        print(f"✓ Consensus clustering: {n_cl} clusters, {n_noise} noise "
              f"({n_noise / max(n, 1) * 100:.0f}%)")
    return pd.Series([int(c) for c in labels], index=df.index, name="consensus")
