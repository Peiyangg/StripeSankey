"""Annotated heatmap of the signed consensus affinity ``Q``.

The companion to :mod:`a_heatmap`. Where ``a_heatmap`` draws a *sample x LC*
matrix, this draws the *sample x sample* consensus affinity that
:func:`mr_consensus.consensus_affinity` returns, ordered by consensus cluster
and carrying the same kind of metadata annotation strips::

    from stripesankey import affinity_heatmap

    affinity_heatmap(
        Q,                              # square sample x sample DataFrame
        above=metadata_df,              # sample-indexed metadata
        annotations=["region"],         # which metadata column(s) to draw
        save_path="affinity.png",
    )

Naming follows ``a_heatmap``: ``above`` is the metadata frame, ``annotations``
picks its columns, ``sort`` chooses the ordering.

Why this view exists
--------------------
StripeSankey encodes how membership *moves* across k; colouring its flows by
consensus cluster says which cluster a sample is in, but has no channel left to
say what that cluster *is*. This plot answers that, and shows ``Q`` itself,
which otherwise only appears in the paper as an equation:

* blocks on the diagonal     -> how coherent each cluster is
* warmth off the diagonal    -> which clusters nearly merge
* the annotation strips      -> what each cluster is made of
* a smooth rather than blocky fade is itself a result: it says the samples lie
  on a gradient rather than in discrete groups.

Colour
------
``Q`` is signed and zero is the chance threshold, so the map is *diverging* and
pinned at zero: red above chance, blue below, neutral grey exactly at zero.
Annotation strips take a fixed, colourblind-checked categorical order.
"""
import math

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Patch, Rectangle

# Diverging pair: blue <-> red with a neutral grey midpoint. Never a hue at the
# midpoint -- zero must read as "nothing", not as a third category. The sample-LC
# heatmap uses a *sequential* Blues ramp because theta is a probability in [0,1];
# Q is signed with a meaningful zero, so it needs a diverging ramp instead.
_NEG, _MID, _POS = "#2a78d6", "#f0efec", "#e34948"
AFFINITY_CMAP = LinearSegmentedColormap.from_list("affinity", [_NEG, _MID, _POS])

# Categorical annotation colours, assigned by slot and never cycled.
#
# NOT d3.schemeTableau10, which `heatmap_sample` uses: its first five fail the
# colourblind check outright -- #59a14f (green) vs #e15759 (red) sit at CVD
# Delta E 0.7 under deuteranopia, i.e. the same colour for a red-green
# colourblind reader. This order clears the all-pairs CVD and normal-vision
# floors. Everything else here follows `heatmap_sample`'s conventions.
_CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]
_OTHER = "#9a9a93"
# A field with more levels than the palette is labelled directly on its strip
# instead of being given invented hues (or collapsed into one grey, which would
# make C5, C6 and C7 the same colour). Alternating neutrals separate the runs;
# the text carries the identity.
_NEUTRAL = ("#dcdbd6", "#efedE9")
_MISSING = "#eee"                  # heatmap_sample's null colour

# Continuous metadata gets Viridis, as in heatmap_sample.
_CONTINUOUS_CMAP = "viridis"

# Ordered categories (a time point, a stage) get a single hue running light to
# dark, so the reader sees the order rather than five unrelated identities.
# Sampled from 0.38 upward: below that the lightest step stops clearing the
# page surface (contrast < 2:1) and the first level disappears in print.
_ORDINAL_ENDS = ("#e3edfa", "#1c4f8f")
_ORDINAL_START = 0.38

# Layout, ported from the widget's ESM so the two figures read as one family:
#   stripH = min(20, ...)   -> strip height cap
#   rh     = stripH - 1     -> a 1px gap between neighbouring strips
#   gy     = metaH + 6      -> a 6px gap between the band and the heatmap
_STRIP_FRAC = 20 / 480.0           # strip height as a fraction of plot height
_STRIP_GAP = 1 / 20.0              # of a strip: the widget's 1px in 20px
_BAND_GAP = 6 / 480.0              # band -> heatmap gap

_HM_W_FRAC = 0.72                  # heatmap width as a fraction of figsize[0]
_SPLIT_GAP_PX = 16.0               # target on-page split gap, matching
                                    # heatmap_sample's own default split_width

