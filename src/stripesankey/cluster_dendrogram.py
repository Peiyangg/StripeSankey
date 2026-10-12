"""
A dendrogram whose LEAVES are colour-coded circles sitting at their own
first-merge height, not a shared y=0 baseline.

A plain dendrogram (matplotlib's or D3's off-the-shelf `d3.cluster()`) plants
every leaf at the same spot and draws a full-length stem up to wherever it
first merges. That stem carries no information beyond "this leaf exists" --
the only real data point is the HEIGHT at which it stops being alone -- and
for a cluster that stays distinct for a long stretch of the tree, the long
uninterrupted line reads as if something continuous were happening along its
whole length, when nothing was measured there at all.

This module drops that stem for leaves specifically (internal branches are
untouched, drawn exactly as usual) and instead places a coloured circle
directly at the leaf's own first-merge height, taken straight off the `Z`
linkage matrix :func:`~stripesankey.mr_consensus.coarse_linkage` builds --
no third distance, no new computation, just a different rendering choice for
a number the tree already carries.

Typical use, docked to the left of a StripeSankey (`orientation="left"`,
the default -- leaves stack top-to-bottom, height grows right-to-left so 0
sits against the diagram it is labelling)::

    import stripesankey.mr_consensus as mrc
    from stripesankey.cluster_dendrogram import ClusterDendrogram, dendrogram_layout

    Cq = mrc.coarse_affinity(Q, labels)
    Z = mrc.coarse_linkage(Cq)
    order = mrc.leaf_plot_order(Z, list(Cq.index))
    palette = {c: mrc.oklch_to_hex(h) for c, h in
              mrc.lineage_palette(mrc.coarse_distance(Cq), order).items()}

    legend = ClusterDendrogram(
        layout=dendrogram_layout(Z, list(Cq.index), colors=palette,
                                 sizes=mrc.coarse_sizes(labels).to_dict()),
        width=170, height=500)

    sankey = k_evaluation(output_path, plot="stripesankey", cluster_colors=palette)
    mo.hstack([legend, sankey], justify="start", align="start", gap=0)   # marimo
"""
import anywidget
import scipy.cluster.hierarchy as sch
import traitlets


def dendrogram_layout(Z, leaf_ids, colors=None, labels=None, sizes=None):
    """Convert a scipy-format linkage matrix into JSON-able draw instructions.

    Args:
        Z: (n-1, 4) linkage matrix, e.g. from
            :func:`~stripesankey.mr_consensus.coarse_linkage`.
        leaf_ids: the id Z's leaf position ``i`` refers to, for every
            ``i in range(n)`` -- same list passed when Z was built.
        colors: optional ``{leaf_id: hex}``.
        labels: optional ``{leaf_id: str}``, defaults to ``f"C{id}"``.
        sizes: optional ``{leaf_id: value}`` drawn as circle radius --
            typically cluster size (:func:`~stripesankey.mr_consensus.coarse_sizes`),
            the thing a reader looks for first in a node. A per-leaf scale
            like self-cohesion (``Cq``'s own diagonal) can go here too, but
            stacking it onto the SAME circle that already encodes identity
            (colour) and persistence (position) asks a viewer to decode
            three things from one shape; prefer a separate table for it
            unless size really is the least important of the three.

    Returns:
        ``{"n", "leaves": [{"pos","id","x","y","size","color","label"}, ...],
        "links": [{"x1","y1","x2","y2"}, ...], "root_y"}``. ``x`` is an
        integer leaf slot (0..n-1) in the SAME left-to-right order scipy's
        own dendrogram would draw them.
    """
    n = len(leaf_ids)
    colors = colors or {}
    labels = labels or {}
    sizes = sizes or {}

    dn = sch.dendrogram(Z, no_plot=True, labels=[str(i) for i in range(n)])
    leaf_order = [int(s) for s in dn["ivl"]]          # positional idx, left-to-right
    x_of = {pos: float(slot) for slot, pos in enumerate(leaf_order)}

    active_x = dict(x_of)          # node id (leaf or merge) -> x
    y_of = {}                      # MERGE-NODE id -> its own height
    leaf_first_h = {}              # leaf positional idx -> height of ITS first merge
    links = []
    next_id = n

    for idx1, idx2, height, _size in Z:
        idx1, idx2 = int(idx1), int(idx2)
        height = float(height)
        x1, x2 = active_x[idx1], active_x[idx2]
        for child, xc in ((idx1, x1), (idx2, x2)):
            if child < n:
                leaf_first_h[child] = height       # leaf: no stem drawn, see below
            else:
                links.append({"x1": xc, "y1": y_of[child], "x2": xc, "y2": height})
        links.append({"x1": x1, "y1": height, "x2": x2, "y2": height})  # the U's bar
        active_x[next_id] = (x1 + x2) / 2.0
        y_of[next_id] = height
        next_id += 1

    leaves = [{
        "pos": i, "id": leaf_ids[i], "x": x_of[i], "y": leaf_first_h[i],
        "size": sizes.get(leaf_ids[i]),
        "color": colors.get(leaf_ids[i], "#4e79a7"),
        "label": labels.get(leaf_ids[i], f"C{leaf_ids[i]}"),
    } for i in range(n)]

    return {"n": n, "leaves": leaves, "links": links, "root_y": float(Z[-1][2])}


