"""
The two views, as one call each.

Both read a finished sweep from its base folder -- the W tables and the
consensus :func:`~stripesankey.sweep` computed over them -- so there is one way
to draw a sweep, whether it was fitted here or elsewhere.

``stripesankey`` and ``metasankey`` are the same figure with one thing changed
-- what a node is sliced by. They are separate functions rather than one with a
``mode=`` switch because they take different arguments: ``metasankey`` requires
metadata, and the colour controls (``gradient``, ``cluster_colors``,
``cluster_legend``) apply only to the cluster-lineage view. Two signatures make
that a fact the caller can see, instead of a runtime warning.
"""

from __future__ import annotations

import os
import warnings
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .cache import _report_convergence, load_consensus, load_run_info, load_W
from .cluster_dendrogram import dendrogram_layout
from .mr_consensus import (
    cluster_from_affinity,
    coarse_affinity,
    coarse_linkage,
    coarse_sizes,
    coherent_cluster_palette,
    consensus_affinity,
)
from .stripesankey import StripeSankeyInline

__all__ = ["stripesankey", "metasankey", "build_sankey_data", "cluster_lineage"]


def _check(W_by_k: Mapping) -> list[int]:
    if not W_by_k:
        raise ValueError("W_by_k is empty")
    ks = sorted(int(k) for k in W_by_k)
    frames = [W_by_k[k] for k in ks]
    if not all(isinstance(f, pd.DataFrame) for f in frames):
        raise TypeError("every value of W_by_k must be a DataFrame "
                        "(rows = samples, columns = LCs)")
    first = frames[0].index
    for k, f in zip(ks, frames):
        if not f.index.equals(first):
            # The census and the ribbon identity both assume every column
            # describes the same population, so this is an error rather than a
            # gap to fill.
            raise ValueError(
                f"the W table at k={k} has a different sample index from the "
                f"one at k={ks[0]}. Every k must describe the same samples in "
                "the same order."
            )
        values = f.to_numpy(dtype=float)
        if np.isnan(values).any():
            raise ValueError(f"the W table at k={k} has missing values")
        if (values < 0).any():
            raise ValueError(f"the W table at k={k} has negative values")
    return ks


def _consensus(W_by_k, ks, resolution=0.0, noise_threshold=0.0):
    """``(sample_to_cluster, Q, labels)`` -- the clustering and what it came from."""
    Q = consensus_affinity({k: W_by_k[k].to_numpy() for k in ks})
    labels = np.asarray(cluster_from_affinity(Q, resolution=resolution,
                                              noise_threshold=noise_threshold))
    index = W_by_k[ks[0]].index
    return {str(s): int(l) for s, l in zip(index, labels)}, Q, labels


def cluster_lineage(Q, labels):
    """
    The palette and the legend tree, both built from the same ``Q``.

    Two things make a legend and the ribbons disagree, and this is how both are
    avoided. First, the widget has a fallback that derives its own dendrogram
    from an ad-hoc cosine distance over per-k occupancy -- a different distance
    from the chance-corrected ``Q`` the clusters actually came from, so its tree
    can group clusters the clustering did not. Second, supplying a palette
    without a matching tree (or the reverse) leaves the colours and the tree
    describing different things.

    So both come from one call on one ``Q``, and :func:`stripesankey` runs it by
    default. That also means the left-column legend is always the one drawn --
    the fallback is unreachable unless you build a ``StripeSankeyInline``
    yourself.

    Returns ``(palette, legend_layout)``.
    """
    palette = coherent_cluster_palette(Q, labels)
    Cq = coarse_affinity(Q, labels)
    legend = dendrogram_layout(coarse_linkage(Cq), list(Cq.index),
                               colors=palette,
                               sizes=coarse_sizes(labels).to_dict())
    return palette, legend


def build_sankey_data(W_by_k: Mapping, clusters: Mapping | pd.Series | None = None,
                      *, resolution: float = 0.0,
                      noise_threshold: float = 0.0) -> dict:
    """The widget's payload, built from ``W_by_k``.

    ``clusters`` defaults to the consensus computed here. Pass your own
    ``{sample_id: int}`` (``-1`` = noise) to view an alternative grouping
    through the same figure.
    """
    ks = _check(W_by_k)
    if clusters is None:
        s2c = _consensus(W_by_k, ks, resolution, noise_threshold)[0]
    elif isinstance(clusters, pd.Series):
        s2c = {str(s): int(c) for s, c in clusters.items()}
    elif isinstance(clusters, dict) and "sample_to_cluster" in clusters:
        s2c = {str(s): int(c) for s, c in clusters["sample_to_cluster"].items()}
    else:
        s2c = {str(s): int(c) for s, c in dict(clusters).items()}

    return {
        # `theta` is the widget's own wire name for this matrix, kept for
        # compatibility with data written before the W/H rename.
        "theta": {str(k): {str(s): [round(float(x), 4) for x in row]
                           for s, row in zip(W_by_k[k].index, W_by_k[k].to_numpy())}
                  for k in ks},
        "clusters": {"sample_to_cluster": s2c,
                     "n_clusters": len({c for c in s2c.values() if c >= 0})},
        "k_range": ks,
    }