_GRID = "#d8d7d2"
_INK, _INK_MUTED = "#111111", "#333333"


def _infer_field(series):
    """Same rule as result_visualization._infer_field: numeric with >8 distinct
    values is continuous, everything else categorical."""
    v = series.dropna()
    if pd.api.types.is_numeric_dtype(v) and v.nunique() > 8:
        lo, hi = (float(v.min()), float(v.max())) if len(v) else (0.0, 1.0)
        return {"type": "continuous", "domain": [lo, hi if hi > lo else lo + 1.0]}
    return {"type": "categorical", "values": _levels(series)}


def _as_frame(Q, index=None):
    if isinstance(Q, pd.DataFrame):
        return Q
    if index is None:
        raise ValueError("Q given as an array needs an `index` of sample ids")
    return pd.DataFrame(np.asarray(Q), index=index, columns=index)


def _cluster_then_core(Q, labels):
    """Order samples by cluster, and inside a cluster by how core they are.

    Ordering members by descending mean affinity to their own cluster puts the
    core of each block at its start and the marginal members at its edge, so a
    gradient between neighbouring clusters stays visible instead of being
    scrambled by the input order.
    """
    order, bounds = [], []
    for c in sorted(set(labels) - {-1}):
        idx = np.flatnonzero(labels == c)
        sub = Q[np.ix_(idx, idx)]
        if idx.size > 1:
            strength = (sub.sum(axis=1) - np.diag(sub)) / (idx.size - 1)
            idx = idx[np.argsort(-strength, kind="stable")]
        order.extend(idx.tolist())
        bounds.append(len(order))
    noise = np.flatnonzero(labels == -1)
    if noise.size:
        order.extend(noise.tolist())
        bounds.append(len(order))
    return np.asarray(order), bounds[:-1]


def _levels(series):
    """Level order for a metadata column.

    A pandas Categorical carries its own order, which is the only way to say
    that "early stage" precedes "late stage" -- alphabetical sorting would put
    late before transitional and mislabel the legend. Everything else sorts.
    """
    if isinstance(series.dtype, pd.CategoricalDtype):
        present = set(series.dropna().astype(str))
        return [str(c) for c in series.cat.categories if str(c) in present]
    v = series.dropna()
    try:
        return [str(x) for x in sorted(v.unique().tolist())]
    except TypeError:
        return [str(x) for x in sorted(map(str, v.unique().tolist()))]


def _ordinal_steps(n):
    """`n` single-hue steps, light -> dark; validated for print contrast."""
    cm = LinearSegmentedColormap.from_list("ordinal", list(_ORDINAL_ENDS))
    xs = [1.0] if n == 1 else np.linspace(_ORDINAL_START, 1.0, n)
    return [mpl.colors.to_hex(cm(x)) for x in xs]


def _continuous_rgb(series, domain=None):
    """(rgb array (n,3), (lo, hi)) mapping `series` through the Viridis ramp.

    Shared by the automatic continuous branch of `_strip_rgb` (a numeric
    column with >8 distinct values) and the forced ``continuous=`` override,
    so a caller can put a low-cardinality numeric field like an ordinal stage
    (0/1/2) on the same smooth ramp instead of the unrelated-hue categorical
    palette that `_infer_field`'s cardinality heuristic would otherwise pick.
    """
    num = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if domain is None:
        finite = num[np.isfinite(num)]
        lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        if hi <= lo:
            hi = lo + 1.0
    else:
        lo, hi = domain
    cmap = plt.get_cmap(_CONTINUOUS_CMAP)
    rgb = np.array([
        mpl.colors.to_rgb(_MISSING) if not np.isfinite(x)
        else cmap((x - lo) / (hi - lo))[:3]
        for x in num
    ])
    return rgb, (lo, hi)