class ClusterDendrogram(anywidget.AnyWidget):
    """Renders the output of :func:`dendrogram_layout` with D3.

    ``orientation``: ``"left"`` (default) -- leaves stacked top-to-bottom,
    height grows RIGHT-to-LEFT (height 0 at the right edge, the root
    farthest left), the standard "row dendrogram docked to the left of a
    heatmap" convention -- meant to sit immediately left of a StripeSankey.
    ``"bottom"`` -- leaves along x, tree grows up, the orientation of the
    StripeSankey's own built-in legend band, for a figure that already
    reserves space below rather than beside the diagram.
    """

    layout = traitlets.Dict({}).tag(sync=True)
    width = traitlets.Int(170).tag(sync=True)
    height = traitlets.Int(500).tag(sync=True)
    y_label = traitlets.Unicode("height").tag(sync=True)
    size_label = traitlets.Unicode("").tag(sync=True)
    title = traitlets.Unicode("").tag(sync=True)
    orientation = traitlets.Unicode("left").tag(sync=True)

    _esm = """
    import * as d3 from "https://esm.sh/d3@7.9.0";

    function render({ model, el }) {
      function draw() {
        el.innerHTML = "";
        const layout = model.get("layout");
        const W = model.get("width"), H = model.get("height");
        const title = model.get("title"), yLabel = model.get("y_label");
        const vertical = model.get("orientation") === "left";
        if (!layout.leaves) return;

        const margin = vertical
          ? { top: title ? 34 : 10, right: 46, bottom: 24, left: 10 }
          : { top: title ? 34 : 14, right: 24, bottom: 34, left: 56 };
        const iw = W - margin.left - margin.right, ih = H - margin.top - margin.bottom;

        const svg = d3.select(el).append("svg").attr("width", W).attr("height", H)
          .style("font-family", "sans-serif").style("background", "#fff");
        const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

        if (title) {
          svg.append("text").attr("x", W / 2).attr("y", 20).attr("text-anchor", "middle")
            .attr("font-size", 13).text(title);
        }

        const n = layout.n;
        // linear, NOT scalePoint: internal nodes sit at midpoints (1.5, 2.25, ...)
        // that are never exact members of the leaf-slot domain, and scalePoint
        // maps anything off-domain to undefined -- every branch above the
        // first merge would silently vanish.
        const cat = d3.scaleLinear().domain([-0.5, n - 0.5])
          .range(vertical ? [0, ih] : [0, iw]);
        const yMax = layout.root_y * 1.1 || 1;
        // height=0 always ends up at the edge nearest the leaves: the bottom
        // in "bottom" mode, the RIGHT edge in "left" mode (leaves dock against
        // whatever sits to their right -- the sankey).
        const hgt = d3.scaleLinear().domain([0, yMax])
          .range(vertical ? [iw, 0] : [ih, 0]);
        // (px, py) for a data point at leaf-slot `xs`, height `hv`.
        const pos = (xs, hv) => vertical ? [hgt(hv), cat(xs)] : [cat(xs), hgt(hv)];

        const axisG = g.append("g");
        if (vertical) {
          axisG.attr("transform", `translate(0,${ih})`)
            .call(d3.axisBottom(hgt).ticks(4).tickSize(-ih))
            .call(sel => sel.selectAll("line").attr("stroke", "#eee"))
            .call(sel => sel.select(".domain").attr("stroke", "#333"));
        } else {
          axisG.call(d3.axisLeft(hgt).ticks(5).tickSize(-iw))
            .call(sel => sel.selectAll("line").attr("stroke", "#eee"))
            .call(sel => sel.select(".domain").attr("stroke", "#333"))
            .append("text").attr("x", -margin.left + 10).attr("y", -8).attr("fill", "#000")
            .attr("font-size", 10).attr("text-anchor", "start").text(yLabel);
        }

        // height = 0 reference line -- everything past it is real merge
        // structure; nothing on the other side is drawn, on purpose (no leaf
        // ever "starts" there).
        const [zx1, zy1] = pos(-0.5, 0), [zx2, zy2] = pos(n - 0.5, 0);
        g.append("line").attr("x1", zx1).attr("y1", zy1).attr("x2", zx2).attr("y2", zy2)
          .attr("stroke", "#ccc").attr("stroke-dasharray", "3,3");

        g.selectAll("line.branch").data(layout.links).join("line")
          .attr("class", "branch")
          .attr("x1", d => pos(d.x1, d.y1)[0]).attr("y1", d => pos(d.x1, d.y1)[1])
          .attr("x2", d => pos(d.x2, d.y2)[0]).attr("y2", d => pos(d.x2, d.y2)[1])
          .attr("stroke", "#999").attr("stroke-width", 1.6);

        // circle radius is a SECOND, independent scale (e.g. cluster size) --
        // only built when every leaf actually carries a `size`, so a plain
        // call with no `sizes=` given still draws plain, equal-sized circles.
        const sizeVals = layout.leaves.map(d => d.size);
        const hasSize = sizeVals.every(v => v !== null && v !== undefined);
        const rMax = vertical ? 11 : 15;
        const r = hasSize
          ? d3.scaleSqrt().domain(d3.extent(sizeVals)).range([5, rMax])
          : () => (vertical ? 7 : 9);

        const leaf = g.selectAll("g.leaf").data(layout.leaves).join("g")
          .attr("class", "leaf")
          .attr("transform", d => { const [px, py] = pos(d.x, d.y); return `translate(${px},${py})`; });
        leaf.append("circle").attr("r", d => r(d.size))
          .attr("fill", d => d.color).attr("stroke", "#222").attr("stroke-width", 1.2);
        leaf.append("title").text(d => `${d.label}: first merges at height ${d.y.toFixed(4)}`
          + (hasSize ? `, own scale ${d.size.toFixed(3)}` : ""));
        if (vertical) {
          leaf.append("text").attr("x", 14).attr("y", 3).attr("text-anchor", "start")
            .attr("font-size", 9).text(d => d.label);
        } else {
          leaf.append("text").attr("y", 22).attr("text-anchor", "middle")
            .attr("font-size", 10).text(d => d.label);
        }

        if (hasSize && !vertical) {
          svg.append("text").attr("x", W - margin.right).attr("y", H - 6)
            .attr("text-anchor", "end").attr("font-size", 9).attr("fill", "#666")
            .text("circle size → " + (model.get("size_label") || "own scale"));
        }
      }
      draw();
      model.on("change:layout", draw);
      model.on("change:width", draw);
      model.on("change:height", draw);
      model.on("change:title", draw);
      model.on("change:y_label", draw);
      model.on("change:size_label", draw);
      model.on("change:orientation", draw);
    }
    export default { render };
    """