def _meta_dict(metadata_df, fields):
    if metadata_df is None:
        return {}
    cols = [c for c in fields if c in metadata_df.columns]
    missing = [c for c in fields if c not in metadata_df.columns]
    if missing:
        raise KeyError(f"hover_field {missing} not in metadata_df "
                       f"(available: {list(metadata_df.columns)})")
    return {str(s): {c: (None if pd.isna(row[c]) else str(row[c])) for c in cols}
            for s, row in metadata_df.iterrows()}


def _fields(hover_field):
    if hover_field is None:
        return []
    if isinstance(hover_field, str):
        return [hover_field]
    return [str(f) for f in hover_field][:3]


def _load_sweep(base_directory, clusters, exclude_unsettled):
    """
    ``(W_by_k, clusters)`` -- every k of the sweep in ``base_directory``, and
    ``clusters`` or, by default, the consensus ``sweep`` computed over them.

    Every k is loaded even when ``k_list`` draws only some: the palette and the
    legend tree have to come from the ``Q`` the consensus came from, which
    pools every k. See :func:`cluster_lineage`.
    """
    if not isinstance(base_directory, (str, os.PathLike)):
        raise TypeError(
            "expected the base folder of a sweep, got "
            f"{type(base_directory).__name__}. To draw W tables made elsewhere, "
            "save each as <base>/results/W/W_<k>.csv and run ss.sweep(base) "
            "for their consensus.")
    try:
        info = load_run_info(base_directory)
        stored = load_consensus(base_directory) if clusters is None else None
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{base_directory} has no finished sweep: results/run_info.json and "
            "results/consensus.json are written by ss.sweep(base) -- which, for "
            "W tables saved from elsewhere, computes the consensus without "
            "fitting anything.") from None
    ks = sorted(int(k) for k in info["k_list"])

    if exclude_unsettled:
        bad = set(_report_convergence(info, verbose=False))
        dropped = sorted(set(ks) & bad)
        ks = [k for k in ks if k not in bad]
        if dropped:
            warnings.warn(
                f"k={dropped} dropped: the fit did not settle. Pass "
                "exclude_unsettled=False to include them anyway.",
                stacklevel=3,
            )
        if not ks:
            raise ValueError(
                "every k has an unsettled fit; nothing left to draw. Raise "
                "`max_passes`, or pass exclude_unsettled=False to look anyway."
            )

    W_by_k = load_W(base_directory, ks)
    if clusters is None:
        clusters = {str(s): int(c) for s, c in stored["sample_to_cluster"].items()}
        if set(clusters) != {str(s) for s in next(iter(W_by_k.values())).index}:
            raise ValueError(
                f"results/consensus.json in {base_directory} is for different "
                "samples than its W tables, which changed after the consensus "
                "was computed. Run ss.sweep(base) again.")
    return W_by_k, clusters


def _common(W_by_k, clusters, k_list, metadata_df, hover_field, figsize, dpi,
            want_lineage=False):
    data = build_sankey_data(W_by_k, clusters)
    lineage = None
    if want_lineage:
        # Built from whatever labels are actually being drawn, not only from a
        # consensus computed here -- supplying your own `clusters` must not cost
        # you the coherent legend, or the widget falls back to its own
        # cosine-distance tree and the legend stops matching the ribbons.
        ks = sorted(int(k) for k in data["k_range"])
        index = W_by_k[ks[0]].index
        s2c = data["clusters"]["sample_to_cluster"]
        labels = np.asarray([s2c.get(str(i), -1) for i in index])
        if len({c for c in labels if c >= 0}) >= 2:
            # Q is N x N -- it stays local and never goes near a traitlet.
            Q = consensus_affinity({k: W_by_k[k].to_numpy() for k in ks})
            lineage = cluster_lineage(Q, labels)
    shown = sorted(int(k) for k in (k_list if k_list is not None else data["k_range"]))
    unknown = set(shown) - set(data["k_range"])
    if unknown:
        raise ValueError(f"k_list asks for k={sorted(unknown)}, but the sweep "
                         f"has k={data['k_range']}")
    fields = _fields(hover_field)
    return (data, shown, fields, _meta_dict(metadata_df, fields),
            int(figsize[1] * dpi), lineage)