def _strip_rgb(series, kind=None, custom_lut=None):
    """(rgb array (n,3), legend spec) for one metadata column.

    ``kind='ordinal'`` forces the single-hue light-to-dark ramp for a column
    whose levels are ordered; ``kind='continuous'`` forces the Viridis ramp
    (bypassing ``_infer_field``'s >8-distinct-values threshold, so a
    low-cardinality numeric field like a 0/1/2 stage can still be read as a
    smooth gradient); otherwise the type is inferred as in
    ``result_visualization._infer_field``.

    ``custom_lut``, when given, replaces the auto-assigned categorical
    palette entirely -- including the >5-level fallback to unlabelled grey
    runs, which is what a caller passing a real palette is trying to escape
    in the first place (e.g. the consensus-cluster column, whose count
    routinely exceeds ``len(_CATEGORICAL)``). A value absent from
    ``custom_lut`` still falls back to ``_OTHER``, so a partial map is safe --
    and conversely a ``custom_lut`` broader than what this column actually
    contains (the same palette reused across a field and a collapsed version
    of it, e.g.) is also safe: the legend below only lists the values this
    series actually has, not every key the caller happened to pass in.
    """
    if custom_lut:
        lut_all = {str(k): v for k, v in custom_lut.items()}
        lut = {v: lut_all.get(v, _OTHER) for v in _levels(series)}
        rgb = np.array([
            mpl.colors.to_rgb(_MISSING) if pd.isna(v) else mpl.colors.to_rgb(lut_all.get(str(v), _OTHER))
            for v in series.to_numpy()
        ])
        return rgb, ("categorical", lut)

    if kind == "ordinal":
        levels = _levels(series)
        lut = dict(zip(levels, _ordinal_steps(len(levels))))
        rgb = np.array([
            mpl.colors.to_rgb(_MISSING) if pd.isna(v)
            else mpl.colors.to_rgb(lut.get(str(v), _MISSING))
            for v in series.to_numpy()
        ])
        return rgb, ("ordinal", lut)

    if kind == "continuous":
        rgb, (lo, hi) = _continuous_rgb(series)
        return rgb, ("continuous", (lo, hi))

    field = _infer_field(series)
    vals = series.to_numpy()
    if field["type"] == "continuous":
        rgb, (lo, hi) = _continuous_rgb(series, domain=field["domain"])
        return rgb, ("continuous", (lo, hi))

    levels = field["values"]
    if len(levels) > len(_CATEGORICAL):
        # direct labels rather than invented hues -- see _NEUTRAL above
        runs, start = [], 0
        for i in range(1, len(vals) + 1):
            if i == len(vals) or str(vals[i]) != str(vals[start]):
                runs.append((str(vals[start]), start, i))
                start = i
        rgb = np.empty((len(vals), 3))
        for j, (_lab, a, b) in enumerate(runs):
            rgb[a:b] = mpl.colors.to_rgb(_NEUTRAL[j % 2])
        return rgb, ("labelled", runs)

    lut = {v: _CATEGORICAL[i] for i, v in enumerate(levels)}
    rgb = np.array([
        mpl.colors.to_rgb(_MISSING) if pd.isna(v) else mpl.colors.to_rgb(lut.get(str(v), _OTHER))
        for v in vals
    ])
    return rgb, ("categorical", lut)


def _insert_gaps(n, boundaries, width):
    """Column-index map from `n` original positions to a padded axis with a
    `width`-cell blank gap inserted before every position in `boundaries`.

    Returns ``(new_n, colmap)`` where ``colmap[i]`` is the padded position of
    original position ``i``. This is the static-figure analogue of
    ``heatmap_sample``'s interactive "scissors" split: instead of a reader
    dragging cosmetic gaps between columns at view time, the boundaries are
    fixed once (at the existing cluster/sort blocks, or at caller-chosen
    positions) and baked into the saved figure as real blank space rather
    than a thin grid line.
    """
    gaps = set(int(b) for b in boundaries)
    colmap = np.empty(n, dtype=int)
    pos = 0
    for i in range(n):
        if i in gaps:
            pos += width
        colmap[i] = pos
        pos += 1
    return pos, colmap