def stripesankey(base_directory: str, *,
                 clusters=None,
                 k_list: Iterable[int] | None = None,
                 exclude_unsettled: bool = True,
                 metadata_df: pd.DataFrame | None = None,
                 hover_field=None,
                 gradient: str | None = None,
                 gradient_spread: float = 0.0,
                 gradient_light: float = 82.0,
                 node_width: int | None = None,
                 cluster_colors: Mapping | None = None,
                 cluster_legend: Mapping | None = None,
                 figsize=(3, 4),
                 dpi: int = 100,
                 **kwargs) -> StripeSankeyInline:
    """
    The census, coloured by consensus cluster.

    Each column is a full census of one k -- every sample in its top-proportion
    LC, no confidence gate -- so node height and ribbon width are the same head
    count and a ribbon's thickness reads as a number of samples.

    Args:
        base_directory: a folder :func:`~stripesankey.sweep` has run on -- its
            W tables and the consensus computed over them.
        clusters: ``{sample_id: int}`` (``-1`` = noise) to colour by your own
            grouping. Default: the consensus ``sweep`` computed.
        k_list: which k columns to draw; gaps are allowed. Default: all.
        exclude_unsettled: leave out any k whose fit did not settle -- a
            column built from an unsettled fit is not a statement about the
            data.
        metadata_df, hover_field: sample-indexed metadata and up to 3 of its
            columns. The first drives the ``K =``-click restack.
        gradient: any CSS colour switches the clusters to a single-hue
            light-to-dark ramp over the same lineage order, so darkness rather
            than hue carries it and the figure survives greyscale printing.
        cluster_colors, cluster_legend: override the palette and replace the
            legend's own tree. Build both from the same ``Q`` -- see
            :func:`coherent_cluster_palette` and :func:`dendrogram_layout` --
            or the legend and the ribbons can disagree about which clusters are
            alike.
    """
    W_by_k, clusters = _load_sweep(base_directory, clusters, exclude_unsettled)
    data, shown, fields, meta, height, lineage = _common(
        W_by_k, clusters, k_list, metadata_df, hover_field, figsize, dpi,
        want_lineage=(cluster_colors is None or cluster_legend is None))
    # Both default to the coherent pair, so the widget's own cosine-distance
    # fallback legend is never the one drawn. See `cluster_lineage`.
    if lineage is not None:
        _pal, _leg = lineage
        cluster_colors = _pal if cluster_colors is None else cluster_colors
        cluster_legend = _leg if cluster_legend is None else cluster_legend
    return StripeSankeyInline(
        sankey_data=data, mode="cluster_prox", k_list=shown,
        metadata=meta, hover_field=fields,
        gradient=gradient or "",
        gradient_spread=float(gradient_spread),
        gradient_light=float(gradient_light),
        node_width=int(node_width or 0),
        cluster_colors={str(k): v for k, v in (cluster_colors or {}).items()},
        cluster_legend=dict(cluster_legend or {}),
        height=height, **kwargs)


def metasankey(base_directory: str, *,
               metadata_df: pd.DataFrame,
               hover_field,
               clusters=None,
               k_list: Iterable[int] | None = None,
               exclude_unsettled: bool = True,
               high_threshold: float = 0.5,
               figsize=(3, 4),
               dpi: int = 100,
               **kwargs) -> StripeSankeyInline:
    """
    The same census, cut by a metadata field instead of by cluster.

    Same layout, same column order, same node positions -- so a bar at a given
    height here is the same bar in :func:`stripesankey`, and flipping between
    the two answers "is this cluster that category?" by eye.

    ``metadata_df`` and ``hover_field`` are required: the first field is what
    the nodes and flows are coloured by. ``clusters`` is still used, but only to
    order the columns and the category stack the way the cluster view orders
    them. ``base_directory``, ``k_list`` and ``exclude_unsettled`` are as in
    :func:`stripesankey`.
    """
    if metadata_df is None or not _fields(hover_field):
        raise ValueError("metasankey needs metadata_df and hover_field -- the "
                         "first field is what nodes and flows are coloured by")
    W_by_k, clusters = _load_sweep(base_directory, clusters, exclude_unsettled)
    data, shown, fields, meta, height, _ = _common(
        W_by_k, clusters, k_list, metadata_df, hover_field, figsize, dpi)
    return StripeSankeyInline(
        sankey_data=data, mode="meta_sankey", k_list=shown,
        metadata=meta, hover_field=fields,
        high_threshold=float(high_threshold),
        height=height, **kwargs)