def _legend_ncol(handles):
    """One row while the labels stay short, two rows once they do not.

    Counting entries alone is not enough: four one-word labels fit on a line,
    four labels like "pre-symptomatic" do not.
    """
    chars = sum(len(str(h.get_label())) for h in handles)
    if len(handles) <= 3 and chars <= 24:
        return len(handles)
    return max(1, (len(handles) + 1) // 2)


def affinity_heatmap(
    Q,
    above=None,
    annotations=None,
    labels=None,
    ordinal=None,
    continuous=None,
    colors=None,
    cluster_strip=True,
    sort=None,
    index=None,
    vmax=None,
    figsize=(7.2, 8.2),
    title=None,
    save_path=None,
    dpi=300,
    split=True,
    split_width=None,
):
    """Annotated heatmap of a signed consensus affinity matrix.

    Parameters
    ----------
    Q : DataFrame or ndarray
        Square sample x sample signed affinity, as returned by
        ``mr_consensus.consensus_affinity``. An ndarray needs ``index``.
    above : DataFrame, optional
        Sample-indexed metadata (index aligned to ``Q``), whose columns are
        drawn *above* the heatmap.
    annotations : str or list of str, optional
        Which column(s) of ``above`` to draw as annotation strips.
    labels : array-like, optional
        Consensus cluster label per sample (``-1`` = unassigned). If omitted,
        they are computed with ``mr_consensus.cluster_from_affinity``.
    ordinal : str or list of str, optional
        Column(s) whose levels are ordered (a time point, a stage). These are
        drawn with a single hue running light to dark instead of unrelated
        categorical hues, so the reader sees the order.
    continuous : str or list of str, optional
        Column(s) to force onto the continuous Viridis ramp, bypassing the
        auto-inferred >8-distinct-values threshold. Use this for a numeric
        field with few distinct levels (e.g. a 0/1/2 stage code) that should
        still read as a gradient rather than as unrelated categorical hues.
    colors : dict, optional
        ``{column_name: {value: css_colour}}``, overriding the auto-assigned
        palette for one or more annotation columns -- entirely, including the
        >5-level fallback to unlabelled grey runs, which is what a real
        palette is usually meant to escape (a consensus-cluster column
        routinely has more than 5 levels). A value missing from the map still
        falls back to a neutral grey, so a partial map is safe. Use this to
        make the "cluster" strip agree with a palette computed elsewhere from
        the same ``Q`` -- e.g. ``colors={"cluster": {f"C{c}": hexcolour for
        c, hexcolour in mr_consensus.coherent_cluster_palette(Q, labels).items()}}``
        -- instead of an unrelated one invented for this figure alone.
    cluster_strip : bool, default True
        Draw the consensus cluster as the annotation strip nearest the heatmap,
        coloured by :func:`~stripesankey.mr_consensus.coherent_cluster_palette`
        on this same ``Q``. The clusters are what ``Q`` was partitioned into and
        what the default ordering blocks by, so without the strip the blocks are
        visible but unlabelled. Pass ``False`` to omit it, or supply your own
        column named ``"cluster"`` in ``above`` to override it.
    sort : str or list of str, optional
        ``None`` (default) orders by consensus cluster, and within a cluster by
        decreasing affinity to that cluster. A metadata column name (or list)
        orders by that instead, which is the view to use when asking whether a
        known grouping is recovered.
    index : sequence, optional
        Sample ids, required only when ``Q`` is a bare ndarray.
    vmax : float, optional
        Symmetric colour limit. Default is the 99th percentile of \\|Q\\|, which
        keeps a few extreme pairs from flattening everything else.
    figsize, dpi : figure size in inches and raster resolution.
    title : str, optional
    save_path : str, optional
        If given, the figure is written here (``.png`` or ``.pdf``).
    split : bool or list of int, optional
        The static-figure analogue of ``heatmap_sample``'s interactive
        "✂ split": instead of a thin grid line, real blank space is inserted
        between blocks so the eye groups them at a glance. ``True`` (default)
        gaps at every boundary already used for the grid lines (the consensus
        cluster or ``sort`` blocks) -- harmless when there is only one block,
        since then there is no boundary to gap at. A list of ints instead
        gaps at exactly those positions in the final (sorted) sample order --
        e.g. boundaries eyeballed with the interactive ``heatmap_sample``
        widget and then locked in here for a publication figure. Pass
        ``False`` (or ``None``) for the old thin-grid-line-only look.
    split_width : int, optional
        Gap width in sample-cell widths. Default ``None`` auto-scales so the
        gap is ``_SPLIT_GAP_PX`` (16, matching ``heatmap_sample``'s own
        default) *physical* pixels wide at this call's ``figsize``/``dpi``,
        regardless of how many samples ``n`` there are -- a fixed cell count
        would go from a 16px gap at n=289 to a sub-pixel hairline at n=2400
        (this package's population-genetics figures) or an oversized gap at
        n=20. Pass an explicit int to override the auto-scaling.

    Returns
    -------
    (fig, order, labels)
        The figure, the sample ordering used, and the cluster labels.
    """
    Qdf = _as_frame(Q, index)
    if Qdf.shape[0] != Qdf.shape[1]:
        raise ValueError(f"Q must be square, got {Qdf.shape}")
    samples = Qdf.index.map(str)
    A = np.asarray(Qdf, dtype=float)

    if labels is None:
        from .mr_consensus import cluster_from_affinity
        labels = cluster_from_affinity(A, resolution=0.0, random_state=0)
    labels = np.asarray(labels)

    if ordinal is None:
        ordinal = []
    elif isinstance(ordinal, str):
        ordinal = [ordinal]
    else:
        ordinal = list(ordinal)

    if continuous is None:
        continuous = []
    elif isinstance(continuous, str):
        continuous = [continuous]
    else:
        continuous = list(continuous)

    if annotations is None:
        annotations = []
    elif isinstance(annotations, str):
        annotations = [annotations]
    else:
        annotations = list(annotations)

    colors = dict(colors or {})

    meta = pd.DataFrame(index=samples) if above is None else above.copy()
    meta.index = meta.index.map(str)
    meta = meta.reindex(samples)
    for c in annotations:
        if c not in meta.columns:
            raise KeyError(f"annotation column {c!r} not in `above` "
                           f"(available: {list(meta.columns)})")

    # ---- the consensus strip, drawn by default ----------------------------
    # The clusters are what `Q` was partitioned into and what the default
    # ordering blocks by, so the figure is hard to read without them -- the
    # blocks are visible but unlabelled, and a reader cannot say which block is
    # which cluster. Its colours come from `coherent_cluster_palette` on the
    # same `Q`, so the strip, the ordering and any lineage figure built from
    # that palette all agree. This is what `colors={"cluster": ...}` used to be
    # for by hand.
    if cluster_strip and "cluster" not in meta.columns:
        from .mr_consensus import coherent_cluster_palette

        meta.insert(0, "cluster",
                    ["noise" if l < 0 else f"C{int(l)}" for l in labels])
        annotations = ["cluster"] + [c for c in annotations if c != "cluster"]
        if "cluster" not in colors:
            try:
                pal = coherent_cluster_palette(A, labels)
                lut = {f"C{int(c)}": hexcol for c, hexcol in pal.items()}
            except Exception:                        # pragma: no cover
                lut = {}
            lut.setdefault("noise", "#ffffff")
            colors = {**colors, "cluster": lut}

    # ---- ordering ----------------------------------------------------------
    if sort is None:
        order, bounds = _cluster_then_core(A, labels)
    else:
        cols = [sort] if isinstance(sort, str) else list(sort)
        for c in cols:
            if c not in meta.columns:
                raise KeyError(f"sort column {c!r} not in `above`")
        order = np.argsort(
            pd.MultiIndex.from_frame(meta[cols].astype(str)).codes[0], kind="stable"
        ) if len(cols) == 1 else np.asarray(
            meta.reset_index().sort_values(cols).index
        )
        keys = meta[cols].astype(str).agg("|".join, axis=1).to_numpy()[order]
        bounds = [i for i in range(1, len(order)) if keys[i] != keys[i - 1]]

    A = A[np.ix_(order, order)]
    n = len(order)

    # ---- colour limits: symmetric, pinned at zero ---------------------------
    if vmax is None:
        off = ~np.eye(n, dtype=bool)
        vmax = float(np.percentile(np.abs(A[off]), 99)) or float(np.abs(A).max())
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

    # ---- split: real blank space at chosen boundaries, not just a grid line -
    if split is None or split is False:
        gap_at = []
    elif split is True:
        gap_at = list(bounds)
    else:
        gap_at = sorted(set(int(b) for b in split))
        for b in gap_at:
            if not (0 < b < n):
                raise ValueError(f"split boundary {b} out of range for {n} samples")
    gap_set = set(gap_at)
    if gap_at:
        if split_width is None:
            # cell width in on-page pixels = (heatmap width in px) / n, so the
            # cell count that spans _SPLIT_GAP_PX px is _SPLIT_GAP_PX / cell
            # width -- i.e. it grows with n instead of staying a fixed count
            # of (shrinking) cells.
            hm_w_px = _HM_W_FRAC * figsize[0] * dpi
            split_width = max(1, round(_SPLIT_GAP_PX * n / hm_w_px))
        new_n, colmap = _insert_gaps(n, gap_at, split_width)
    else:
        new_n, colmap = n, np.arange(n)

    # ---- layout, following heatmap_sample -----------------------------------
    # Explicit axes rectangles rather than a gridspec: the matrix is square, so
    # the band has to be pinned to the heatmap's own x-extent or the two drift
    # apart. One axes holds the whole band so the strips stack tight (a 1px
    # separator, as in the widget) instead of being spaced by matplotlib.
    n_strips = len(annotations)
    fig_w, fig_h = figsize
    left, bottom, hm_w = 0.15, 0.14, _HM_W_FRAC
    hm_h = hm_w * fig_w / fig_h                     # square in inches
    strip_h = _STRIP_FRAC * hm_h                    # widget: 20px of 480px
    band_h = n_strips * strip_h
    band_gap = _BAND_GAP * hm_h                     # widget: 6px of 480px

    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_axes([left, bottom, hm_w, hm_h])
    cax = fig.add_axes([left + hm_w + 0.015, bottom, 0.018, hm_h])

    legends, field_labels = [], []
    if n_strips:
        bax = fig.add_axes([left, bottom + hm_h + band_gap, hm_w, band_h])
        band = np.empty((n_strips, n, 3), dtype=float)
        for r, col in enumerate(annotations):
            kind = ('continuous' if col in continuous
                    else 'ordinal' if col in ordinal else None)
            rgb, spec = _strip_rgb(meta[col].iloc[order], kind=kind,
                                   custom_lut=colors.get(col))
            band[r] = rgb
            legends.append((col, spec))
        if gap_at:
            band_plot = np.ones((n_strips, new_n, 3), dtype=float)
            band_plot[:, colmap, :] = band
        else:
            band_plot = band
        bax.imshow(band_plot, aspect="auto", interpolation="nearest")
        for r in range(1, n_strips):                # the widget's 1px gap
            bax.axhline(r - 0.5, color="white", lw=0.8)
        for r, (_col, (kind_, spec_)) in enumerate(legends):
            if kind_ != "labelled":
                continue
            for lab_, a, b in spec_:
                if (b - a) / n < 0.02:          # too narrow to letter
                    continue
                cx = (colmap[a] + colmap[b - 1] + 1) / 2 - 0.5
                bax.text(cx, r, lab_, ha="center", va="center",
                         fontsize=7, color=_INK)
        bax.set_xticks([]); bax.set_yticks([])
        for sp in bax.spines.values():
            sp.set_visible(False)
        for r, col in enumerate(annotations):       # right-aligned in the margin
            field_labels.append(bax.text(
                -0.008, r, col, transform=bax.get_yaxis_transform(),
                ha="right", va="center", fontsize=9, color=_INK_MUTED))

    if gap_at:
        A_plot = np.full((new_n, new_n), np.nan)
        A_plot[np.ix_(colmap, colmap)] = A
        gap_cmap = AFFINITY_CMAP.copy()
        gap_cmap.set_bad("white")
    else:
        A_plot, gap_cmap = A, AFFINITY_CMAP
    im = ax.imshow(A_plot, cmap=gap_cmap, norm=norm,
                   interpolation="nearest", aspect="auto")
    for b in bounds:
        if b in gap_set:
            continue
        ax.axhline(colmap[b] - 0.5, color=_GRID, lw=0.6)
        ax.axvline(colmap[b] - 0.5, color=_GRID, lw=0.6)
    if gap_at:
        # bold box around each block cut apart by the split, echoing the
        # widget's "box each split block" -- the gap alone separates the
        # blocks, the box reinforces which cells belong to the same one.
        segs = [0] + sorted(gap_set) + [n]
        for p in range(len(segs) - 1):
            a, b = segs[p], segs[p + 1]
            if b <= a:
                continue
            x0, x1 = colmap[a] - 0.5, colmap[b - 1] + 0.5
            ax.add_patch(Rectangle((x0, x0), x1 - x0, x1 - x0,
                                   fill=False, edgecolor=_INK, lw=1.3,
                                   zorder=5))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(_GRID); sp.set_linewidth(0.6)
    ax.set_xlabel(f"{n} samples, ordered by "
                  + ("consensus cluster" if sort is None else str(sort)),
                  fontsize=9, color=_INK_MUTED, labelpad=8)

    cb = fig.colorbar(im, cax=cax)
    cb.set_label("consensus affinity $Q$   (0 = chance)", fontsize=9, color=_INK)
    cb.ax.tick_params(labelsize=8, colors=_INK_MUTED, length=2)
    cb.outline.set_visible(False)

    # ---- legends: one row under the plot, one equal slot per field ---------
    # Identity is never colour-alone, so every strip gets named swatches.
    keyed = [(c, sp) for c, sp in legends if sp[0] != "labelled"]
    if keyed:
        # The legend row spans the figure's real content width: from the left
        # edge of the annotation field names to the right edge of the colour
        # bar's label. Both are text, so the span has to be measured from what
        # was actually drawn rather than guessed from the axes rectangles --
        # "Diagnosis_clinical" reaches much further left than the heatmap does.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        inv = fig.transFigure.inverted()

        def _x_range(artists):
            xs = []
            for a in artists:
                if a is None:
                    continue
                bb = a.get_window_extent(renderer)
                xs += [inv.transform((bb.x0, 0))[0], inv.transform((bb.x1, 0))[0]]
            return xs

        left_artists = list(field_labels) or [ax]
        x_left = min(_x_range(left_artists) + [left])
        x_right = max(_x_range([cb.ax.yaxis.label]) + [left + hm_w])
        span = x_right - x_left

        slot = span / len(keyed)
        ley = bottom - 0.055
        for i, (col, (kind, spec)) in enumerate(keyed):
            x = x_left + i * slot
            if kind == "continuous":
                lo, hi = spec
                sm = mpl.cm.ScalarMappable(
                    cmap=plt.get_cmap(_CONTINUOUS_CMAP),
                    norm=mpl.colors.Normalize(lo, hi))
                lcax = fig.add_axes([x, ley - 0.012, slot * 0.6, 0.014])
                lcb = fig.colorbar(sm, cax=lcax, orientation="horizontal")
                lcb.set_label(col, fontsize=9, color=_INK, labelpad=4)
                lcb.ax.xaxis.set_label_position("top")
                lcb.ax.tick_params(labelsize=8, colors=_INK_MUTED, length=2)
                lcb.outline.set_visible(False)
                continue
            handles = [Patch(facecolor=c, label=str(v))
                       for v, c in spec.items() if c != _OTHER]
            if _OTHER in spec.values():
                handles.append(Patch(facecolor=_OTHER, label="other"))
            leg = fig.legend(
                handles=handles, title=col, loc="upper left",
                bbox_to_anchor=(x, ley), frameon=False,
                ncol=_legend_ncol(handles), columnspacing=0.8,
                fontsize=8, title_fontsize=9,
                handlelength=0.9, handleheight=0.9,
                handletextpad=0.4, borderpad=0, borderaxespad=0,
            )
            leg.get_title().set_color(_INK)
            leg._legend_box.align = "left"
            for t in leg.get_texts():
                t.set_color(_INK_MUTED)

    if title:
        # top-left, as in the widget's in-SVG title
        fig.text(left, bottom + hm_h + band_h + band_gap + 0.025, title,
                 fontsize=11, fontweight="bold", color=_INK, ha="left")
    if save_path:
        fig.savefig(save_path, bbox_inches="tight", facecolor="white")
    return fig, samples[order], labels
