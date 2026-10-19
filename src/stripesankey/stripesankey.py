import anywidget
import traitlets

class StripeSankeyInline(anywidget.AnyWidget):
    _esm = r"""
    import * as d3 from "https://esm.sh/d3@7.9.0";

    // ---- column headings -------------------------------------------------
    // Every renderer below indexes its columns by an integer, and that integer
    // is normally K -- so the heading reads "K = 3". The `column_labels` trait
    // keeps the integer as a plain column INDEX and prints something else over
    // it, which is what lets a non-K x-axis reuse this file's layout untouched:
    // see `lda4microbiome.modes`, whose columns are replicate RUNS at one fixed
    // K. `__COLLAB` is refreshed on entry to every renderer and at the top of
    // every interactive redraw, so a `draw()` after a click still reads the
    // widget it belongs to rather than whichever rendered last.
    let __COLLAB = {};
    let __COLSUB = {};
    const __setColLabels = model => { __COLLAB = model.get("column_labels") || {};
                                      __COLSUB = model.get("column_sublabels") || {}; };
    const __colLabel = (k, fb) => {
      const v = __COLLAB[String(k)];
      return (v === undefined || v === null)
        ? (fb !== undefined ? fb : "K = " + k)
        : String(v);
    };
    // The optional SECOND heading line (`column_sublabels`), small and grey under
    // the main one. It QUALIFIES a column rather than naming it -- the mode axis
    // puts "major mode | rep. k6r2 | 5 of 8 runs" there -- so every caller that
    // wants only the name (tooltips, focus banners) keeps reading __colLabel and
    // is untouched. "" / missing = no second line, and the renderer then keeps
    // its original one-line top margin.
    const __colSub = k => {
      const v = __COLSUB[String(k)];
      return (v === undefined || v === null) ? "" : String(v);
    };
    const __hasColSubs = () => Object.values(__COLSUB).some(v => v);

    // ---- SVG text inside a fixed-width column ----------------------------
    // The left-docked legends live in a narrow column (LEGEND_W) with the
    // diagram right against it, so a long field name or category label would
    // run over the ribbons. `__shrinkText` steps the size down (never past
    // `minPx`) until the string fits; `__clipText` keeps the size and
    // truncates with an ellipsis, carrying the full string in a <title> so
    // hovering still shows it. Width comes from the rendered glyphs, with a
    // per-size estimate as fallback for the pre-attach render where
    // getComputedTextLength() is unavailable (it reports 0 or throws).
    function __textW(sel, px) {
      let w = 0;
      try { w = sel.node().getComputedTextLength(); } catch (e) { w = 0; }
      return w || (sel.text() || "").length * px * 0.55;
    }
    function __clipText(sel, maxW, px) {
      const full = sel.text();
      if (__textW(sel, px) <= maxW) return;
      let s = full;
      while (s.length > 1 && __textW(sel, px) > maxW) { s = s.slice(0, -1); sel.text(s + "\u2026"); }
      sel.append("title").text(full);        // after .text(), which clears children
    }
    function __shrinkText(sel, maxW, maxPx, minPx) {
      let px = maxPx;
      sel.style("font-size", px + "px");
      while (px > minPx && __textW(sel, px) > maxW) { px -= 1; sel.style("font-size", px + "px"); }
      __clipText(sel, maxW, px);
      return px;
    }

    // ---- in-output export toolbar: SVG/PNG of the LIVE svg (captures current
    // interactive state — splits, selections, focus). Mounted per render. --------
    const __SVGNS = "http://www.w3.org/2000/svg";
    function __inlineStyles(src, dst) {
      const s = getComputedStyle(src);
      ["fill","stroke","stroke-width","opacity","fill-opacity","stroke-opacity","font","font-size","font-family","font-weight","text-anchor","dominant-baseline"]
        .forEach(p => { const v = s.getPropertyValue(p); if (v) dst.style.setProperty(p, v); });
      const sc = src.children, dc = dst.children;
      for (let i = 0; i < sc.length; i++) __inlineStyles(sc[i], dc[i]);
    }
    function __buildSVG(el) {
      const svgs = [...el.querySelectorAll("svg")].filter(s => !s.closest(".__exp"));
      if (!svgs.length) return null;
      const root = document.createElementNS(__SVGNS, "svg"); root.setAttribute("xmlns", __SVGNS);
      let xoff = 0, maxH = 0;
      svgs.forEach((svg, i) => {
        const w = +svg.getAttribute("width") || svg.clientWidth || 320;
        const h = +svg.getAttribute("height") || svg.clientHeight || 220;
        const clone = svg.cloneNode(true); __inlineStyles(svg, clone);
        clone.setAttribute("x", xoff); clone.setAttribute("y", 0); clone.setAttribute("width", w); clone.setAttribute("height", h);
        root.appendChild(clone); xoff += w + (i < svgs.length - 1 ? 14 : 0); maxH = Math.max(maxH, h);
      });
      root.setAttribute("width", xoff); root.setAttribute("height", maxH); root.setAttribute("viewBox", `0 0 ${xoff} ${maxH}`);
      const bg = document.createElementNS(__SVGNS, "rect");
      bg.setAttribute("width", xoff); bg.setAttribute("height", maxH); bg.setAttribute("fill", "#ffffff");
      root.insertBefore(bg, root.firstChild);
      return { root, w: xoff, h: maxH };
    }
    function __ser(root) { return '<?xml version="1.0" encoding="UTF-8"?>' + new XMLSerializer().serializeToString(root); }
    function __trig(url, fn) { const a = document.createElement("a"); a.href = url; a.download = fn; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); }
    function __stamp() { const d = new Date(), p = n => String(n).padStart(2, "0"); return `${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`; }
    function __dl(el, name, fmt) {
      const ex = __buildSVG(el); if (!ex) { alert("nothing to export yet"); return; }
      const xml = __ser(ex.root);
      if (fmt === "svg") { __trig(URL.createObjectURL(new Blob([xml], { type: "image/svg+xml;charset=utf-8" })), `${name}_${__stamp()}.svg`); return; }
      const url = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
      const img = new Image();
      img.onload = () => { const c = document.createElement("canvas"); c.width = Math.round(ex.w * 3); c.height = Math.round(ex.h * 3);
        const ctx = c.getContext("2d"); ctx.setTransform(3, 0, 0, 3, 0, 0); ctx.drawImage(img, 0, 0);
        c.toBlob(b => __trig(URL.createObjectURL(b), `${name}_${__stamp()}.png`), "image/png"); };
      img.onerror = () => alert("PNG export failed - try SVG."); img.src = url;
    }
    function __mountExport(el, name) {
      const old = el.querySelector(":scope > .__exp"); if (old) old.remove();
      if (getComputedStyle(el).position === "static") el.style.position = "relative";
      const bar = document.createElement("div"); bar.className = "__exp";
      bar.style.cssText = "position:absolute;top:6px;right:8px;display:flex;gap:4px;z-index:50";
      const mk = (t, fmt) => { const b = document.createElement("button"); b.textContent = t;
        b.style.cssText = "font:11px sans-serif;border:1px solid #ccc;background:#fff;color:#333;border-radius:5px;padding:2px 7px;cursor:pointer;opacity:.7";
        b.onmouseenter = () => b.style.opacity = 1; b.onmouseleave = () => b.style.opacity = .7;
        b.onclick = e => { e.stopPropagation(); __dl(el, name, fmt); }; bar.appendChild(b); };
      mk("⬇SVG", "svg"); mk("⬇PNG", "png");
      el.appendChild(bar);
    }

    // Place a floating element (tooltip / taxa panel) so it is ALWAYS fully
    // inside the widget box: offer it the bottom-right of the cursor, FLIP to the
    // opposite side on whichever axis would spill, then clamp. That is why a node
    // near the bottom edge gets its tooltip above it rather than cut off.
    // Measure after the content is set, or the size is stale.
    function __placeFloat(node, e, boxW, boxH, pad) {
      const p = (pad == null) ? 14 : pad;
      const w = node.offsetWidth, h = node.offsetHeight;
      let x = e.offsetX + p, y = e.offsetY + p;
      if (x + w > boxW - 4) x = e.offsetX - w - p;     // flip to the left
      if (y + h > boxH - 4) y = e.offsetY - h - p;     // flip above
      node.style.left = Math.max(4, Math.min(x, boxW - w - 4)) + "px";
      node.style.top  = Math.max(4, Math.min(y, boxH - h - 4)) + "px";
    }

    // ---- per-component annotations, supplied by the caller ----------------
    // `lc_annotations` = {"<k>": {"<lc>": [[label, weight], ...]}}, best first.
    // The library never reads a feature table: what the rows are (genera,
    // genes, words) and which ones are left out is the caller's business.
    // `annotation_label` says what they are ("Genus"); `component_label` what
    // a component is called ("LC" by default). A component WITH rows gets a
    // two-part caption (`__twoPartCaption`): its component part keeps the
    // whole-node selection every caption has, its annotation part opens a
    // pinned popup listing the rows and leaves the selection alone. Shared by
    // cluster_prox and meta_sankey.
    function __annotations(el, model, width, height) {
        const ANN = model.get("lc_annotations") || {};
        const LABEL = model.get("annotation_label") || "";
        const COMP = model.get("component_label") || "LC";
        const rowsOf = (k, lc) => ((ANN[String(k)] || {})[String(lc)]) || [];
        const panel = d3.select(el).append("div").attr("class", "__annot")
            .style("position", "absolute").style("display", "none")
            .style("background", "#111").style("color", "#fff")
            .style("padding", "10px 13px").style("border-radius", "8px")
            .style("box-shadow", "0 4px 16px rgba(0,0,0,.35)")
            .style("font", "14px sans-serif").style("z-index", 20)
            .on("click", e => e.stopPropagation());    // a click inside never clears the selection
        let shown = null;                              // "k:lc" of the open popup
        const hide = () => { panel.style("display", "none"); shown = null; };
        function toggle(k, lc, e) {
            const rows = rowsOf(k, lc);
            if (!rows.length) return;
            const key = k + ":" + lc;
            if (shown === key) { hide(); return; }     // re-click = dismiss
            shown = key;
            const mx = d3.max(rows, r => +r[1]) || 1, BAR = 150;
            let html = `<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px">`
                     + `<b style="font-size:15px">K${k} ${COMP}${lc}</b>`
                     + `<span style="opacity:.6">top ${rows.length}${LABEL ? " " + LABEL : ""}</span>`
                     + `<span class="__annotclose" style="margin-left:auto;cursor:pointer;opacity:.6;font-size:16px">\u00d7</span></div>`;
            rows.forEach(([name, w]) => {
                const bw = Math.max(3, (+w / mx) * BAR);
                html += `<div style="display:flex;align-items:center;gap:9px;margin:5px 0;line-height:1">`
                      +  `<span style="display:inline-block;width:160px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${name}">${name}</span>`
                      +  `<span style="display:inline-block;height:15px;width:${bw.toFixed(0)}px;background:#5b9bd5;border-radius:3px"></span>`
                      +  `<span style="opacity:.85;white-space:nowrap">${(+w).toFixed(3)}</span></div>`;
            });
            panel.html(html).style("display", "block");
            __placeFloat(panel.node(), e, width, height);  // flip/clamp into the widget box
            panel.select(".__annotclose").on("click", ev => { ev.stopPropagation(); hide(); });
        }
        return {
            COMP, hide, toggle,
            has: (k, lc) => rowsOf(k, lc).length > 0,
            // the annotation part's text: the top row's name alone -- what it is
            // (`annotation_label`) is said in the tooltip and the popup heading
            headline: (k, lc) => { const r = rowsOf(k, lc); return r.length ? String(r[0][0]) : ""; },
            tip: (k, lc) => { const r = rowsOf(k, lc); if (!r.length) return "";
                return `<b>K${k} ${COMP}${lc}</b> \u00b7 top ${LABEL || "annotation"}: <b>${r[0][0]}</b> (${(+r[0][1]).toFixed(3)})`
                     + `<br><span style="opacity:.7">click for the top ${r.length}${LABEL ? " " + LABEL : ""}</span>`; },
        };
    }

    // Two-part caption under a node: "{COMP}{lc}" (bold -- the whole-node
    // handle) then "\u00b7 {headline}" (lighter -- the annotation handle), the
    // pair centred on x within `maxW`. The headline gives way first (clipped
    // with an ellipsis, full text in a <title>); when not even a few letters
    // fit it becomes an "\u24d8". Returns { comp, ann } for the caller to wire.
    function __twoPartCaption(parent, x, y, compText, annText, maxW, fill) {
        const grp = parent.append("g");
        const comp = grp.append("text").attr("x", 0).attr("y", y)
            .style("font-size", "12px").style("font-weight", "bold").style("fill", fill).text(compText);
        const compW = __textW(comp, 12), GAP = 4;
        const ann = grp.append("text").attr("x", compW + GAP).attr("y", y)
            .style("font-size", "11px").style("font-weight", "normal")
            .style("fill", fill === "#333" ? "#6b7280" : fill).text("\u00b7 " + annText);
        const room = maxW - compW - GAP;
        if (room < 28) ann.text("\u24d8");
        else __clipText(ann, room, 11);
        grp.attr("transform", `translate(${x - (compW + GAP + __textW(ann, 11)) / 2},0)`);
        return { comp, ann };
    }

    function render({ model, el }) {
        el.innerHTML = '';

        // hard_sankey (hard clustering labels) is standalone: it reads `hard_data`,
        // NOT sankey_data, so it must dispatch BEFORE the sankey_data.nodes guard.
        if (model.get("color_mode") === 'hard_sankey') {
            el.style.position = 'relative';
            drawHardSankeyAll(el, model);
            const rerun = () => { if (model.get("color_mode") === 'hard_sankey') drawHardSankeyAll(el, model); };
            model.on("change:hard_data", rerun);
            model.on("change:min_flow_samples", rerun);
            model.on("change:width", rerun);
            model.on("change:height", rerun);
            return;
        }

        const data = model.get("sankey_data");
        const width = model.get("width");
        const height = model.get("height");
        const colorSchemes = model.get("color_schemes");
        const selectedFlow = model.get("selected_flow");
        const metricMode = model.get("metric_mode");
        const metricConfig = model.get("metric_config");

        // `nodes`/`flows` are what the K-axis Sankey renderers consume. The
        // theta-driven renderers below (cluster_prox, small_multiples,
        // meta_sankey) rebuild their own census from `theta` + `clusters` and
        // never read `nodes`, so requiring it here would reject a perfectly
        // complete payload -- which is exactly what a run-axis payload is
        // (`lda4microbiome.modes.ModeAnalysis.payload`: theta per RUN, no
        // precomputed K-to-K flows to carry). Each of those renderers prints
        // its own message naming what it is actually missing.
        const THETA_DRIVEN = ['cluster_prox', 'small_multiples', 'meta_sankey'];
        const hasNodes = !!(data && data.nodes && Object.keys(data.nodes).length);
        const hasTheta = !!(data && data.theta && Object.keys(data.theta).length);
        if (!hasNodes && !(THETA_DRIVEN.includes(model.get("color_mode")) && hasTheta)) {
            el.innerHTML = '<div style="padding: 20px; text-align: center; font-family: sans-serif;">No data available. Please load your processed data first.</div>';
            return;
        }

        // cluster_prox (OKLCH lineage) has its own self-contained renderer
        if (model.get("color_mode") === 'cluster_prox') {
            el.style.position = 'relative';
            drawClusterProxAll(el, model);
            const rerun = () => { if (model.get("color_mode") === 'cluster_prox') drawClusterProxAll(el, model); };
            model.on("change:sankey_data", rerun);
            model.on("change:k_list", rerun);
            model.on("change:probability_thresholds", rerun);
            model.on("change:min_flow_samples", rerun);
            model.on("change:metadata", rerun);
            model.on("change:hover_field", rerun);
            model.on("change:gradient", rerun);
            model.on("change:gradient_spread", rerun);
            model.on("change:gradient_light", rerun);
            model.on("change:node_width", rerun);
            model.on("change:layout_effort", rerun);
            model.on("change:cluster_colors", rerun);
            model.on("change:cluster_legend", rerun);
            model.on("change:column_labels", rerun);
            model.on("change:lc_annotations", rerun);
            model.on("change:annotation_label", rerun);
            model.on("change:component_label", rerun);
            return;
        }

        // small_multiples — the same Sankey drawn N times, one colouring each
        if (model.get("color_mode") === 'small_multiples') {
            el.style.position = 'relative';
            drawSmallMultiplesAll(el, model);
            const rerun = () => { if (model.get("color_mode") === 'small_multiples') drawSmallMultiplesAll(el, model); };
            model.on("change:sankey_data", rerun);
            model.on("change:k_list", rerun);
            model.on("change:panels", rerun);
            model.on("change:panel_cols", rerun);
            model.on("change:layout_effort", rerun);
            model.on("change:metadata", rerun);
            model.on("change:gradient", rerun);
            model.on("change:gradient_spread", rerun);
            model.on("change:gradient_light", rerun);
            model.on("change:width", rerun);
            model.on("change:height", rerun);
            model.on("change:cluster_colors", rerun);
            model.on("change:component_label", rerun);
            return;
        }

        // meta_sankey (metadata-encoded, no clustering) — separate renderer
        if (model.get("color_mode") === 'meta_sankey') {
            el.style.position = 'relative';
            drawMetaSankeyAll(el, model);
            const rerun = () => { if (model.get("color_mode") === 'meta_sankey') drawMetaSankeyAll(el, model); };
            model.on("change:sankey_data", rerun);
            model.on("change:k_list", rerun);
            model.on("change:probability_thresholds", rerun);
            model.on("change:metadata", rerun);
            model.on("change:hover_field", rerun);
            model.on("change:lc_annotations", rerun);
            model.on("change:annotation_label", rerun);
            model.on("change:component_label", rerun);
            return;
        }

        // Create SVG
        const svg = d3.select(el)
            .append("svg")
            .attr("width", width)
            .attr("height", height)
            .style("background", "#fafafa")
            .style("border", "1px solid #ddd");

        // Adjust top margin based on color mode - 'metrics' mode needs more space for perplexity bars
        const topMargin = model.get("color_mode") === 'metrics' ? 120 : 60;
        const margin = { top: topMargin, right: 150, bottom: 60, left: 100 }; // Increased right margin for tooltips
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;

        const g = svg.append("g")
            .attr("transform", `translate(${margin.left}, ${margin.top})`);

        // Process data for visualization
        const processedData = processDataForVisualization(data);

        // Calculate metric scales if in metric mode
        let metricScales = null;
        if (metricMode) {
            metricScales = calculateMetricScales(processedData, data, metricConfig);
        }

        // Draw the actual sankey diagram
        drawSankeyDiagram(g, processedData, chartWidth, chartHeight, colorSchemes, selectedFlow, model, metricMode, metricScales, metricConfig);

        // No metric legend - removed to avoid clutter

        // Update on data change
        model.on("change:sankey_data", () => {
            const newData = model.get("sankey_data");
            if (newData && Object.keys(newData).length > 0) {
                const newProcessedData = processDataForVisualization(newData);
                let newMetricScales = null;
                if (model.get("metric_mode")) {
                    newMetricScales = calculateMetricScales(newProcessedData, newData, model.get("metric_config"));
                }
                svg.selectAll("*").remove();
                const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                drawSankeyDiagram(newG, newProcessedData, chartWidth, chartHeight, colorSchemes, model.get("selected_flow"), model, model.get("metric_mode"), newMetricScales, model.get("metric_config"));
                // No metric legend - removed
            }
        });

        // Update on metric mode change
        model.on("change:metric_mode", () => {
            const newMetricMode = model.get("metric_mode");
            let newMetricScales = null;
            if (newMetricMode) {
                newMetricScales = calculateMetricScales(processedData, data, model.get("metric_config"));
            }
            
            // Recalculate margin based on new color mode
            const newTopMargin = model.get("color_mode") === 'metrics' ? 120 : 60;
            const newMargin = { top: newTopMargin, right: 150, bottom: 60, left: 100 };
            const newChartWidth = width - newMargin.left - newMargin.right;
            const newChartHeight = height - newMargin.top - newMargin.bottom;
            
            svg.selectAll("*").remove();
            const newG = svg.append("g").attr("transform", `translate(${newMargin.left}, ${newMargin.top})`);
            drawSankeyDiagram(newG, processedData, newChartWidth, newChartHeight, colorSchemes, model.get("selected_flow"), model, newMetricMode, newMetricScales, model.get("metric_config"));
            // No metric legend - removed
        });

        // Update on selected flow change
        model.on("change:selected_flow", () => {
            const newSelectedFlow = model.get("selected_flow");
            svg.selectAll("*").remove();
            const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
            let newMetricScales = null;
            if (model.get("metric_mode")) {
                newMetricScales = calculateMetricScales(processedData, data, model.get("metric_config"));
            }
            drawSankeyDiagram(newG, processedData, chartWidth, chartHeight, colorSchemes, newSelectedFlow, model, model.get("metric_mode"), newMetricScales, model.get("metric_config"));
            // No metric legend - removed
        });
    }


    // =====================================================================
    // SHARED VOLUME-ACCURATE GEOMETRY
    //
    // Once node height and ribbon width are the same head count over a full
    // census, the LAYOUT is a pure function of (samples, per-K dominant LC,
    // K range, panel height) — it knows nothing about what determines colour.
    // That is what lets `cluster_prox` and the small-multiples renderer share
    // one geometry and differ only in how a node is CUT: compute the boxes
    // once, then cut and tile them N times with N different grouping
    // functions. Any drift between panels would make the comparison
    // meaningless, so there is deliberately only one copy of this code.
    // =====================================================================

    // dominant LC per sample per K — plain argmax, NO confidence gate, so
    // every sample is placed at every K and each column is a full census
    function __domMapFactory(theta) {
        const cache = {};
        return function (k) {
            if (cache[k]) return cache[k];
            const th = theta[String(k)] || {}, out = {};
            for (const s in th) { const v = th[s]; let bi = 0, bv = -1;
                for (let i = 0; i < v.length; i++) if (v[i] > bv) { bv = v[i]; bi = i; }
                out[s] = { mc: bi, p: bv }; }
            return (cache[k] = out);
        };
    }

    // ===================================================================
    // Column stack order: minimise sample-weighted ribbon crossings.
    //
    // The old rule was one forward pass — first column by mean consensus-cluster
    // rank, every later column by barycentre against the one before it. That is
    // a greedy local optimum and it cannot take anything back: a choice made at
    // the first column stands even when the fourth shows it was wrong. On the
    // run axis that is exactly what went wrong. At K=7 of 1kg_p3 the M0 columns
    // put LC0 (91) above LC2 (192); the next mode merges LC0 with LC6 (346) into
    // one node that lands BELOW the one LC2 feeds, so those two ribbons had to
    // cross. Swapping LC0 and LC2 in all four M0 columns removes the crossing
    // and costs nothing — but no forward pass can make that move, because by the
    // time the evidence arrives the first column is already drawn.
    //
    // So: keep that pass as the seed, then search. Three stages, each one only
    // ever accepted if it crosses strictly LESS than the best so far, which is
    // what makes this safe — a layout that was already clean stays exactly as it
    // was, bit for bit.
    //
    //   1. polish     alternating up/down barycentre sweeps, with every column
    //                 re-ordered optimally against its two neighbours in between
    //   2. re-seed    the same, started from each column in turn rather than
    //                 from the first — a different greedy path, different optimum
    //   3. kick       perturb the best answer, re-polish, keep it if it improved
    //                 (iterated local search, fixed PRNG seed)
    //
    // Determinism matters here — small-multiple panels share one geometry and
    // would drift apart if the layout depended on machine speed — so the search
    // is metered in edge-pair comparisons, not wall-clock time, and every
    // tie-break falls through to barycentre, mean rank, LC id in that order.
    //
    // `effort` scales the budget: 0 returns the seed untouched (the pre-search
    // behaviour), 1 is the default (a few tens of ms), 10-20 is for a figure
    // being exported once, where a second of search is free.
    // ===================================================================
    function __orderColumns(COLS, domMap, SAMPLES, kList, meanRankOf, centresOf, ih, effort) {
        const NC = COLS.length;
        const seedOrder = () => {                       // the shipped forward pass
            const o = COLS.map(a => a.slice());
            o[0] = o[0].slice().sort((a, b) => (mr(0, a) - mr(0, b)) || (a.mc - b.mc));
            for (let i = 1; i < NC; i++) barySort(o, i, -1);
            return o; };

        // Flows between consecutive columns, collapsed to {a, b, n}: the census
        // is per sample but nothing below needs a sample, only how many take
        // each route. Everything after this point is O(edges), not O(samples).
        const EDGES = [];
        for (let i = 0; i < NC - 1; i++) {
            const da = domMap(kList[i]), db = domMap(kList[i + 1]), w = {};
            SAMPLES.forEach(s => { const key = da[s].mc + "|" + db[s].mc; w[key] = (w[key] || 0) + 1; });
            EDGES.push(Object.entries(w).map(([key, n]) => {
                const p = key.split("|"); return { a: +p[0], b: +p[1], n }; })); }
        const bySrc = EDGES.map(() => ({})), byTgt = EDGES.map(() => ({}));
        EDGES.forEach((E, i) => E.forEach(e => {
            (bySrc[i][e.a] = bySrc[i][e.a] || []).push(e);
            (byTgt[i][e.b] = byTgt[i][e.b] || []).push(e); }));
        // mean rank once per node, not once per sort comparison
        const MR = {}; COLS.forEach((col, i) => col.forEach(o => MR[i + ":" + o.mc] = meanRankOf(o)));
        const mr = (i, o) => MR[i + ":" + o.mc];

        const BUDGET = Math.max(0, Math.min(40, +effort || 0)) * 3e6;
        let work = 0; const spent = () => work >= BUDGET;
        const posOf = arr => { const p = {}; arr.forEach((o, j) => p[o.mc] = j); return p; };
        const clone = o => o.map(a => a.slice());

        // ---- the objective -------------------------------------------------
        // Two ribbons cross when their endpoints sit in opposite order. A
        // crossing between two thick ribbons is a visible X and one between two
        // hairlines is not, so each crossing pair is weighted by the product of
        // its sample counts — the same quantity the eye reads as crossed area.
        // Ribbons leaving the SAME node never count: they are tiled inside the
        // node by target centre (see __buildRibbons) and cannot cross. Counted
        // as weighted inversions with a Fenwick tree, O(E log m) per boundary.
        function boundaryCross(i, posA, posB, mB) {
            const E = EDGES[i]; if (E.length < 2) return 0;
            work += E.length * 4;
            const blocks = {};
            E.forEach(e => { const p = posA[e.a]; (blocks[p] = blocks[p] || []).push(e); });
            const keys = Object.keys(blocks).map(Number).sort((x, y) => x - y);
            const bit = new Float64Array(mB + 1); let tot = 0, x = 0;
            const add = (p, v) => { for (let j = p + 1; j <= mB; j += j & -j) bit[j] += v; };
            const pre = p => { let s = 0; for (let j = p + 1; j > 0; j -= j & -j) s += bit[j]; return s; };
            keys.forEach(p => { const blk = blocks[p];
                blk.forEach(e => { x += e.n * (tot - pre(posB[e.b])); });   // already placed, strictly above
                blk.forEach(e => { add(posB[e.b], e.n); tot += e.n; }); });
            return x; }
        function crossAll(ord) { let x = 0;
            for (let i = 0; i < NC - 1; i++)
                x += boundaryCross(i, posOf(ord[i]), posOf(ord[i + 1]), ord[i + 1].length);
            return x; }

        // What it costs to put u above v rather than the other way round, at
        // both of column i's boundaries. Only these two nodes' own flows can
        // change, so a swap or a move is scored exactly without recounting the
        // boundary — that is what makes the local search cheap enough to run
        // inside every sweep.
        function pairCost(i, u, v, pR, pL) {
            let uv = 0, vu = 0;
            if (pR) { const eu = bySrc[i][u.mc], ev = bySrc[i][v.mc];
                if (eu && ev) { work += eu.length * ev.length;
                    for (const a of eu) for (const b of ev) { const d = pR[b.b] - pR[a.b];
                        if (d < 0) uv += a.n * b.n; else if (d > 0) vu += a.n * b.n; } } }
            if (pL) { const eu = byTgt[i - 1][u.mc], ev = byTgt[i - 1][v.mc];
                if (eu && ev) { work += eu.length * ev.length;
                    for (const a of eu) for (const b of ev) { const d = pL[b.a] - pL[a.a];
                        if (d < 0) uv += a.n * b.n; else if (d > 0) vu += a.n * b.n; } } }
            return uv - vu; }                            // < 0: u really does belong above v

        // ---- one column, re-ordered against its neighbours -----------------
        // With both neighbours fixed the column's own cost is a sum over ordered
        // pairs, i.e. a linear ordering problem. Up to DP_MAX nodes that is
        // solved exactly by subset DP (2^m*m, ~50k at m=12); above it, by
        // sliding each node to its best position, which is the same neighbourhood
        // adjacent-swap refinement explores but takes multi-step moves in one go.
        const DP_MAX = 12;
        function columnExact(ord, i, pR, pL) {
            const col = ord[i], m = col.length;
            const M = []; for (let a = 0; a < m; a++) M.push(new Float64Array(m));
            for (let a = 0; a < m; a++) for (let b = a + 1; b < m; b++) {
                const d = pairCost(i, col[a], col[b], pR, pL);
                if (d < 0) M[b][a] = -d; else M[a][b] = d; }    // cost of the WRONG way round
            const score = perm => { let s = 0;
                for (let a = 0; a < m; a++) for (let b = a + 1; b < m; b++) s += M[perm[a]][perm[b]];
                return s; };
            const full = (1 << m) - 1; work += full * m;
            const f = new Float64Array(full + 1).fill(Infinity), ch = new Int8Array(full + 1).fill(-1);
            const row = new Float64Array(m);
            for (let v = 0; v < m; v++) { let s = 0;
                for (let w2 = 0; w2 < m; w2++) if (w2 !== v) s += M[v][w2]; row[v] = s; }
            f[0] = 0;
            for (let S = 0; S <= full; S++) { if (f[S] === Infinity) continue;
                for (let v = 0; v < m; v++) { if (S & (1 << v)) continue;
                    let inS = 0; for (let w2 = 0; w2 < m; w2++) if (S & (1 << w2)) inS += M[v][w2];
                    const nf = f[S] + row[v] - inS, NS = S | (1 << v);
                    if (nf < f[NS] - 1e-9) { f[NS] = nf; ch[NS] = v; } } }
            const out = []; let S = full; while (S) { const v = ch[S]; out.push(v); S &= ~(1 << v); }
            out.reverse();
            const cur = []; for (let j = 0; j < m; j++) cur.push(j);
            if (score(out) < score(cur) - 1e-9) { ord[i] = out.map(j => col[j]); return true; }
            return false; }
        function columnLocal(ord, i, pR, pL) {
            const m = ord[i].length; let moved = false, guard = 0, again = true;
            while (again && guard++ < 6 && !spent()) { again = false;
                for (let a = 0; a < m; a++) {
                    const col = ord[i], u = col[a];
                    let bestD = 0, bestB = a, run = 0;
                    for (let b = a - 1; b >= 0; b--) { run += pairCost(i, u, col[b], pR, pL);
                        if (run < bestD - 1e-9) { bestD = run; bestB = b; } }
                    run = 0;
                    for (let b = a + 1; b < m; b++) { run -= pairCost(i, u, col[b], pR, pL);
                        if (run < bestD - 1e-9) { bestD = run; bestB = b; } }
                    if (bestB !== a) { col.splice(a, 1); col.splice(bestB, 0, u); moved = true; again = true; } } }
            return moved; }
        function refineColumn(ord, i) {
            if (ord[i].length < 2) return false;
            const pR = i < NC - 1 ? posOf(ord[i + 1]) : null, pL = i > 0 ? posOf(ord[i - 1]) : null;
            return ord[i].length <= DP_MAX ? columnExact(ord, i, pR, pL) : columnLocal(ord, i, pR, pL); }
        function refine(ord) { let g = 0, ch = true;
            while (ch && g++ < 4 && !spent()) { ch = false;
                for (let i = 0; i < NC; i++) if (refineColumn(ord, i)) ch = true;
                for (let i = NC - 1; i >= 0; i--) if (refineColumn(ord, i)) ch = true; } }

        // ---- barycentre sweep ----------------------------------------------
        // Same rule as before — a node sits at the mean height of what feeds it —
        // but read off the flow table instead of looping the samples, which is
        // the same number and lets a sweep run hundreds of times instead of once.
        // Barycentres are quantised before comparison: ties are real (two nodes
        // fed 100% by the same neighbour have the same one) and letting float
        // noise break them made the stack order depend on the panel height.
        function barySort(ord, i, dir) {                 // dir -1: from the left
            const j = i + dir, tbl = dir < 0 ? byTgt[i - 1] : bySrc[i];
            const key = dir < 0 ? 'a' : 'b';
            const C2 = centresOf(ord[j]), B = {};
            work += EDGES[dir < 0 ? i - 1 : i].length;
            ord[i].forEach(o => { const es = tbl[o.mc]; let ws = 0, w = 0;
                if (es) es.forEach(e => { const c = C2[e[key]]; if (c != null) { ws += c * e.n; w += e.n; } });
                B[o.mc] = w ? Math.round((ws / w) * 1e6) / 1e6 : ih / 2; });
            ord[i] = ord[i].slice().sort((a, b) =>
                (B[a.mc] - B[b.mc]) || (mr(i, a) - mr(i, b)) || (a.mc - b.mc)); }
        const sweepDown = ord => { for (let i = 1; i < NC; i++) barySort(ord, i, -1); };
        const sweepUp = ord => { for (let i = NC - 2; i >= 0; i--) barySort(ord, i, +1); };

        function seedFrom(pv) {
            const o = COLS.map(a => a.slice());
            o[pv] = o[pv].slice().sort((a, b) => (mr(pv, a) - mr(pv, b)) || (a.mc - b.mc));
            for (let i = pv + 1; i < NC; i++) barySort(o, i, -1);
            for (let i = pv - 1; i >= 0; i--) barySort(o, i, +1);
            return o; }
        // A sweep is allowed to make things worse on the way to something better,
        // so each round is scored and only the best configuration seen survives.
        // Forgetting that was the whole difference between "a bit better" and
        // "no crossings left at all" on the K=7 run axis.
        function polish(o, rounds) {
            refine(o); let b = clone(o), bx = crossAll(o);
            for (let it = 0; it < rounds && bx > 0 && !spent(); it++) {
                sweepUp(o); refine(o); let x = crossAll(o); if (x < bx) { bx = x; b = clone(o); }
                sweepDown(o); refine(o); x = crossAll(o); if (x < bx) { bx = x; b = clone(o); } }
            return { ord: b, x: bx }; }

        // A single column has no boundary and so no crossings: mean rank is the
        // whole answer, the same one the old code gave it.
        if (NC < 2) return { order: COLS.map((a, i) => a.slice()
                .sort((x, y) => (mr(i, x) - mr(i, y)) || (x.mc - y.mc))),
            report: { seed: 0, final: 0, work: 0 } };
        const seed = seedOrder();
        let best = clone(seed), bx = crossAll(seed);
        const seedX = bx;
        if (BUDGET > 0 && bx > 0) {
            const r = polish(clone(seed), 6);
            if (r.x < bx) { bx = r.x; best = r.ord; }
            for (let pv = 1; pv < NC && bx > 0 && !spent(); pv++) {
                const rr = polish(seedFrom(pv), 3);
                if (rr.x < bx) { bx = rr.x; best = rr.ord; } }
            // Iterated local search. The PRNG is seeded with a constant, so the
            // "random" kicks are the same sequence every time this runs.
            let s = 20250923 >>> 0;
            const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
            let cur = clone(best), cx = bx, stall = 0, since = 0;
            while (bx > 0 && !spent() && since < 120) {
                since++;
                const o = clone(cur);
                if (rnd() < 0.45) {                      // reshuffle one column
                    const i = Math.floor(rnd() * NC), a = o[i];
                    for (let j = a.length - 1; j > 0; j--) { const q = Math.floor(rnd() * (j + 1));
                        const t = a[j]; a[j] = a[q]; a[q] = t; } }
                else for (let q = 0; q < 2; q++) {       // or nudge two nodes
                    const i = Math.floor(rnd() * NC), m = o[i].length; if (m < 2) continue;
                    const a = Math.floor(rnd() * m);
                    let b2 = Math.floor(rnd() * m); if (a === b2) b2 = (b2 + 1) % m;
                    const [x] = o[i].splice(a, 1); o[i].splice(b2, 0, x); }
                const rr = polish(o, 2);
                if (rr.x < bx) { bx = rr.x; best = rr.ord; cur = clone(rr.ord); cx = rr.x; stall = 0; since = 0; }
                else if (rr.x <= cx) { cur = rr.ord; cx = rr.x; stall++; }
                else stall++;
                if (stall > 20) { cur = clone(best); cx = bx; stall = 0; } }
        }
        // Reversing EVERY column top-to-bottom leaves the crossing count exactly
        // as it was -- the objective cannot tell the two apart, so the search is
        // free to hand back a figure that reads upside down against the
        // dendrogram legend. Break that tie the way the old first-column rule
        // did: keep whichever orientation puts low consensus-cluster ranks
        // nearer the top, counted over every column and weighted by node size
        // so the big blocks decide it. Only when the search actually moved
        // something: if it found nothing, the seed is handed back untouched.
        let up = bx < seedX ? 0 : 1;
        if (bx < seedX)
            best.forEach((col, i) => { for (let a = 0; a < col.length; a++)
                for (let b = a + 1; b < col.length; b++) {
                    const d = mr(i, col[a]) - mr(i, col[b]);
                    if (d) up += (d < 0 ? 1 : -1) * col[a].total * col[b].total; } });
        if (up < 0) best = best.map(col => col.slice().reverse());

        return { order: best, report: { seed: seedX, final: bx, work } };
    }

    // The census + the node boxes.
    //   domMap    (k) -> {sampleId: {mc, p}}
    //   rankOf    (sampleId) -> a number used to order the FIRST column and to
    //             break barycentre ties (mean consensus-cluster rank)
    //   effort    search budget multiplier for __orderColumns (0 = the plain
    //             forward barycentre pass, 1 = the default)
    // Returns {nodes, nodePos, scale, gap, CAP_H, crossings} with nodePos keyed
    // `k:mc`; `x` is left to the caller, since only the vertical layout is shared.
    function __censusLayout(domMap, SAMPLES, kList, ih, rankOf, effort) {
        const nodes = {};
        kList.forEach(k => { const dm = domMap(k);
            SAMPLES.forEach(s => { const mc = dm[s].mc, key = `${k}:${mc}`;
                const o = nodes[key] || (nodes[key] = { k, mc, total: 0, samples: [] });
                o.total++; o.samples.push(s); }); });

        // Gaps are budgeted FIRST (at most half the panel, however many LCs a
        // column has) and `scale` takes everything left over, with no floor: the
        // census always fits whatever K and however many samples. Ribbon heights
        // use the same `scale`, so widths equal node heights exactly.
        const maxNodes = d3.max(kList, k => Object.values(nodes).filter(o => o.k === k).length) || 1;
        const gapMax = maxNodes > 1 ? (ih * 0.5) / (maxNodes - 1) : ih * 0.5;
        const CAP_H = gapMax >= 16 ? 15 : 0;          // "LCn" caption in the gap
        const gap = Math.max(3, Math.min(CAP_H ? CAP_H + 4 : 8, gapMax));
        let scale = Infinity;
        kList.forEach(k => { const arr = Object.values(nodes).filter(o => o.k === k);
            const t = d3.sum(arr, o => o.total);
            const avail = ih - (arr.length - 1) * gap - CAP_H;
            if (t > 0) scale = Math.min(scale, avail / t); });
        scale = Math.min(scale, 60);
        if (!(scale > 0)) scale = 0.2;                // degenerate guard only

        // The stack order of each column, chosen to minimise sample-weighted
        // ribbon crossings (see __orderColumns). The seed is still the old
        // forward pass — first column by mean consensus-cluster rank, the rest
        // by barycentre — and the search only ever replaces it with something
        // that crosses strictly less, so no layout gets worse than it was.
        const meanRank = o => d3.sum(o.samples, s => rankOf(s)) / (o.samples.length || 1);
        const COLS = kList.map(k => Object.values(nodes).filter(o => o.k === k));
        // centres a column WOULD have if stacked in this order — barycentres
        // are taken against these, so the same numbers the bars end up at.
        const centresOf = arr => {
            const colH = d3.sum(arr, o => o.total) * scale + (arr.length - 1) * gap;
            let y = Math.max(0, (ih - colH - CAP_H) / 2); const c = {};
            arr.forEach(o => { c[o.mc] = y + o.total * scale / 2; y += o.total * scale + gap; });
            return c; };
        const ORD = __orderColumns(COLS, domMap, SAMPLES, kList, meanRank, centresOf, ih, effort);

        const nodePos = {};
        kList.forEach((k, ki) => {
            const arr = ORD.order[ki];
            const colH = d3.sum(arr, o => o.total) * scale + (arr.length - 1) * gap;
            let y = Math.max(0, (ih - colH - CAP_H) / 2);
            arr.forEach(o => { const h = o.total * scale;
                nodePos[`${k}:${o.mc}`] = { top: y, h, k: o.k, mc: o.mc, total: o.total, samples: o.samples };
                y += h + gap; });
        });
        return { nodes, nodePos, scale, gap, CAP_H, crossings: ORD.report };
    }

    // Cut every node into bands by `groupOf`, stacked in the global `order`.
    // One band per group, so a group reads as one horizontal stripe across all
    // K — and, in a small-multiples figure, across all panels.
    function __cutNodes(nodePos, groupOf, order, scale) {
        const cuts = {};
        Object.entries(nodePos).forEach(([nk, n]) => {
            const by = {}; n.samples.forEach(s => { const gk = groupOf(s); (by[gk] = by[gk] || []).push(s); });
            const out = { list: [], by: {} };
            let yy = n.top;
            order.forEach(gval => { const sids = by[String(gval)] || by[gval]; if (!sids || !sids.length) return;
                const sl = { key: `g:${gval}`, group: gval, y0: yy, h: sids.length * scale, sids };
                out.list.push(sl); out.by[sl.key] = sl; yy += sl.h; });
            cuts[nk] = out;
        });
        return cuts;
    }

    // Ribbons split by (source LC, target LC, group), tiled inside the band
    // that holds them. Each ribbon is whole and its height is `count * scale`,
    // the same pixels-per-sample the nodes use — so every ribbon entering or
    // leaving a node sums to exactly that node.
    function __buildRibbons(domMap, SAMPLES, kList, nodePos, cuts, groupOf, scale) {
        const subs = [], outF = {}, inF = {};
        const centre = n => n ? n.top + n.h / 2 : 0;
        for (let i = 0; i < kList.length - 1; i++) {
            const ka = kList[i], kb = kList[i + 1];
            const da = domMap(ka), db = domMap(kb), map = {};
            SAMPLES.forEach(s => { const a = da[s].mc, b = db[s].mc, gk = groupOf(s);
                const key = `${a}|${b}|${gk}`;
                const f = map[key] || (map[key] = { ka, kb, a, b, g: gk, count: 0, sids: [] });
                f.count++; f.sids.push(s); });
            const fs = Object.values(map);
            fs.forEach(f => { subs.push(f);
                f.sids.forEach(s => { outF[`${ka}:${s}`] = f; inF[`${kb}:${s}`] = f; }); });
            const bySrc = {}, byTgt = {};
            fs.forEach(f => {
                const s1 = `${ka}:${f.a}||g:${f.g}`, s2 = `${kb}:${f.b}||g:${f.g}`;
                (bySrc[s1] = bySrc[s1] || []).push(f); (byTgt[s2] = byTgt[s2] || []).push(f); });
            Object.entries(bySrc).forEach(([key, arr]) => {
                const q = key.split("||"), sl = (cuts[q[0]] || { by: {} }).by[q[1]]; if (!sl) return;
                arr.sort((p, r) => centre(nodePos[`${kb}:${p.b}`]) - centre(nodePos[`${kb}:${r.b}`]));
                let yy = sl.y0; arr.forEach(f => { f.so = { y0: yy, y1: yy + f.count * scale }; yy += f.count * scale; }); });
            Object.entries(byTgt).forEach(([key, arr]) => {
                const q = key.split("||"), sl = (cuts[q[0]] || { by: {} }).by[q[1]]; if (!sl) return;
                arr.sort((p, r) => centre(nodePos[`${ka}:${p.a}`]) - centre(nodePos[`${ka}:${r.a}`]));
                let yy = sl.y0; arr.forEach(f => { f.to = { y0: yy, y1: yy + f.count * scale }; yy += f.count * scale; }); });
        }
        return { subs, outF, inF };
    }

    // Re-tile ONLY the selected samples, from the top of the same band, so a
    // traced sub-ribbon lands exactly on the highlighted part of the node. The
    // ribbon objects outlive a redraw, so last click's offsets are cleared
    // first — leaving them made every selection paint over the previous one.
    function __traceRibbons(subs, kList, nodePos, cuts, selSet, scale) {
        subs.forEach(f => { f.sn = 0; f.sso = null; f.sto = null; });
        if (!selSet) return;
        const centre = n => n ? n.top + n.h / 2 : 0;
        for (let i = 0; i < kList.length - 1; i++) {
            const ka = kList[i], kb = kList[i + 1], bySrc = {}, byTgt = {};
            subs.forEach(f => { if (f.ka !== ka) return;
                const n = f.sids.filter(s => selSet.has(s)).length; if (!n) return;
                f.sn = n;
                const s1 = `${ka}:${f.a}||g:${f.g}`, s2 = `${kb}:${f.b}||g:${f.g}`;
                (bySrc[s1] = bySrc[s1] || []).push(f); (byTgt[s2] = byTgt[s2] || []).push(f); });
            Object.entries(bySrc).forEach(([key, arr]) => {
                const q = key.split("||"), sl = (cuts[q[0]] || { by: {} }).by[q[1]]; if (!sl) return;
                arr.sort((x, y) => centre(nodePos[`${kb}:${x.b}`]) - centre(nodePos[`${kb}:${y.b}`]));
                let yy = sl.y0; arr.forEach(f => { f.sso = { y0: yy, y1: yy + f.sn * scale }; yy += f.sn * scale; }); });
            Object.entries(byTgt).forEach(([key, arr]) => {
                const q = key.split("||"), sl = (cuts[q[0]] || { by: {} }).by[q[1]]; if (!sl) return;
                arr.sort((x, y) => centre(nodePos[`${ka}:${x.a}`]) - centre(nodePos[`${ka}:${y.a}`]));
                let yy = sl.y0; arr.forEach(f => { f.sto = { y0: yy, y1: yy + f.sn * scale }; yy += f.sn * scale; }); });
        }
    }


    // The single-hue ramp. Both ends are derived from the target's hue in
    // CIELab rather than interpolating from plain white: a light input
    // ("yellow") would otherwise give a near-invisible or inverted ramp.
    // d3-color's Lab pairs the sRGB/D65 matrix with a D50 white point, so white
    // is lab(100, -2.4, -19.4) and NOT (100, 0, 0) — anchoring the pale end on
    // a=b=0 would tint a neutral ramp cream (#f9e6c9); blending toward d3's
    // actual white keeps gradient="black" grey.
    function __gradientRamp(GRAD, LIGHT_L) {
        const _c = d3.lab(d3.color(GRAD) || d3.color("black"));
        const _w = d3.lab(d3.rgb(255, 255, 255));
        const _dark  = d3.lab(Math.min(_c.l, 38), _c.a, _c.b);
        const _light = d3.lab(LIGHT_L, _w.a + (_c.a - _w.a) * 0.25,
                                       _w.b + (_c.b - _w.b) * 0.25);
        return d3.interpolateLab(_light, _dark);
    }

    function __clusterLineage(domMap, CL, K_RANGE, SINGLE, rampFn, SPREAD) {
        // OKLCH lineage: cosine distance between cross-k LC-occupancy profiles ->
        // average-linkage tree -> hue by cumulative tree distance along leaf order.
        // Hue sweep runs Red (~25) -> Blue (~255) only; capped before purple so it
        // never wraps back toward red (which would make distant clusters look alike).
        const HUE0 = 25, ARC = 230, CUTF = 0.6;
            const ids = [...new Set(Object.values(CL))].map(Number)
                .filter(c => c !== -1 && !Number.isNaN(c)).sort((a, b) => a - b);
            const color = {}, family = {};
            if (ids.length <= 1) { ids.forEach(c => { color[c] = SINGLE ? rampFn(0.6) : "oklch(0.62 0.15 250)"; family[c] = 0; });
                return { order: ids.slice(), color, family, root: null, maxH: 0 }; }
            const idx = Object.fromEntries(ids.map((c, i) => [c, i]));
            const vecs = ids.map(() => []);
            K_RANGE.forEach(k => { const dm = domMap(k); const cnt = ids.map(() => new Array(k).fill(0)), tot = ids.map(() => 0);
                for (const s in dm) { const ci = idx[CL[s]]; if (ci === undefined) continue; const mc = dm[s].mc; if (mc == null || mc >= k) continue; cnt[ci][mc]++; tot[ci]++; }
                ids.forEach((_, ci) => { const t = tot[ci] || 1; for (let m = 0; m < k; m++) vecs[ci].push(cnt[ci][m] / t); }); });
            const n = ids.length, D = Array.from({ length: n }, () => new Array(n).fill(0));
            const dot = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; };
            const nrm = vecs.map(v => Math.sqrt(dot(v, v)) || 1e-9);
            for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) { const d = 1 - dot(vecs[i], vecs[j]) / (nrm[i] * nrm[j]); D[i][j] = D[j][i] = d; }
            let active = ids.map((_, i) => ({ leaves: [i] }));
            const cd = (A, B) => { let s = 0, c = 0; A.leaves.forEach(x => B.leaves.forEach(y => { s += D[x][y]; c++; })); return s / c; };
            while (active.length > 1) { let bi = 0, bj = 1, bd = Infinity;
                for (let i = 0; i < active.length; i++) for (let j = i + 1; j < active.length; j++) { const d = cd(active[i], active[j]); if (d < bd) { bd = d; bi = i; bj = j; } }
                const A = active[bi], B = active[bj]; const m = { leaves: A.leaves.concat(B.leaves), left: A, right: B, height: bd };
                active = active.filter((_, i) => i !== bi && i !== bj); active.push(m); }
            const root = active[0], maxH = (function mh(nd) { return nd.left ? Math.max(nd.height, mh(nd.left), mh(nd.right)) : 0; })(root) || 1;
            const order = []; (function walk(nd) { if (nd.left) { walk(nd.left); walk(nd.right); } else order.push(nd.leaves[0]); })(root);
            const CUT = CUTF * maxH; let fid = 0;
            (function fam(nd) { if (nd.left && nd.height <= CUT) { const f = fid++; nd.leaves.forEach(l => family[ids[l]] = f); }
                else if (nd.left) { fam(nd.left); fam(nd.right); } else family[ids[nd.leaves[0]]] = fid++; })(root);
            const cum = [0]; for (let i = 1; i < order.length; i++) cum[i] = cum[i - 1] + D[order[i - 1]][order[i]];
            const span = cum[order.length - 1] || 1;
            const fam2 = {}; order.forEach(l => { const f = family[ids[l]]; (fam2[f] = fam2[f] || []).push(l); });
            order.forEach((l, i) => {
                // single-hue mode: cum[i]/span -- the exact quantity that drives
                // hue below -- drives lightness instead. The family L/C ramp is
                // dropped: lightness is the primary channel and cannot do double duty.
                if (SINGLE) {
                    const td = cum[i] / span, tr = order.length > 1 ? i / (order.length - 1) : 0.5;
                    color[ids[l]] = rampFn((1 - SPREAD) * td + SPREAD * tr);
                    return;
                }
                const h = HUE0 + (cum[i] / span) * ARC; const sibs = fam2[family[ids[l]]], si = sibs.indexOf(l), ns = sibs.length;
                const L = ns > 1 ? 0.52 + (si / (ns - 1)) * 0.24 : 0.63; const C = ns > 1 ? 0.20 - (si / (ns - 1)) * 0.07 : 0.16;
                color[ids[l]] = `oklch(${L.toFixed(3)} ${C.toFixed(3)} ${h.toFixed(1)})`; });
        return { order: order.map(l => ids[l]), color, family, root, maxH, ids };
    }

    // ---- stacking order override ----------------------------------------
    // `__clusterLineage` derives its own leaf order from the data (cosine
    // distance between cross-column LC-occupancy profiles), which is the right
    // default when the clusters ARE the lineage it just built. When the colours
    // come from outside -- a metadata field, where the meaningful order is the
    // field's own (1000 Genomes populations run Africa -> Europe -> South Asia
    // -> East Asia -> America, not by LC occupancy) -- that derived order would
    // disagree with the legend, and a reader matching a band to a legend entry
    // would be reading two different orders. `cluster_order` replaces it. Ids
    // the figure does not contain are dropped and ids the override forgot are
    // appended in the derived order, so a partial or stale list still draws.
    function __stackOrder(model, derived) {
        const want = (model.get("cluster_order") || []).map(Number);
        if (!want.length) return derived;
        const have = new Set(derived.map(Number));
        const out = want.filter(c => have.has(c));
        if (!out.length) return derived;
        const seen = new Set(out);
        derived.forEach(c => { if (!seen.has(Number(c))) out.push(Number(c)); });
        return out;
    }

    const __ribbonPath = (x0, y0t, y0b, x1, y1t, y1b) => { const mx = (x0 + x1) / 2;
        return `M ${x0} ${y0t} C ${mx} ${y0t} ${mx} ${y1t} ${x1} ${y1t} L ${x1} ${y1b} C ${mx} ${y1b} ${mx} ${y0b} ${x0} ${y0b} Z`; };

    // ===================================================================
    // cluster_prox — VOLUME-ACCURATE cluster-lineage StripeSankey
    //
    // Node height and ribbon width are the SAME quantity — a head count — so
    // every ribbon entering or leaving a node sums to exactly that node, and
    // each column is a full census of the cohort. The sizing/conservation
    // mechanic is meta_sankey's (`count * scale`, gap budgeted first); the
    // encoding is the stripesankey's (consensus-cluster bands in dendrogram
    // order, one colour per cluster end to end, OKLCH lineage or single-hue
    // ramp), and the interaction is unchanged: click a band / a ribbon / a
    // cluster chip to trace, click a "K =" label to focus that column.
    //
    // Two things the older trajectory-line version did are deliberately gone:
    //   * high_threshold no longer gates membership. Every sample is placed in
    //     its top-probability LC at each K, so nothing silently disappears —
    //     that gate is what made the old widths unreadable as counts.
    //   * min_flow_samples is ignored. Dropping a thin ribbon would break the
    //     node-height == sum-of-ribbons identity that is the point of this view.
    // Needs sankey_data.theta (per-k sample->LC) + sankey_data.clusters.
    // ===================================================================
    function drawClusterProxAll(el, model) {
        __setColLabels(model);
        el.innerHTML = '';
        el.style.position = 'relative';
        const data   = model.get("sankey_data") || {};
        const width  = model.get("width");
        const height = model.get("height");
        const theta  = data.theta || {};
        const CL     = ((data.clusters || {}).sample_to_cluster) || {};
        const META   = model.get("metadata") || {};        // {sample_id: {field: value}}
        // hover_field is a single name (str) or up to 3 names (list). The first
        // field also drives the cluster_prox focus-mode node restack.
        const _hf = model.get("hover_field");
        const HFIELDS = (Array.isArray(_hf) ? _hf : (_hf ? [_hf] : []))
            .map(String).filter(Boolean).slice(0, 3);
        const HFIELD0 = HFIELDS[0] || "";                   // first field (focus mode)
        const COMP = model.get("component_label") || "LC";  // what a component is called

        // gradient: "" (default) keeps the OKLCH hue-lineage strategy; any CSS
        // colour switches to a single-hue light->dark ramp over the SAME
        // dendrogram leaf order (see clusterLineage). node_width: 0 = auto.
        const GRAD   = model.get("gradient") || "";
        const SINGLE = GRAD !== "";
        const NODE_W_OVERRIDE = model.get("node_width") || 0;
        const SPREAD = Math.max(0, Math.min(1, +model.get("gradient_spread") || 0));
        // Both ends are derived from the target's hue in CIELab rather than
        // interpolating from plain white: a light input ("yellow") would
        // otherwise give a near-invisible or inverted ramp. The pale end used to
        // stop at L=92 (~#e8e8e8), which is nearly the #fafafa panel background —
        // the lightest cluster read as empty space. It now stops at L=82
        // (~#c9c9c9). gradient_light overrides that anchor (CIE L*, 0-100).
        const LIGHT_L = Math.max(40, Math.min(97, +model.get("gradient_light") || 82));
        const rampFn = SINGLE ? __gradientRamp(GRAD, LIGHT_L) : null;

        // stable category -> colour, per field (same category same colour)
        const _fieldColors = {};
        function fieldColor(field, val) {
            if (!_fieldColors[field]) {
                const set = new Set();
                for (const s in META) { const v = (META[s] || {})[field]; if (v != null) set.add(String(v)); }
                const cats = [...set].sort();
                const pal = d3.schemeTableau10 || d3.schemeCategory10;
                const map = {};
                cats.forEach((c, i) => map[c] = pal[i % pal.length]);
                _fieldColors[field] = map;
            }
            return _fieldColors[field][String(val)] || "#9aa0a6";
        }
        const valOf = (s, f) => { const v = (META[s] || {})[f]; return v == null ? "NA" : String(v); };

        // metadata composition of a set of samples -> mini bar chart(s), one
        // section per hover field (or "" when no field / no metadata). `fields`
        // overrides which fields to show (focus mode passes just the first).
        function metaComp(sids, fields) {
            const use = fields || HFIELDS;
            if (!use.length || !sids || !sids.length || !Object.keys(META).length) return "";
            let out = "";
            use.forEach(field => {
                const cnt = {};
                sids.forEach(s => { const key = valOf(s, field); cnt[key] = (cnt[key] || 0) + 1; });
                const rows = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 8);
                const mx = d3.max(rows, r => r[1]) || 1, tot = sids.length || 1, BAR = 160;
                out += `<div style="margin-top:8px;border-top:1px solid #444;padding-top:7px">`
                     + `<div style="opacity:.65;margin-bottom:6px;font-size:15px">${field}</div>`;
                rows.forEach(([k, n]) => {
                    const w = Math.max(3, (n / mx) * BAR), pct = Math.round(n / tot * 100);
                    out += `<div style="display:flex;align-items:center;gap:9px;margin:5px 0;font:15px sans-serif;line-height:1">`
                         +  `<span style="display:inline-block;width:110px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${k}">${k}</span>`
                         +  `<span style="display:inline-block;height:16px;width:${w.toFixed(0)}px;background:${fieldColor(field, k)};border-radius:3px"></span>`
                         +  `<span style="opacity:.85;white-space:nowrap">${n} (${pct}%)</span></div>`;
                });
                out += `</div>`;
            });
            return out;
        }

        if (!Object.keys(theta).length || !Object.keys(CL).length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">cluster_prox needs <b>theta</b> + <b>clusters</b> in sankey_data. Re-run training(cluster=True).</div>';
            return;
        }

        let K_RANGE = (data.k_range && data.k_range.length ? data.k_range : Object.keys(theta).map(Number))
            .map(Number).sort((a, b) => a - b);
        let kList = (model.get("k_list") || []).map(Number).filter(k => K_RANGE.includes(k));
        kList = [...new Set(kList)].sort((a, b) => a - b);
        if (!kList.length) kList = K_RANGE.slice();

        // ---- helpers (closures over theta / CL) ----
        const thetaK = k => theta[String(k)] || {};
        const domMap = __domMapFactory(theta);
        // The census: every sample that has a consensus-cluster label AND a
        // theta row in every shown K. No probability gate — that is the whole
        // difference from the old renderer.
        const SAMPLES = Object.keys(thetaK(kList[0]))
            .filter(s => CL[s] !== undefined && kList.every(k => domMap(k)[s]));
        if (!SAMPLES.length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">No samples are shared by the selected K and the consensus clustering.</div>';
            return;
        }
        const clOf = s => +CL[s];

        const LIN  = __clusterLineage(domMap, CL, K_RANGE, SINGLE, rampFn, SPREAD);
        const CCOL = model.get("cluster_colors") || {};
        if (Object.keys(CCOL).length) Object.assign(LIN.color, CCOL);
        const CORD = __stackOrder(model, LIN.order);   // leaf order (overridable)
        const rank = {}; CORD.forEach((c, i) => rank[c] = i);
        const NOISE = SAMPLES.some(s => clOf(s) === -1);
        // CORD is the lineage (what the dendrogram legend and the colour ramp
        // know about); STACK is what the bars are actually cut into, which
        // additionally carries the noise cluster -1 — unclustered samples still
        // have to be drawn or the node would no longer be a census.
        const STACK = NOISE ? CORD.concat([-1]) : CORD.slice();
        const lineageColor = cid => (+cid === -1)
            ? (SINGLE ? "#ffffff" : "#d4d6db")
            : (LIN.color[cid] || "#ccc");

        // ---- panel -------------------------------------------------------
        const svg = d3.select(el).append("svg").attr("width", width).attr("height", height)
            .style("background", "#fafafa").style("border", "1px solid #ddd");
        // A non-empty `cluster_legend` moves the "consensus clusters" legend
        // to a left column (drawLeftLineageLegend) instead of the bottom band
        // -- the two would otherwise show two different trees for the same
        // clusters (this one's own cosine-distance dendrogram vs. whatever
        // coherent one `cluster_legend` carries), so the bottom dendrogram is
        // dropped entirely rather than kept as a second, disagreeing one. The
        // focus-mode metadata key (`drawMetaLegend`'s job) moves into the SAME
        // left column too (`drawLeftMetaLegend`, mutually exclusive with the
        // dendrogram) so the bottom band is reclaimed for the diagram
        // entirely, rather than left an empty grey strip nothing draws into.
        const CLEG = model.get("cluster_legend") || {};
        const HAS_LEFT_LEGEND = !!(CLEG.leaves && CLEG.leaves.length);
        const LEGEND_W = 170;
        const legendH = HAS_LEFT_LEGEND ? 0 : 120;   // bottom band: reclaimed vs. full legend
        // A second heading line needs ~18px more above the diagram; with no
        // sublabels SUB_H is 0, the margin is the original 34 and nothing moves.
        const SUB_H = __hasColSubs() ? 18 : 0;
        const m = { t: 34 + SUB_H, r: 12, b: legendH + 12, l: (HAS_LEFT_LEGEND ? LEGEND_W : 0) + 12 };
        const iw = width - m.l - m.r, ih = height - m.t - m.b;
        if (iw < 60 || ih < 60) return;
        const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
        const INSET = Math.max(16, Math.min(52, iw * 0.06));
        const colX = d3.scalePoint().domain(kList.map(String)).range([INSET, iw - INSET]).padding(0.25);
        const STEP = colX.step() || 140;
        // wide nodes (the height is now readable as a count, so it deserves the
        // width), but never more than ~45% of the column pitch or bars of
        // adjacent K would meet
        const NODE_W = NODE_W_OVERRIDE > 0 ? NODE_W_OVERRIDE
            : Math.max(10, Math.min(64, STEP * 0.45, Math.max(26, STEP * 0.28)));

        // ---- geometry: node boxes, shared with the small-multiples renderer.
        // Nothing here knows about colour, which is the whole point — the same
        // call lays out a cluster-coloured panel and a metadata-coloured one.
        const LAY = __censusLayout(domMap, SAMPLES, kList, ih,
            s => { const r = rank[clOf(s)]; return r == null ? CORD.length : r; },
            model.get("layout_effort"));
        const scale = LAY.scale, CAP_H = LAY.CAP_H, nodePos = LAY.nodePos;
        // What the ordering search bought, for anyone checking a figure: the
        // forward-pass seed's weighted crossings vs. the ones actually drawn.
        // Left on `window` as well as the console so a headless render can read
        // it back (scripts/proto_iterated_barycentre.py).
        if (LAY.crossings) { window.__layoutReport = LAY.crossings;
            console.log("[stripesankey] weighted ribbon crossings  seed:",
                LAY.crossings.seed, " drawn:", LAY.crossings.final); }
        Object.values(nodePos).forEach(n => { n.x = colX(String(n.k)); });
        const centre = n => n ? n.top + n.h / 2 : 0;

        // ---- the two cuts of a node ----------------------------------------
        // SLC  consensus-cluster bands, in dendrogram order   (the default view)
        // SLM  metadata segments                              (the focused column)
        // Neither subdivides the other — a cluster is one block, a category is
        // one block. Ribbons are tiled against SLC once and never move again, so
        // toggling focus or a selection only ever recolours the bars.
        const SLC = __cutNodes(nodePos, clOf, STACK, scale);
        const _rb = __buildRibbons(domMap, SAMPLES, kList, nodePos, SLC, clOf, scale);
        const subs = _rb.subs, outF = _rb.outF, inF = _rb.inF;

        // metadata segments, ordered by the mean attachment height of the ribbons
        // the samples in each category travel on (both edges of the node count).
        // That is what keeps the focused view honest: a ribbon can no longer
        // appear to leave a segment none of its samples are in.
        function metaSlices(n) {
            const out = { list: [], by: {} };
            if (!HFIELD0) return out;
            const mid = o => o ? (o.y0 + o.y1) / 2 : null;
            const posOf = s => {
                const fo = outF[`${n.k}:${s}`], fi = inF[`${n.k}:${s}`];
                const a = fo ? mid(fo.so) : null, b = fi ? mid(fi.to) : null;
                if (a != null && b != null) return (a + b) / 2;
                return a != null ? a : (b != null ? b : n.top + n.h / 2);
            };
            const groups = {};
            n.samples.forEach(s => { const c = valOf(s, HFIELD0); (groups[c] = groups[c] || []).push(s); });
            const mean = {};
            Object.keys(groups).forEach(c => { let acc = 0; groups[c].forEach(s => acc += posOf(s)); mean[c] = acc / groups[c].length; });
            const cats = Object.keys(groups).sort((a, b) => mean[a] - mean[b] || (a < b ? -1 : a > b ? 1 : 0));
            let yy = n.top;
            cats.forEach(c => { const sids = groups[c];
                const sl = { key: `m:${c}`, cat: c, y0: yy, h: sids.length * scale, sids };
                out.list.push(sl); out.by[sl.key] = sl; yy += sl.h; });
            return out;
        }

        // Metadata categories ordered by the MEAN CLUSTER RANK of their samples,
        // not alphabetically: the cluster bands are tiled in dendrogram order, so
        // this puts a category at the same height as the cluster it belongs to —
        // flipping focus on and off, a block stays put when the two encodings
        // agree and visibly moves when they do not.
        const _catOrder = {};
        function catOrder(field) {
            if (_catOrder[field]) return _catOrder[field];
            const sum = {}, cnt = {};
            SAMPLES.forEach(s => { const v = valOf(s, field); const r = rank[clOf(s)];
                sum[v] = (sum[v] || 0) + (r == null ? CORD.length : r); cnt[v] = (cnt[v] || 0) + 1; });
            return (_catOrder[field] = Object.keys(cnt).sort((a, b) =>
                (sum[a] / cnt[a]) - (sum[b] / cnt[b]) || (a < b ? -1 : a > b ? 1 : 0)));
        }

        // ---- tooltip --------------------------------------------------------
        const tt = d3.select(el).append("div").style("position", "absolute").style("pointer-events", "none").style("opacity", 0)
            .style("background", "#111").style("color", "#fff").style("padding", "9px 13px").style("border-radius", "7px")
            .style("font", "16px sans-serif").style("z-index", 10);
        const showTip = (html, e) => { tt.html(html).style("opacity", 1); __placeFloat(tt.node(), e, width, height); };
        const hideTip = () => tt.style("opacity", 0);
        const ANN = __annotations(el, model, width, height);   // caller-supplied annotations

        // Which consensus clusters a set of samples belongs to — the mirror of
        // metaComp(), so the focused (metadata) view can be read back into the
        // cluster view and vice versa.
        function clComp(sids) {
            if (!sids || !sids.length) return "";
            const cnt = {}; sids.forEach(s => { const c = clOf(s); cnt[c] = (cnt[c] || 0) + 1; });
            const rows = STACK.filter(c => cnt[c]).map(c => [c, cnt[c]]);
            const mx = d3.max(rows, r => r[1]) || 1, tot = sids.length;
            let out = `<div style="margin-top:8px;border-top:1px solid #444;padding-top:7px">`
                    + `<div style="opacity:.65;margin-bottom:6px;font-size:15px">consensus cluster</div>`;
            rows.forEach(([c, n]) => { const w = Math.max(3, (n / mx) * 160);
                out += `<div style="display:flex;align-items:center;gap:9px;margin:5px 0;font:15px sans-serif;line-height:1">`
                     +  `<span style="display:inline-block;width:110px;text-align:right">${+c === -1 ? "noise" : "C" + c}</span>`
                     +  `<span style="display:inline-block;height:16px;width:${w.toFixed(0)}px;background:${lineageColor(c)};border-radius:3px"></span>`
                     +  `<span style="opacity:.85;white-space:nowrap">${n} (${Math.round(n / tot * 100)}%)</span></div>`; });
            return out + `</div>`;
        }

        // ---- state ----------------------------------------------------------
        let sel = null;                    // { key, set: Set(sample id) }
        let focusK = null;                 // focus mode: the single K column (null = normal)
        const topG = svg.append("g"), legendG = svg.append("g"), leftLegendG = svg.append("g");
        const content = g.append("g");
        const anyIn = arr => { if (!sel) return true; for (let i = 0; i < arr.length; i++) if (sel.set.has(arr[i])) return true; return false; };
        // Publish the selection to Python, exactly as meta_sankey does:
        // `selected_samples` + `selection_info` become readable in the live
        // kernel. Wrapped because the static-HTML export stubs model.set out.
        function pushSelection(info) {
            try {
                model.set("selected_samples", sel ? [...sel.set].sort() : []);
                model.set("selection_info", sel ? Object.assign({ key: sel.key, n: sel.set.size }, info || {}) : {});
                model.save_changes();
            } catch (err) { /* static export / no live kernel */ }
        }
        function toggleSel(key, sids, info) {
            sel = (sel && sel.key === key) ? null : { key, set: new Set(sids) };
            pushSelection(info); draw();
        }
        // Every sample dominated by this LC at this K -- the node as a whole,
        // across all its cluster bands. Its own selection key, so clicking the
        // node and clicking one of its bands stay separate toggles.
        function selectWholeNode(n) {
            toggleSel(`N:${n.k}:${n.mc}`, n.samples,
                { source: "node_all", k: n.k, mc: n.mc, n_total: n.total });
        }

        // The metadata cut is built after the ribbons, because its ordering
        // reads their attachment heights.
        const SLM = {};
        Object.entries(nodePos).forEach(([nk, n]) => { SLM[nk] = metaSlices(n); });
        const ribbon = __ribbonPath;

        // Large metadata key shown in the bottom band while a K is focused.
        function drawMetaLegend(group, field, fk) {
            const sids = [];
            Object.values(nodePos).forEach(n => { if (n.k === fk) n.samples.forEach(s => sids.push(s)); });
            const cnt = {}; sids.forEach(s => { const key = valOf(s, field); cnt[key] = (cnt[key] || 0) + 1; });
            const cats = catOrder(field).filter(c => cnt[c]);
            const Y0 = height - legendH + 18;
            group.append("text").attr("x", m.l).attr("y", Y0).style("font", "bold 15px sans-serif").style("fill", "#111")
                .text(`${field}  \u00b7  ${__colLabel(fk)} (${sids.length} samples)`);
            let x = m.l, y = Y0 + 28; const rowH = 26, sw = 16;
            cats.forEach(cat => {
                const label = `${cat} (${cnt[cat]})`, wpx = 30 + label.length * 8.4;
                if (x + wpx > width - m.r) { x = m.l; y += rowH; }
                group.append("rect").attr("x", x).attr("y", y - 13).attr("width", sw).attr("height", sw).attr("rx", 3).attr("fill", fieldColor(field, cat));
                group.append("text").attr("x", x + sw + 6).attr("y", y).style("font", "14px sans-serif").style("fill", "#222").text(label);
                x += wpx;
            });
            group.append("text").attr("x", m.l).attr("y", height - 6).style("font", "12px sans-serif").style("fill", "#888")
                .text(`click "${__colLabel(fk)}" again (or empty space) to exit focus`);
        }

        function draw() {
            __setColLabels(model);
            content.selectAll("*").remove(); topG.selectAll("*").remove();
            legendG.selectAll("*").remove(); leftLegendG.selectAll("*").remove();
            const focused = focusK != null, active = sel != null;

            // K labels along the top — clickable to focus
            kList.forEach(k => { const isF = focused && k === focusK, dim = focused && k !== focusK;
                topG.append("text").attr("x", m.l + colX(String(k))).attr("y", 20).attr("text-anchor", "middle")
                    .style("font-size", "16px").style("font-weight", "bold").style("fill", dim ? "#bbb" : "#000")
                    .style("cursor", "pointer").style("text-decoration", isF ? "underline" : "none").text(__colLabel(k))
                    .on("click", function (e) { e.stopPropagation(); hideTip(); ANN.hide();
                        focusK = (focusK === k) ? null : k; sel = null; pushSelection(); draw(); });
                // the optional qualifier line, shrunk to its own column's width so
                // a long one cannot run into its neighbour
                const sub = __colSub(k);
                if (sub) __shrinkText(topG.append("text")
                    .attr("x", m.l + colX(String(k))).attr("y", 20 + SUB_H)
                    .attr("text-anchor", "middle")
                    .style("fill", dim ? "#ccc" : "#666")
                    .text(sub), STEP * 0.95, 11, 8); });

            // legend: metadata key when focused, proximity dendrogram
            // otherwise -- LEFT column (both legends live there, mutually
            // exclusive) if `cluster_legend` was given, else the original
            // bottom band.
            const pick = (sel && sel.key.slice(0, 2) === "c:") ? +sel.key.slice(2) : null;
            const onPickCluster = cid => { const sids = SAMPLES.filter(s => clOf(s) === cid);
                toggleSel(`c:${cid}`, sids, { source: "cluster", cluster: cid }); };
            const showMetaLegend = focused && HFIELD0;
            if (HAS_LEFT_LEGEND) {
                if (showMetaLegend) {
                    const fsids = [];
                    Object.values(nodePos).forEach(n => { if (n.k === focusK) n.samples.forEach(s => fsids.push(s)); });
                    const fcnt = {}; fsids.forEach(s => { const key = valOf(s, HFIELD0); fcnt[key] = (fcnt[key] || 0) + 1; });
                    const fcats = catOrder(HFIELD0).filter(c => fcnt[c]);
                    drawLeftMetaLegend(leftLegendG, HFIELD0,
                        `${__colLabel(focusK)} \u00b7 ${fsids.length} samples`,
                        `click "${__colLabel(focusK)}" to exit`,
                        fcnt, fcats, fieldColor, 12, m.t, LEGEND_W, ih);
                } else {
                    drawLeftLineageLegend(leftLegendG, CLEG, lineageColor, 12, m.t, LEGEND_W, ih,
                        pick, onPickCluster,
                        (cid, e) => { const sids = SAMPLES.filter(s => clOf(s) === cid);
                            const lf = (CLEG.leaves || []).find(l => +l.id === cid);
                            showTip(`<b>${(lf && lf.label) || ("C" + cid)}</b> \u00b7 ${sids.length} samples`
                                + metaComp(sids, HFIELD0 ? [HFIELD0] : []), e); },
                        hideTip);
                }
            } else if (showMetaLegend) {
                drawMetaLegend(legendG, HFIELD0, focusK);
            } else {
                drawHorizontalLineageLegend(legendG, LIN, lineageColor, m.l, height - legendH,
                    width - m.l - m.r, legendH - 8, SINGLE, pick, onPickCluster,
                    `across all candidate models  \u00b7  ${SAMPLES.length} samples, all of them  \u00b7  ribbon width = samples`);
            }

            // Traced sub-ribbons land exactly on the highlighted part of the node.
            __traceRibbons(subs, kList, nodePos, SLC, active ? sel.set : null, scale);

            // ---- ribbons ----
            const fg = content.append("g");
            subs.forEach(f => {
                const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`];
                if (!sn || !tn || !f.so || !f.to) return;
                const x0 = sn.x + NODE_W / 2, x1 = tn.x - NODE_W / 2;
                const hit = active ? (f.sn || 0) : 0;
                const base = focused ? 0.3 : (active ? (hit ? 0.2 : 0.06) : (SINGLE ? 0.72 : 0.55));
                fg.append("path").attr("d", ribbon(x0, f.so.y0, f.so.y1, x1, f.to.y0, f.to.y1))
                    .attr("fill", lineageColor(f.g)).attr("opacity", base).style("cursor", "pointer")
                    .attr("stroke", SINGLE ? "#fff" : "none").attr("stroke-width", SINGLE ? 0.7 : 0)
                    .style("pointer-events", focused ? "none" : "auto")
                    .on("mousemove", e => showTip(`K${f.ka} ${COMP}${f.a} \u2192 K${f.kb} ${COMP}${f.b}`
                        + `<br><b>${+f.g === -1 ? "noise (unclustered)" : "cluster C" + f.g}</b> \u00b7 ${f.count} samples`
                        + (hit ? `<br><b>traced here: ${hit}</b>` : "") + metaComp(f.sids), e))
                    .on("mouseleave", hideTip)
                    .on("mouseover", function () { d3.select(this).attr("opacity", Math.max(base, 0.75)); })
                    .on("mouseout", function () { d3.select(this).attr("opacity", base); })
                    .on("click", function (e) { e.stopPropagation(); hideTip();
                        toggleSel(`f:${f.ka}|${f.a}|${f.b}|${f.g}`, f.sids,
                            { source: "flow", k_from: f.ka, k_to: f.kb, mc_from: f.a, mc_to: f.b, cluster: f.g }); });
            });
            if (active) subs.forEach(f => {
                if (!f.sso || !f.sto) return;
                const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`]; if (!sn || !tn) return;
                fg.append("path").attr("d", ribbon(sn.x + NODE_W / 2, f.sso.y0, f.sso.y1,
                                                   tn.x - NODE_W / 2, f.sto.y0, f.sto.y1))
                    .attr("fill", lineageColor(f.g)).attr("opacity", 0.92).style("pointer-events", "none"); });

            // ---- nodes ----
            Object.values(nodePos).forEach(n => {
                const rel = anyIn(n.samples), isFocus = focused && n.k === focusK;
                const away = focused && !isFocus;                 // a column being looked past
                const useMeta = isFocus && HFIELD0;
                const cut = (useMeta ? SLM : SLC)[`${n.k}:${n.mc}`] || { list: [] };
                cut.list.forEach(s => {
                    const hit = active ? s.sids.filter(i => sel.set.has(i)).length : 0;
                    const isNoise = !useMeta && +s.group === -1;
                    const op = away ? 0.4 : (active ? (hit ? 0.32 : 0.12) : 1);
                    const r = content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", s.y0)
                        .attr("width", NODE_W).attr("height", s.h)
                        .attr("fill", useMeta ? fieldColor(HFIELD0, s.cat) : lineageColor(s.group))
                        .attr("stroke", isNoise ? "#999" : ((SINGLE && !useMeta) ? "#8a8a8a" : "#fff"))
                        .attr("stroke-width", (SINGLE && !useMeta) ? 0.7 : 0.5)
                        // a white hairline between two adjacent near-identical
                        // tints disappears, fusing the bands into one blob
                        .attr("stroke-dasharray", (isNoise && SINGLE) ? "3,2" : null)
                        .attr("opacity", op).style("cursor", away ? "default" : "pointer")
                        .style("pointer-events", away ? "none" : "auto")
                        .on("mouseleave", hideTip);
                    if (useMeta) {
                        r.on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                            + `<br>${HFIELD0}: <b>${s.cat}</b> ${s.sids.length}`
                            + ` (${Math.round(s.sids.length / n.total * 100)}%)` + clComp(s.sids), e));
                    } else {
                        const cname = +s.group === -1 ? "<b>noise</b> (unclustered)" : `cluster <b>C${s.group}</b>`;
                        r.on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                            + `<br>${cname}: ${s.sids.length} (${Math.round(s.sids.length / n.total * 100)}%)`
                            + (hit ? `<br><b>traced here: ${hit}</b>` : "") + metaComp(s.sids), e))
                         .on("click", function (e) { e.stopPropagation(); hideTip();
                            // A band is one cluster INSIDE a node; shift/alt widens
                            // the same click to the whole node, which is the set
                            // "everyone dominated by this LC at this K".
                            if (e.shiftKey || e.altKey) selectWholeNode(n);
                            else toggleSel(`n:${n.k}:${n.mc}:${s.group}`, s.sids,
                                { source: "node", k: n.k, mc: n.mc, cluster: s.group }); });
                    }
                    if (hit && !focused) content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", s.y0)
                        .attr("width", NODE_W).attr("height", hit * scale).attr("fill", useMeta ? fieldColor(HFIELD0, s.cat) : lineageColor(s.group))
                        .attr("stroke", "#111").attr("stroke-width", 0.8).style("pointer-events", "none");
                });
                content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", n.top).attr("width", NODE_W)
                    .attr("height", n.h).attr("fill", "none").attr("stroke", "#333")
                    .attr("stroke-width", isFocus ? 1.5 : 1.4)
                    .attr("opacity", away ? 0.5 : (active && !rel ? 0.2 : 1)).style("pointer-events", "none");
                // LC caption UNDER the node (not to its right); when the gap
                // cannot hold one, the id goes inside the bar instead
                const capFill = away ? "#999" : (!focused && active && !rel ? "#bbb" : "#333");
                // The caption is the WHOLE-NODE handle. The node body is already
                // spoken for -- each band there selects its own cluster -- so the
                // label under it, which names the node rather than any one band,
                // is the natural place to ask for all of it. With annotations it
                // has a second part, which opens them and selects nothing.
                const wireComp = s => s.style("cursor", away ? "default" : "pointer")
                    .style("pointer-events", away ? "none" : "auto")
                    .on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                        + `<br><span style="opacity:.7">click to select the whole node</span>`
                        + clComp(n.samples), e))
                    .on("mouseleave", hideTip)
                    .on("click", function (e) { e.stopPropagation(); hideTip(); selectWholeNode(n); });
                const wireAnn = s => s.style("cursor", away ? "default" : "pointer")
                    .style("pointer-events", away ? "none" : "auto")
                    .on("mousemove", e => showTip(ANN.tip(n.k, n.mc), e))
                    .on("mouseleave", hideTip)
                    .on("click", function (e) { e.stopPropagation(); hideTip(); ANN.toggle(n.k, n.mc, e); });
                const annotated = ANN.has(n.k, n.mc);
                if (CAP_H && annotated) {
                    // at most the column pitch, ~220 px, and never past either
                    // edge of the plot (a wide sweep of few k has wide columns)
                    const capW = Math.min(STEP * 0.95, 220, 2 * (n.x - 2), 2 * (iw - n.x + m.r - 4));
                    const cap = __twoPartCaption(content, n.x, n.top + n.h + 12, `${COMP}${n.mc}`,
                        ANN.headline(n.k, n.mc), capW, capFill);
                    wireComp(cap.comp); wireAnn(cap.ann);
                } else if (CAP_H) wireComp(content.append("text").attr("x", n.x).attr("y", n.top + n.h + 12)
                    .attr("text-anchor", "middle").style("font-size", "12px").style("font-weight", "bold")
                    .style("fill", capFill).text(`${COMP}${n.mc}`));
                else if (n.h >= 9) {
                    const t = content.append("text").attr("x", n.x).attr("y", n.top + n.h / 2 + 3)
                        .attr("text-anchor", "middle").style("font-size", "9px").style("font-weight", "bold")
                        .style("fill", "#fff").style("stroke", "rgba(0,0,0,.55)").style("stroke-width", "2px")
                        .style("paint-order", "stroke").style("pointer-events", "none").text(n.mc);
                    // no room for a caption: the in-bar id opens the annotations
                    // (shift-click a band still selects the whole node)
                    if (annotated) wireAnn(t);
                }
            });
        }

        draw();
        svg.on("click", () => { let changed = false; ANN.hide();
            if (sel != null) { sel = null; pushSelection(); changed = true; }
            if (focusK != null) { focusK = null; changed = true; }
            if (changed) draw(); });
        __mountExport(el, "stripesankey");
        // exposed for verification: node boxes, both cuts, the tiled ribbons
        el.__VOLSANKEY__ = { nodePos, SLC, SLM, subs, scale, samples: SAMPLES,
                             get focusK() { return focusK; },
                             get sel() { return sel ? { key: sel.key, n: sel.set.size } : null; } };
    }


    // ===================================================================
    // small_multiples — the SAME Sankey, coloured N different ways
    //
    // One panel per entry in `panels`: 'cluster' (consensus cluster, the
    // stripesankey's OKLCH lineage) or the name of a metadata column. The
    // point of putting them side by side is direct comparison, so every panel
    // shares ONE layout: same samples, same K columns, same `scale`, and the
    // same node y-position and stacking order at every K. Only the CUT differs
    // — which grouping a node is sliced into, and therefore how the ribbons
    // are split and coloured. If the layouts drifted the comparison would be
    // meaningless, so the geometry is computed once by __censusLayout and
    // handed to every panel; a panel cannot move a node even in principle.
    //
    // Panels are laid out left-to-right and share the vertical axis, so a
    // block at the same height in two panels really is the same height: you
    // can read "is the EUR segment exactly cluster C3?" straight off the
    // figure. Clicking a band or a ribbon traces those samples in EVERY panel
    // at once, which is the same question asked interactively.
    // ===================================================================
    function drawSmallMultiplesAll(el, model) {
        __setColLabels(model);
        el.innerHTML = "";
        el.style.position = "relative";
        const width = model.get("width"), height = model.get("height");
        const data = model.get("sankey_data") || {};
        const theta = data.theta || {};
        const CL = ((data.clusters || {}).sample_to_cluster) || {};
        const META = model.get("metadata") || {};
        const COMP = model.get("component_label") || "LC";  // what a component is called
        const GRAD = model.get("gradient") || "";
        const SINGLE = GRAD !== "";
        const SPREAD = Math.max(0, Math.min(1, +model.get("gradient_spread") || 0));
        const LIGHT_L = Math.max(40, Math.min(97, +model.get("gradient_light") || 82));
        const rampFn = SINGLE ? __gradientRamp(GRAD, LIGHT_L) : null;

        if (!Object.keys(theta).length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">small_multiples needs <b>theta</b> in sankey_data. Re-run training().</div>';
            return;
        }

        let K_RANGE = (data.k_range && data.k_range.length ? data.k_range : Object.keys(theta).map(Number))
            .map(Number).sort((a, b) => a - b);
        let kList = (model.get("k_list") || []).map(Number).filter(k => K_RANGE.includes(k));
        kList = [...new Set(kList)].sort((a, b) => a - b);
        if (!kList.length) kList = K_RANGE.slice();

        const domMap = __domMapFactory(theta);
        const hasCL = Object.keys(CL).length > 0;

        // Requested panels: 'cluster' needs the consensus labels, a field panel
        // needs that column to exist in the metadata. Anything unusable is
        // dropped with a note rather than drawn empty.
        const want = (model.get("panels") || []).map(String).filter(Boolean);
        const dropped = [];
        const PANELS = want.filter(pn => {
            if (pn === "cluster") { if (hasCL) return true; dropped.push(pn + " (no consensus clusters in the Sankey JSON)"); return false; }
            for (const s in META) if ((META[s] || {})[pn] != null) return true;
            dropped.push(pn + " (not a metadata column)"); return false;
        });
        if (!PANELS.length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">small_multiples needs at least one usable panel. '
                + 'Pass <b>panels=</b> as "cluster" and/or metadata column names'
                + (dropped.length ? '<br><span style="color:#a33">dropped: ' + dropped.join(", ") + '</span>' : '') + '</div>';
            return;
        }

        // The census: every sample with a theta row in every shown K (and a
        // cluster label, when a cluster panel is present — the panels must be
        // over the SAME samples or their heights would not be comparable).
        const needCL = PANELS.indexOf("cluster") >= 0;
        const SAMPLES = Object.keys(theta[String(kList[0])] || {})
            .filter(s => (!needCL || CL[s] !== undefined) && kList.every(k => domMap(k)[s]));
        if (!SAMPLES.length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">No samples are shared by the selected K.</div>';
            return;
        }
        const clOf = s => (CL[s] === undefined ? -1 : +CL[s]);
        const valOf = (s, f) => { const v = (META[s] || {})[f]; return v == null ? "NA" : String(v); };

        // cluster lineage: colours AND the rank that orders the layout
        const LIN = hasCL ? __clusterLineage(domMap, CL, K_RANGE, SINGLE, rampFn, SPREAD)
                          : { order: [], color: {}, root: null, maxH: 0 };
        const CCOL = model.get("cluster_colors") || {};
        if (Object.keys(CCOL).length) Object.assign(LIN.color, CCOL);
        const CORD = __stackOrder(model, LIN.order);
        const rank = {}; CORD.forEach((c, i) => rank[c] = i);
        const NOISE = hasCL && SAMPLES.some(s => clOf(s) === -1);
        const STACK = NOISE ? CORD.concat([-1]) : CORD.slice();
        const lineageColor = cid => (+cid === -1) ? (SINGLE ? "#ffffff" : "#d4d6db")
                                                  : (LIN.color[cid] || "#ccc");
        const pal = d3.schemeTableau10 || d3.schemeCategory10;
        const _fc = {};
        function fieldColor(field, val) {
            if (!_fc[field]) { const set = new Set();
                SAMPLES.forEach(s => set.add(valOf(s, field)));
                const mp = {}; [...set].sort().forEach((c, i) => mp[c] = pal[i % pal.length]); _fc[field] = mp; }
            return _fc[field][String(val)] || "#9aa0a6";
        }
        // Categories stack by the MEAN CLUSTER RANK of their samples, not
        // alphabetically. The cluster panel is tiled in dendrogram order, so a
        // metadata category ends up at the same height as the cluster it
        // mostly is — agreement between two panels then reads as alignment,
        // and disagreement as a visible offset. Without clusters, fall back to
        // the largest category first.
        const _co = {};
        function catOrder(field) {
            if (_co[field]) return _co[field];
            const sum = {}, cnt = {};
            SAMPLES.forEach(s => { const v = valOf(s, field); const r = rank[clOf(s)];
                sum[v] = (sum[v] || 0) + (r == null ? CORD.length : r); cnt[v] = (cnt[v] || 0) + 1; });
            const cats = Object.keys(cnt).sort(hasCL
                ? (a, b) => (sum[a] / cnt[a]) - (sum[b] / cnt[b]) || (a < b ? -1 : a > b ? 1 : 0)
                : (a, b) => cnt[b] - cnt[a] || (a < b ? -1 : a > b ? 1 : 0));
            return (_co[field] = cats);
        }

        // ---- canvas -------------------------------------------------------
        const svg = d3.select(el).append("svg").attr("width", width).attr("height", height)
            .style("background", "#fafafa").style("border", "1px solid #ddd");
        const MX = 14, PAD = 18, ROW_PAD = 16, CAP_BAND = 16, nP = PANELS.length;
        const TITLE_Y = 17, KLAB_Y = 39, HEAD_H = 50;   // title + "K =" row above the diagram

        // The legend wraps to as many rows as the panel width allows, and the
        // band booked for it has to be the SAME in every panel — `ih` is shared,
        // so a taller legend in one panel shortens the diagram in all of them.
        // Measuring is therefore a function of the candidate panel width, and it
        // has to run inside the grid search below rather than after it.
        const legendItems = PANELS.map(pn => {
            const items = (pn === "cluster")
                ? STACK.map(c => ({ key: c, label: (+c === -1 ? "noise" : "C" + c) }))
                : catOrder(pn).map(c => ({ key: c, label: c }));
            const cnt = {};
            SAMPLES.forEach(s => { const gk = (pn === "cluster") ? clOf(s) : valOf(s, pn); cnt[gk] = (cnt[gk] || 0) + 1; });
            items.forEach(it => { it.n = cnt[it.key] || 0;
                it.text = it.label + " (" + it.n + ")";
                it.w = 26 + it.text.length * 7.0; });        // incl. an 8px inter-item gap
            return items;
        });
        // greedy wrap of one panel's items at width pw -> rows of items
        function wrapLegend(items, pw) {
            const rows = [[]]; let w = 0;
            items.forEach(it => {
                if (w + it.w > pw && rows[rows.length - 1].length) { rows.push([]); w = 0; }
                rows[rows.length - 1].push(it); w += it.w;
            });
            return rows;
        }
        const legendHFor = pw => Math.min(
            20 + (d3.max(legendItems, its => wrapLegend(its, pw).length) || 1) * 21,
            Math.round(height * 0.4));

        // ---- automatic grid ------------------------------------------------
        // Panels no longer have to fit on one row. Adding columns makes each
        // panel narrower; adding rows makes each shorter — so the two knobs pull
        // against each other and there is a genuine optimum. Every feasible
        // column count is scored on how close the resulting plot area lands to
        // the aspect ratio a Sankey of THIS many K columns wants (wider with more
        // K), and the closest wins. `panel_cols` overrides the whole search.
        const MIN_PW = 240, MIN_PLOT_H = 130;
        // Calibrated against what a K column actually needs, roughly 110 px of
        // width, versus a plot area tall enough to read the bands — so four K
        // want about 1.5:1, not the 2.2:1 an earlier guess used. That guess was
        // wrong in a visible way: it laid three panels of a 4-K sweep out 2x2,
        // leaving a slot empty and squashing each plot to 193 px tall, because a
        // 777x193 panel scored closer to "wide" than a 512x493 one did.
        const TARGET_AR = Math.max(1.0, Math.min(3.0, 0.28 * kList.length + 0.4));
        const forced = Math.max(0, Math.min(nP, model.get("panel_cols") || 0));
        let best = null;
        for (let nc = forced || 1; nc <= (forced || nP); nc++) {
            const nr = Math.ceil(nP / nc);
            const pw = (width - 2 * MX - (nc - 1) * PAD) / nc;
            const rh = (height - CAP_BAND - (nr - 1) * ROW_PAD) / nr;
            if (pw < 20 || rh < 20) continue;
            const lh = legendHFor(pw);
            const ph = rh - HEAD_H - lh;                  // the diagram's own height
            const fits = pw >= MIN_PW && ph >= MIN_PLOT_H;
            // Aspect alone does not know that a half-empty last row looks wrong:
            // four panels scored marginally better as 3+1 than as 2x2. A small
            // per-empty-slot penalty settles those near-ties toward the balanced
            // grid without overriding a genuinely better shape.
            const waste = nc * nr - nP;
            const score = Math.abs(Math.log((pw / Math.max(ph, 1)) / TARGET_AR)) + 0.06 * waste;
            // a forced column count is honoured even when it does not fit, so the
            // user sees a cramped figure rather than a silent fallback
            if (!fits && !forced) continue;
            if (!best || score < best.score) best = { nc, nr, pw, rh, lh, ph, score };
        }
        if (!best) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">Not enough room for ' + nP
                + ' panels at ' + width + '\u00d7' + height + '. Raise <b>width</b>/<b>height</b>, '
                + 'pass fewer <b>panels</b>, or set <b>ncols</b> to force a grid.</div>';
            return;
        }
        const NCOLS = best.nc, NROWS = best.nr, PW = best.pw, ROW_H = best.rh;
        const legendH = best.lh;
        const m = { t: HEAD_H };
        const ih = ROW_H - m.t - legendH;                  // identical in every panel
        if (ih < 60) { el.innerHTML = '<div style="padding:20px;font-family:sans-serif">Too short — raise <b>height</b>.</div>'; return; }
        const legendRowsOf = items => wrapLegend(items, PW);

        // ---- ONE geometry, shared by every panel ---------------------------
        const LAY = __censusLayout(domMap, SAMPLES, kList, ih,
            s => { const r = rank[clOf(s)]; return r == null ? CORD.length : r; },
            model.get("layout_effort"));
        const scale = LAY.scale, CAP_H = LAY.CAP_H, nodePos = LAY.nodePos;

        // per-panel x scale; the y layout above is deliberately NOT per panel
        const INSET = Math.max(12, Math.min(40, PW * 0.09));
        const colX = d3.scalePoint().domain(kList.map(String)).range([INSET, PW - INSET]).padding(0.25);
        const STEP = colX.step() || 100;
        const NODE_W = Math.max(8, Math.min(40, STEP * 0.42, Math.max(16, STEP * 0.26)));

        // ---- tooltip ------------------------------------------------------
        const tt = d3.select(el).append("div").style("position", "absolute").style("pointer-events", "none")
            .style("opacity", 0).style("background", "#111").style("color", "#fff")
            .style("padding", "9px 13px").style("border-radius", "7px")
            .style("font", "14px sans-serif").style("z-index", 10);
        const showTip = (html, e) => { tt.html(html).style("opacity", 1); __placeFloat(tt.node(), e, width, height); };
        const hideTip = () => tt.style("opacity", 0);
        // The tooltip always breaks a set of samples down by EVERY panel's
        // dimension, not just the one being hovered — that cross-reading is
        // the whole reason the panels are side by side.
        function comp(sids) {
            if (!sids || !sids.length) return "";
            let out = "";
            PANELS.forEach(pn => {
                const cnt = {};
                sids.forEach(s => { const gk = (pn === "cluster") ? clOf(s) : valOf(s, pn); cnt[gk] = (cnt[gk] || 0) + 1; });
                const order = (pn === "cluster") ? STACK : catOrder(pn);
                const rows = order.filter(c => cnt[c]).map(c => [c, cnt[c]]);
                const mx = d3.max(rows, r => r[1]) || 1, tot = sids.length;
                out += `<div style="margin-top:7px;border-top:1px solid #444;padding-top:6px">`
                     + `<div style="opacity:.65;margin-bottom:5px;font-size:13px">${pn === "cluster" ? "consensus cluster" : pn}</div>`;
                rows.forEach(([c, n]) => { const w = Math.max(3, (n / mx) * 130);
                    const lab = (pn === "cluster") ? (+c === -1 ? "noise" : "C" + c) : c;
                    const fill = (pn === "cluster") ? lineageColor(c) : fieldColor(pn, c);
                    out += `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;line-height:1">`
                         +  `<span style="display:inline-block;width:100px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${lab}">${lab}</span>`
                         +  `<span style="display:inline-block;height:13px;width:${w.toFixed(0)}px;background:${fill};border-radius:3px"></span>`
                         +  `<span style="opacity:.85;white-space:nowrap">${n} (${Math.round(n / tot * 100)}%)</span></div>`; });
                out += `</div>`;
            });
            return out;
        }

        // ---- per-panel cut + ribbons (the only thing that differs) ---------
        const PANEL = PANELS.map((pn, pi) => {
            const isCl = pn === "cluster";
            const groupOf = isCl ? (s => clOf(s)) : (s => valOf(s, pn));
            const order = isCl ? STACK : catOrder(pn);
            const colorOf = isCl ? lineageColor : (v => fieldColor(pn, v));
            const cuts = __cutNodes(nodePos, groupOf, order, scale);
            const rb = __buildRibbons(domMap, SAMPLES, kList, nodePos, cuts, groupOf, scale);
            const col = pi % NCOLS, row = Math.floor(pi / NCOLS);
            return { name: pn, isCl, groupOf, order, colorOf, cuts, subs: rb.subs,
                     x0: MX + col * (PW + PAD), y0: row * (ROW_H + ROW_PAD),
                     legendRows: legendRowsOf(legendItems[pi]),
                     title: isCl ? "consensus cluster" : pn };
        });

        // ---- state --------------------------------------------------------
        let sel = null;                      // { key, set: Set(sample id) } — SHARED
        const gRoot = svg.append("g");
        function pushSelection(info) {
            try {
                model.set("selected_samples", sel ? [...sel.set].sort() : []);
                model.set("selection_info", sel ? Object.assign({ key: sel.key, n: sel.set.size }, info || {}) : {});
                model.save_changes();
            } catch (err) { /* static export / no live kernel */ }
        }
        function toggleSel(key, sids, info) {
            sel = (sel && sel.key === key) ? null : { key, set: new Set(sids) };
            pushSelection(info); draw();
        }
        // The whole node. Deliberately NOT namespaced by panel: the node boxes
        // are shared, so "everyone in K5 LC2" is the same set whichever panel you
        // asked from, and clicking it in a second panel should toggle it off, not
        // re-select it.
        function selectWholeNode(n) {
            toggleSel(`N:${n.k}:${n.mc}`, n.samples,
                { source: "node_all", k: n.k, mc: n.mc, n_total: n.total });
        }

        function draw() {
            __setColLabels(model);
            gRoot.selectAll("*").remove();
            const active = sel != null;
            PANEL.forEach(P => {
                const g = gRoot.append("g").attr("transform", `translate(${P.x0},${P.y0})`);
                // Panel heading + a rule, so the panels read as separate figures.
                // Centred over the panel rather than left-aligned: it then sits
                // over the columns it describes and lines up with the "K =" row
                // under it, so three headings scan as three figures instead of as
                // one ragged left margin.
                g.append("text").attr("x", PW / 2).attr("y", TITLE_Y).attr("text-anchor", "middle")
                    .style("font", "bold 14px sans-serif").style("fill", "#111").text(P.title);
                g.append("line").attr("x1", 0).attr("y1", TITLE_Y + 6).attr("x2", PW).attr("y2", TITLE_Y + 6)
                    .attr("stroke", "#e0e2e6");
                kList.forEach(k => g.append("text").attr("x", colX(String(k))).attr("y", KLAB_Y)
                    .attr("text-anchor", "middle").style("font-size", "13px").style("font-weight", "bold")
                    .style("fill", "#000").text(__colLabel(k)));

                const gg = g.append("g").attr("transform", `translate(0,${m.t})`);
                __traceRibbons(P.subs, kList, nodePos, P.cuts, active ? sel.set : null, scale);

                // ribbons
                P.subs.forEach(f => {
                    const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`];
                    if (!sn || !tn || !f.so || !f.to) return;
                    const x0 = colX(String(f.ka)) + NODE_W / 2, x1 = colX(String(f.kb)) - NODE_W / 2;
                    const hit = active ? (f.sn || 0) : 0;
                    const base = active ? (hit ? 0.2 : 0.06) : (SINGLE && P.isCl ? 0.72 : 0.55);
                    const lab = P.isCl ? (+f.g === -1 ? "noise (unclustered)" : "cluster C" + f.g) : `${P.name}: ${f.g}`;
                    gg.append("path").attr("d", __ribbonPath(x0, f.so.y0, f.so.y1, x1, f.to.y0, f.to.y1))
                        .attr("fill", P.colorOf(f.g)).attr("opacity", base).style("cursor", "pointer")
                        .attr("stroke", (SINGLE && P.isCl) ? "#fff" : "none").attr("stroke-width", (SINGLE && P.isCl) ? 0.7 : 0)
                        .on("mousemove", e => showTip(`K${f.ka} ${COMP}${f.a} \u2192 K${f.kb} ${COMP}${f.b}`
                            + `<br><b>${lab}</b> \u00b7 ${f.count} samples`
                            + (hit ? `<br><b>traced here: ${hit}</b>` : "") + comp(f.sids), e))
                        .on("mouseleave", hideTip)
                        .on("mouseover", function () { d3.select(this).attr("opacity", Math.max(base, 0.75)); })
                        .on("mouseout", function () { d3.select(this).attr("opacity", base); })
                        .on("click", function (e) { e.stopPropagation(); hideTip();
                            toggleSel(`${P.name}|f:${f.ka}|${f.a}|${f.b}|${f.g}`, f.sids,
                                { source: "flow", panel: P.name, k_from: f.ka, k_to: f.kb,
                                  mc_from: f.a, mc_to: f.b, group: f.g }); });
                });
                if (active) P.subs.forEach(f => {
                    if (!f.sso || !f.sto) return;
                    gg.append("path").attr("d", __ribbonPath(colX(String(f.ka)) + NODE_W / 2, f.sso.y0, f.sso.y1,
                                                             colX(String(f.kb)) - NODE_W / 2, f.sto.y0, f.sto.y1))
                        .attr("fill", P.colorOf(f.g)).attr("opacity", 0.92).style("pointer-events", "none"); });

                // nodes: identical boxes in every panel, cut differently
                Object.values(nodePos).forEach(n => {
                    const x = colX(String(n.k));
                    const rel = !active || n.samples.some(s => sel.set.has(s));
                    const cut = P.cuts[`${n.k}:${n.mc}`] || { list: [] };
                    cut.list.forEach(s => {
                        const hit = active ? s.sids.filter(i => sel.set.has(i)).length : 0;
                        const isNoise = P.isCl && +s.group === -1;
                        const lab = P.isCl ? (isNoise ? "<b>noise</b> (unclustered)" : `cluster <b>C${s.group}</b>`)
                                           : `${P.name}: <b>${s.group}</b>`;
                        gg.append("rect").attr("x", x - NODE_W / 2).attr("y", s.y0)
                            .attr("width", NODE_W).attr("height", s.h)
                            .attr("fill", P.colorOf(s.group))
                            .attr("stroke", isNoise ? "#999" : ((SINGLE && P.isCl) ? "#8a8a8a" : "#fff"))
                            .attr("stroke-width", (SINGLE && P.isCl) ? 0.7 : 0.5)
                            .attr("stroke-dasharray", (isNoise && SINGLE) ? "3,2" : null)
                            .attr("opacity", active ? (hit ? 0.32 : 0.12) : 1)
                            .style("cursor", "pointer")
                            .on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                                + `<br>${lab}: ${s.sids.length} (${Math.round(s.sids.length / n.total * 100)}%)`
                                + (hit ? `<br><b>traced here: ${hit}</b>` : "") + comp(s.sids), e))
                            .on("mouseleave", hideTip)
                            .on("click", function (e) { e.stopPropagation(); hideTip();
                                // shift/alt widens the click from this band to the
                                // whole node (identical in every panel, so it is
                                // the one selection all panels already share)
                                if (e.shiftKey || e.altKey) selectWholeNode(n);
                                else toggleSel(`${P.name}|n:${n.k}:${n.mc}:${s.group}`, s.sids,
                                    { source: "node", panel: P.name, k: n.k, mc: n.mc, group: s.group }); });
                        if (hit) gg.append("rect").attr("x", x - NODE_W / 2).attr("y", s.y0)
                            .attr("width", NODE_W).attr("height", hit * scale).attr("fill", P.colorOf(s.group))
                            .attr("stroke", "#111").attr("stroke-width", 0.8).style("pointer-events", "none");
                    });
                    gg.append("rect").attr("x", x - NODE_W / 2).attr("y", n.top).attr("width", NODE_W)
                        .attr("height", n.h).attr("fill", "none").attr("stroke", "#333").attr("stroke-width", 1.2)
                        .attr("opacity", rel ? 1 : 0.2).style("pointer-events", "none");
                    const capFill = (active && !rel) ? "#bbb" : "#333";
                    // caption = the whole-node handle (see cluster_prox)
                    if (CAP_H) gg.append("text").attr("x", x).attr("y", n.top + n.h + 11)
                        .attr("text-anchor", "middle").style("font-size", "10px").style("font-weight", "bold")
                        .style("fill", capFill).style("cursor", "pointer")
                        .on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                            + `<br><span style="opacity:.7">click to select the whole node</span>`
                            + comp(n.samples), e))
                        .on("mouseleave", hideTip)
                        .on("click", function (e) { e.stopPropagation(); hideTip(); selectWholeNode(n); })
                        .text(`${COMP}${n.mc}`);
                    else if (n.h >= 9) gg.append("text").attr("x", x).attr("y", n.top + n.h / 2 + 3)
                        .attr("text-anchor", "middle").style("font-size", "9px").style("font-weight", "bold")
                        .style("fill", "#fff").style("stroke", "rgba(0,0,0,.55)").style("stroke-width", "2px")
                        .style("paint-order", "stroke").style("pointer-events", "none").text(n.mc);
                });

                // Legend: swatch + label + count, in the SAME stacking order the
                // bands use, so the key reads top-to-bottom like the bars do —
                // and CENTRED under its own panel, each wrapped row centred
                // independently, so the key sits under the columns it describes
                // rather than trailing off to the left of a wide panel.
                const lg = g.append("g").attr("transform", `translate(0,${ROW_H - legendH + 4})`);
                P.legendRows.forEach((row, ri) => {
                    const ly = 12 + ri * 21;
                    if (ly > legendH - 2) return;                    // clipped, not overflowing
                    // the 8px trailing gap of the last item is not ink, so it is
                    // taken off before centring or every row sits 4px left
                    const rowW = d3.sum(row, it => it.w) - 8;
                    let lx = Math.max(0, (PW - rowW) / 2);
                    row.forEach(it => {
                        const isNoise = P.isCl && +it.key === -1;
                        lg.append("rect").attr("x", lx).attr("y", ly - 10).attr("width", 13).attr("height", 13).attr("rx", 3)
                            .attr("fill", P.colorOf(it.key))
                            .attr("stroke", isNoise ? "#999" : ((SINGLE && P.isCl) ? "#8a8a8a" : "#fff"))
                            .attr("stroke-width", 0.6)
                            .attr("stroke-dasharray", (isNoise && SINGLE) ? "3,2" : null)
                            .style("cursor", "pointer")
                            .on("click", function (e) { e.stopPropagation(); hideTip();
                                const sids = SAMPLES.filter(s => String(P.groupOf(s)) === String(it.key));
                                toggleSel(`${P.name}|g:${it.key}`, sids,
                                    { source: "legend", panel: P.name, group: it.key }); });
                        lg.append("text").attr("x", lx + 18).attr("y", ly).style("font", "12px sans-serif")
                            .style("fill", "#222").text(it.text);
                        lx += it.w;
                    });
                });
            });

            // One shared caption under everything. A one-panel figure is only as
            // wide as one panel, so the caption is picked to FIT rather than
            // clipped: the widest variant the room allows, at ~5.6 px per
            // character, and nothing at all below that.
            const head = `${SAMPLES.length} samples, all of them`;
            const tail = sel ? `${sel.set.size} traced \u2014 click again or click empty space to clear`
                             : "click a band, a ribbon or a legend swatch to trace those samples; "
                               + "click an \u201cMCn\u201d caption (or shift-click a band) for the whole node";
            const room = width - 2 * MX - (dropped.length ? 160 : 0);
            void NROWS;   // (grid shape is already baked into every panel's y0)
            const cands = [`${head} \u00b7 identical node layout in every panel \u00b7 ${tail}`,
                           `${head} \u00b7 identical node layout in every panel`,
                           head];
            const cap = cands.find(c => c.length * 5.6 <= room);
            if (cap) gRoot.append("text").attr("x", MX).attr("y", height - 4)
                .style("font", "11px sans-serif").style("fill", "#888").text(cap);
            if (dropped.length) gRoot.append("text").attr("x", width - MX).attr("y", height - 4)
                .attr("text-anchor", "end").style("font", "11px sans-serif").style("fill", "#a33")
                .text("dropped: " + dropped.join(", "));
        }

        draw();
        svg.on("click", () => { if (sel) { sel = null; pushSelection(); draw(); } });
        __mountExport(el, "small_multiples");
        el.__VOLSANKEY__ = { nodePos, scale, samples: SAMPLES,
                             panels: PANEL.map(P => ({ name: P.name, cuts: P.cuts, subs: P.subs })),
                             get sel() { return sel ? { key: sel.key, n: sel.set.size } : null; } };
    }

    // Horizontal proximity dendrogram (leaves along x, tree grows up) + cluster chips.
    // `sel` is the currently highlighted cluster id (null = none) and `onPick(cid)`
    // toggles it, so a chip click drives the same highlight as clicking a node band
    // or a trajectory. Both are optional: without onPick the legend stays static.
    // `subtitle` replaces the default caption line under the title — the
    // volume-accurate cluster_prox passes the census there (N samples, all of
    // them, ribbon width = samples).
    function drawHorizontalLineageLegend(svg, lin, colorFn, X0, Y0, W, H, single, sel, onPick, subtitle) {
        const order = lin.order, n = order.length; if (!n) return;
        const g = svg.append("g").attr("transform", `translate(${X0},${Y0})`);
        g.append("line").attr("x1", 0).attr("y1", 0).attr("x2", W).attr("y2", 0).attr("stroke", "#e5e7eb");
        // title + short subtitle (publication caption)
        g.append("text").attr("x", 0).attr("y", 16).style("font-size", "14px").style("font-weight", "600").style("fill", "#333").text("consensus clusters");
        g.append("text").attr("x", 0).attr("y", 31).style("font-size", "11px").style("fill", "#888").text(subtitle || "across all candidate models");
        // right-aligned hint, skipped on narrow panels where it would collide
        if (onPick && W > 430) g.append("text").attr("x", W).attr("y", 16).attr("text-anchor", "end").style("font-size", "11px").style("fill", "#888")
            .text(sel != null ? `cluster ${sel} highlighted \u00b7 click C${sel} again to clear` : "click a cluster chip to highlight it");
        const pad = 26, colW = (W - 2 * pad) / Math.max(1, n);
        const xLeafPos = i => pad + (i + 0.5) * colW;
        const chipY = H - 28, treeBot = chipY - 8, treeTop = 42;
        // chips + labels — dimmed when another cluster is highlighted, ringed when
        // this one is. The hit area spans chip + label so small chips stay clickable.
        order.forEach((cid, i) => { const x = xLeafPos(i);
            const isSel = sel != null && +sel === +cid, dim = sel != null && !isSel;
            const gc = g.append("g").attr("opacity", dim ? 0.3 : 1);
            gc.append("rect").attr("x", x - 7.5).attr("y", chipY).attr("width", 15).attr("height", 15).attr("rx", 3).attr("fill", colorFn(cid))
                .attr("stroke", isSel ? "#111" : (single ? "#8a8a8a" : "#fff")).attr("stroke-width", isSel ? 2 : 0.6);
            gc.append("text").attr("x", x).attr("y", chipY + 28).attr("text-anchor", "middle").style("font-size", "12px")
                .style("font-weight", isSel ? "bold" : "normal").style("fill", isSel ? "#111" : "#333").text("C" + cid);
            if (onPick) gc.append("rect").attr("x", x - Math.min(colW, 34) / 2).attr("y", chipY - 4)
                .attr("width", Math.min(colW, 34)).attr("height", 38).attr("fill", "transparent").style("cursor", "pointer")
                .on("click", function (e) { e.stopPropagation(); onPick(+cid); }); });
        if (!lin.root) return;
        const root = lin.root, maxH = lin.maxH || 1;
        const colOf = {}; let c = 0; (function walk(nd) { if (nd.left) { walk(nd.left); walk(nd.right); } else colOf[nd.leaves[0]] = c++; })(root);
        const xOf = nd => nd.left ? (xOf(nd.left) + xOf(nd.right)) / 2 : xLeafPos(colOf[nd.leaves[0]]);
        const yH = h => treeBot - (h / maxH) * (treeBot - treeTop);
        (function drawNode(nd) { if (!nd.left) return; drawNode(nd.left); drawNode(nd.right);
            const xn = xOf(nd), yn = yH(nd.height);
            [nd.left, nd.right].forEach(ch => { const xc = xOf(ch), yc = ch.left ? yH(ch.height) : treeBot;
                g.append("path").attr("d", `M ${xc} ${yc} V ${yn} H ${xn}`).attr("fill", "none").attr("stroke", "#b8bcc4").attr("stroke-width", 1); });
        })(root);
    }

    // Left-docked replacement for the legend above: leaves stacked top-to-
    // bottom, height growing right-to-left (0 against the diagram it labels),
    // each leaf a CIRCLE at its own first-merge height rather than a shared
    // baseline (see cluster_dendrogram.py's module docstring for why a plain
    // dendrogram's uniform baseline hides that number). `legend` is the exact
    // dict `dendrogram_layout()` produces -- built from `coarse_linkage`, so
    // the tree shape is the SAME chance-corrected Q as `cluster_colors`, not
    // this file's own cosine-distance one. Colour comes from `colorFn`
    // (`lineageColor`) at draw time, not `legend`'s own baked-in `color`
    // field, so this can never show a different colour than the ribbons even
    // if only `cluster_legend` (not `cluster_colors`) is set.
    function drawLeftLineageLegend(g, legend, colorFn, X0, Y0, W, H, sel, onPick,
                                   onHover, onHoverEnd) {
        const leaves = legend.leaves || [], links = legend.links || [], n = legend.n || 0;
        if (!n) return;

        // Title aligned with the "K = " row above the diagram -- same
        // baseline (y=20), same size/weight -- rather than a second,
        // differently-styled header competing with it for attention.
        // The heading names whatever the leaves actually are. It defaults to the
        // consensus clusters because that is what every caller that predates
        // `title` passes; a metadata colouring sets its own ("Population") and
        // must, since "Consensus clusters" over 26 population codes would be a
        // plain misstatement of what the figure shows.
        __shrinkText(g.append("text").attr("x", X0).attr("y", 20)
            .style("font-weight", "bold").style("fill", "#000")
            .text(legend.title || "Consensus clusters"), W - 4, 16, 10);

        const leg = g.append("g").attr("transform", `translate(${X0},${Y0})`);
        const PADX = 44;                       // room for the circle + label at the right edge
        const cat = d3.scaleLinear().domain([-0.5, n - 0.5]).range([10, H - 10]);
        const yMax = (legend.root_y || 0) * 1.1 || 1;
        const hgt = d3.scaleLinear().domain([0, yMax]).range([W - PADX, 0]);

        links.forEach(d => {
            leg.append("line").attr("x1", hgt(d.y1)).attr("y1", cat(d.x1))
                .attr("x2", hgt(d.y2)).attr("y2", cat(d.x2))
                .attr("stroke", "#b8bcc4").attr("stroke-width", 1);
        });
        // height = 0 reference -- everything left of it is real merge
        // structure; nothing right of it is drawn, since no leaf "starts" there.
        leg.append("line").attr("x1", hgt(0)).attr("y1", cat(-0.5))
            .attr("x2", hgt(0)).attr("y2", cat(n - 0.5))
            .attr("stroke", "#ddd").attr("stroke-dasharray", "3,3");

        const sizes = leaves.map(d => d.size);
        const hasSize = sizes.every(v => v !== null && v !== undefined);
        const rOf = hasSize ? d3.scaleSqrt().domain(d3.extent(sizes)).range([4, 11]) : (() => 7);

        const grp = leg.selectAll("g.__leftleaf").data(leaves).join("g")
            .attr("class", "__leftleaf")
            .attr("transform", d => `translate(${hgt(d.y)},${cat(d.x)})`)
            .style("cursor", onPick ? "pointer" : "default")
            .attr("opacity", d => (sel != null && +sel !== +d.id) ? 0.35 : 1);
        if (onPick) grp.on("click", (e, d) => { e.stopPropagation(); onPick(+d.id); });
        if (onHover) grp.on("mousemove", (e, d) => onHover(+d.id, e))
            .on("mouseleave", () => onHoverEnd && onHoverEnd());
        grp.append("circle").attr("r", d => rOf(d.size))
            .attr("fill", d => colorFn(d.id))
            .attr("stroke", d => (sel != null && +sel === +d.id) ? "#111" : "#222")
            .attr("stroke-width", d => (sel != null && +sel === +d.id) ? 2 : 1.1);
        grp.append("text").attr("x", d => rOf(d.size) + 5).attr("y", 3)
            .style("font-size", "11px").style("fill", "#333")
            .style("font-weight", d => (sel != null && +sel === +d.id) ? "bold" : "normal")
            .text(d => d.label || `C${d.id}`);
    }

    // The metadata key for the left column: cluster_prox's focus mode puts it
    // there in place of `drawLeftLineageLegend` (mutually exclusive with it)
    // when a `cluster_legend` is in use -- so the bottom band it used to occupy
    // in `drawHorizontalLineageLegend`'s layout can be reclaimed for the
    // diagram instead of sitting empty -- and meta_sankey, whose every column
    // is that focused column, docks it there permanently. Vertically stacked
    // chips rather than horizontally wrapped ones, since the column is narrow
    // and tall, not wide and short. `subtitle` and `footer` are the only parts
    // that differ between the two callers (one is in a focused K, the other is
    // not), so they are passed in rather than rebuilt here.
    //
    // `sel` + `onPick` make the swatches live, the way the cluster chips in
    // `drawHorizontalLineageLegend` are: `onPick(cat)` toggles, `sel` is the
    // category currently traced (null = none) and dims the others. Both are
    // optional -- without `onPick` the key stays static, which is what
    // cluster_prox's focus mode wants (its ribbons are tiled by cluster there,
    // so a metadata trace would have nothing coherent to land on).
    function drawLeftMetaLegend(g, field, subtitle, footer, cnt, cats, fieldColorFn, X0, Y0, W, H, sel, onPick) {
        // Title in the same slot and style as `drawLeftLineageLegend`'s
        // "Consensus clusters" (y=20, 16px bold, aligned with the "K =" row):
        // the two legends swap in and out of this one column, so a
        // differently-sized header would read as the layout jumping. Field
        // names are user data and can be long, so the size steps down to
        // 11px and only then truncates -- never past the column edge.
        __shrinkText(g.append("text").attr("x", X0).attr("y", 20)
            .style("font-weight", "bold").style("fill", "#000").text(field),
            W - 6, 16, 11);

        const leg = g.append("g").attr("transform", `translate(${X0},${Y0})`);
        leg.append("text").attr("x", 0).attr("y", 12).style("font-size", "10px")
            .style("fill", "#888").text(subtitle || "");
        // Swatch rows at 11px -- the size the lineage legend labels its
        // leaves with, so title-to-label contrast matches there too.
        let y = 32; const rowH = 19, sw = 12, tx = sw + 6;
        // Rows that fit between the subtitle and the exit hint. With more
        // categories than that, the last row counts what was left out rather
        // than dropping it silently.
        const maxRows = Math.max(1, Math.floor((H - 22 - y) / rowH));
        const nShow = cats.length > maxRows ? maxRows - 1 : cats.length;
        cats.slice(0, nShow).forEach(cat => {
            // Dimmed when another category is traced, ringed + bold when this
            // one is -- the same vocabulary the cluster chips use, so the two
            // legends read alike.
            const isSel = sel != null && String(sel) === String(cat);
            const dim = sel != null && !isSel;
            const row = leg.append("g").attr("opacity", dim ? 0.35 : 1);
            row.append("rect").attr("x", 0).attr("y", y - 10).attr("width", sw).attr("height", sw)
                .attr("rx", 2).attr("fill", fieldColorFn(field, cat))
                .attr("stroke", isSel ? "#111" : "none").attr("stroke-width", isSel ? 2 : 0);
            __clipText(row.append("text").attr("x", tx).attr("y", y)
                .style("font-size", "11px").style("fill", isSel ? "#111" : "#222")
                .style("font-weight", isSel ? "bold" : "normal")
                .text(`${cat} (${cnt[cat]})`), W - tx - 4, 11);
            // One hit area over swatch + label, so a short label is no harder
            // to click than a long one
            if (onPick) row.append("rect").attr("x", -2).attr("y", y - 12)
                .attr("width", W - 4).attr("height", rowH - 2)
                .attr("fill", "transparent").style("cursor", "pointer")
                .on("click", function (e) { e.stopPropagation(); onPick(cat); });
            y += rowH;
        });
        if (nShow < cats.length)
            leg.append("text").attr("x", 0).attr("y", y).style("font-size", "10px")
                .style("fill", "#888").text(`\u2026 +${cats.length - nShow} more`);
        if (footer) leg.append("text").attr("x", 0).attr("y", H - 4).style("font-size", "10px")
            .style("fill", "#888").text(footer);
    }

    // ---- meta_sankey: the stripesankey, cut by metadata --------------------
    // The SAME figure as cluster_prox with one thing changed: a node is sliced
    // into the categories of a metadata field instead of into consensus
    // clusters. "Same" is literal, not aspirational -- census, column order,
    // node positions, gaps, `scale`, margins and the left legend column all
    // come out of the shared layout (__censusLayout -> __cutNodes ->
    // __buildRibbons) called with the arguments cluster_prox passes, so a bar
    // at a given height in one render is the same bar in the other and
    // flipping between the two answers "is this cluster that category?" by
    // eye. Two things the old renderer did made that comparison impossible and
    // are deliberately gone:
    //   * high_threshold no longer gates membership. It used to keep only the
    //     samples confident in EVERY shown K, so node heights were a subset's
    //     and could not line up with cluster_prox's full census.
    //   * the per-LC top-taxa panel is gone. It needed a feature x annotation
    //     table, which is domain knowledge this package does not hold. Its
    //     replacement is generic: a caller passes `lc_annotations` and the
    //     caption gets a second, annotation part (see __annotations).
    // Needs sankey_data.theta + metadata_df + hover_field. sankey_data.clusters
    // is optional, and used only to order the columns and the category stack
    // the way cluster_prox orders them.
    function drawMetaSankeyAll(el, model) {
        __setColLabels(model);
        el.innerHTML = "";
        el.style.position = "relative";       // anchor the absolute tooltip / taxa panel
        const width = model.get("width"), height = model.get("height");
        const data = model.get("sankey_data") || {};
        const theta = data.theta || {};
        const CL = ((data.clusters || {}).sample_to_cluster) || {};
        const META = model.get("metadata") || {};
        const _hf = model.get("hover_field");
        const HFIELDS = (Array.isArray(_hf) ? _hf : (_hf ? [_hf] : [])).map(String).filter(Boolean).slice(0, 3);
        const FIELD = HFIELDS[0] || "";
        const COMP = model.get("component_label") || "LC";  // what a component is called
        // Colour traits, read only so the lineage call below is identical to
        // cluster_prox's. Nothing here is painted with a lineage colour -- but
        // `__clusterLineage` takes them, and making the call identical is the
        // cheapest guarantee that its leaf order, which DOES move the layout,
        // is the same one.
        const GRAD = model.get("gradient") || "";
        const SINGLE = GRAD !== "";
        const SPREAD = Math.max(0, Math.min(1, +model.get("gradient_spread") || 0));
        const LIGHT_L = Math.max(40, Math.min(97, +model.get("gradient_light") || 82));
        const rampFn = SINGLE ? __gradientRamp(GRAD, LIGHT_L) : null;
        const NODE_W_OVERRIDE = model.get("node_width") || 0;

        if (!Object.keys(theta).length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">meta_sankey needs <b>theta</b> in sankey_data. Re-run training().</div>';
            return;
        }
        if (!FIELD || !Object.keys(META).length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">meta_sankey needs <b>metadata_df</b> + a <b>hover_field</b> (the first field is encoded on nodes &amp; flows).</div>';
            return;
        }

        let K_RANGE = (data.k_range && data.k_range.length ? data.k_range : Object.keys(theta).map(Number)).map(Number).sort((a, b) => a - b);
        let kList = (model.get("k_list") || []).map(Number).filter(k => K_RANGE.includes(k));
        kList = [...new Set(kList)].sort((a, b) => a - b);
        if (!kList.length) kList = K_RANGE.slice();

        const domMap = __domMapFactory(theta);
        const hasCL = Object.keys(CL).length > 0;

        // The census, cluster_prox's exactly: a theta row in every shown K, and
        // a consensus label when the payload carries them. No probability gate.
        const SAMPLES = Object.keys(theta[String(kList[0])] || {})
            .filter(s => (!hasCL || CL[s] !== undefined) && kList.every(k => domMap(k)[s]));
        if (!SAMPLES.length) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">No samples are shared by the selected K'
                + (hasCL ? ' and the consensus clustering.' : '.') + '</div>';
            return;
        }
        const clOf = s => (CL[s] === undefined ? -1 : +CL[s]);
        const valOf = (s, f) => { const v = (META[s] || {})[f || FIELD]; return v == null ? "NA" : String(v); };

        // Colours off this are unused here; the leaf ORDER is not. It is what
        // __censusLayout ranks the first column by and barycentres the rest
        // from, so it has to be the order cluster_prox computes or the two
        // figures would stack their LCs differently and stop being overlayable.
        const LIN = hasCL ? __clusterLineage(domMap, CL, K_RANGE, SINGLE, rampFn, SPREAD)
                          : { order: [] };
        const CORD = __stackOrder(model, LIN.order);
        const rank = {}; CORD.forEach((c, i) => rank[c] = i);

        // stable category -> colour, built over ALL of META rather than over
        // the drawn samples -- cluster_prox's rule, so a category is the same
        // colour in its focused column as it is in every column here
        const _fieldColors = {};
        function fieldColor(field, val) {
            if (!_fieldColors[field]) {
                const set = new Set();
                for (const s in META) { const v = (META[s] || {})[field]; if (v != null) set.add(String(v)); }
                const pal = d3.schemeTableau10 || d3.schemeCategory10;
                const map = {};
                [...set].sort().forEach((c, i) => map[c] = pal[i % pal.length]);
                _fieldColors[field] = map;
            }
            return _fieldColors[field][String(val)] || "#9aa0a6";
        }

        // Categories stack by the MEAN CLUSTER RANK of their samples, which is
        // what cluster_prox's focused column does: a category then sits at the
        // height of the cluster it mostly is, so agreement between the two
        // renders reads as alignment and disagreement as a visible offset.
        // Without clusters there is no rank to use -- largest category first.
        const _catOrder = {};
        function catOrder(field) {
            if (_catOrder[field]) return _catOrder[field];
            const sum = {}, cnt = {};
            SAMPLES.forEach(s => { const v = valOf(s, field), r = rank[clOf(s)];
                sum[v] = (sum[v] || 0) + (r == null ? CORD.length : r); cnt[v] = (cnt[v] || 0) + 1; });
            return (_catOrder[field] = Object.keys(cnt).sort(hasCL
                ? (a, b) => (sum[a] / cnt[a]) - (sum[b] / cnt[b]) || (a < b ? -1 : a > b ? 1 : 0)
                : (a, b) => cnt[b] - cnt[a] || (a < b ? -1 : a > b ? 1 : 0)));
        }
        const CATS = catOrder(FIELD);
        const CNT = {}; SAMPLES.forEach(s => { const c = valOf(s); CNT[c] = (CNT[c] || 0) + 1; });

        // ---- panel: cluster_prox's margins, to the pixel ---------------------
        // The left column is permanent here. cluster_prox gives it to the
        // dendrogram and lends it to the metadata key only while a K is
        // focused; every column of this figure IS that focused column, so the
        // key simply lives there -- which is also what reclaims the bottom band
        // and makes `ih`, and with it `scale` and every node height, equal to
        // cluster_prox's whenever that is drawn with a `cluster_legend`.
        const svg = d3.select(el).append("svg").attr("width", width).attr("height", height)
            .style("background", "#fafafa").style("border", "1px solid #ddd");
        const LEGEND_W = 170;
        const m = { t: 34, r: 12, b: 12, l: LEGEND_W + 12 };
        const iw = width - m.l - m.r, ih = height - m.t - m.b;
        if (iw < 60 || ih < 60) return;
        const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
        const topG = svg.append("g"), leftLegendG = svg.append("g");
        const INSET = Math.max(16, Math.min(52, iw * 0.06));
        const colX = d3.scalePoint().domain(kList.map(String)).range([INSET, iw - INSET]).padding(0.25);
        const STEP = colX.step() || 140;
        const NODE_W = NODE_W_OVERRIDE > 0 ? NODE_W_OVERRIDE
            : Math.max(10, Math.min(64, STEP * 0.45, Math.max(26, STEP * 0.28)));

        // ---- geometry: the shared layout, the call cluster_prox makes --------
        const LAY = __censusLayout(domMap, SAMPLES, kList, ih,
            s => { const r = rank[clOf(s)]; return r == null ? CORD.length : r; },
            model.get("layout_effort"));
        const scale = LAY.scale, CAP_H = LAY.CAP_H, nodePos = LAY.nodePos;
        Object.values(nodePos).forEach(n => { n.x = colX(String(n.k)); });

        // One cut (metadata categories, in the global CATS order so a category
        // reads as one stripe across every K) and the ribbons tiled against it.
        const groupOf = s => valOf(s);
        const SLM = __cutNodes(nodePos, groupOf, CATS, scale);
        const subs = __buildRibbons(domMap, SAMPLES, kList, nodePos, SLM, groupOf, scale).subs;
        const ribbon = __ribbonPath;

        // ---- tooltip + up-to-3-field mini bar charts -------------------------
        const tt = d3.select(el).append("div").style("position", "absolute").style("pointer-events", "none").style("opacity", 0)
            .style("background", "#111").style("color", "#fff").style("padding", "9px 13px").style("border-radius", "7px").style("font", "15px sans-serif").style("z-index", 10);
        const showTip = (html, e) => { tt.html(html).style("opacity", 1); __placeFloat(tt.node(), e, width, height); };
        const hideTip = () => tt.style("opacity", 0);
        const ANN = __annotations(el, model, width, height);   // caller-supplied annotations
        function metaComp(sids) {
            if (!HFIELDS.length || !sids || !sids.length) return "";
            let out = "";
            HFIELDS.forEach(field => {
                const cnt = {}; sids.forEach(s => { const key = valOf(s, field); cnt[key] = (cnt[key] || 0) + 1; });
                const rows = Object.entries(cnt).sort((a, b) => b[1] - a[1]);
                const mx = d3.max(rows, r => r[1]) || 1, tot = d3.sum(rows, r => r[1]) || 1, BAR = 150;
                out += `<div style="margin-top:7px;border-top:1px solid #444;padding-top:6px"><div style="opacity:.65;margin-bottom:5px;font-size:14px">${field}</div>`;
                rows.forEach(([kk, n]) => { const w = Math.max(3, (n / mx) * BAR), pct = Math.round(n / tot * 100);
                    out += `<div style="display:flex;align-items:center;gap:8px;margin:4px 0;font:14px sans-serif;line-height:1"><span style="display:inline-block;width:100px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${kk}">${kk}</span><span style="display:inline-block;height:15px;width:${w.toFixed(0)}px;background:${fieldColor(field, kk)};border-radius:3px"></span><span style="opacity:.85;white-space:nowrap">${n} (${pct}%)</span></div>`; });
                out += `</div>`;
            });
            return out;
        }

        // ---- interactive draw: click a segment/flow to trace its samples ------
        // Selection = a set of sample ids. Click a node SEGMENT -> that segment's
        // samples; click a FLOW -> that flow's samples. Every flow + segment those
        // samples traverse (across all K) stays lit; the rest dims. Click again /
        // click empty space clears. (Same spirit as cluster_prox.)
        let sel = null;   // { key, set: Set(sampleId) }
        const anyIn = arr => { if (!sel) return true; for (let i = 0; i < arr.length; i++) if (sel.set.has(arr[i])) return true; return false; };
        // Publish the selection to Python: `selected_samples` + `selection_info`
        // become readable in the notebook as soon as save_changes() lands. Wrapped
        // because the static-HTML export stubs model.set/save_changes out.
        function pushSelection(info) {
            try {
                model.set("selected_samples", sel ? [...sel.set].sort() : []);
                model.set("selection_info", sel ? Object.assign({ key: sel.key, n: sel.set.size }, info || {}) : {});
                model.save_changes();
            } catch (err) { /* static export / no live kernel */ }
        }
        const toggleSel = (key, samples, info) => {
            sel = (sel && sel.key === key) ? null : { key, set: new Set(samples) };
            pushSelection(info); syncBar(); draw();
        };
        // Every sample dominated by this LC at this K -- the node as a whole,
        // across all its category bands.
        function selectWholeNode(n) {
            toggleSel(`N:${n.k}:${n.mc}`, n.samples,
                { source: "node_all", k: n.k, mc: n.mc, n_total: n.total });
        }
        // A legend swatch picks its WHOLE category -- every sample with that
        // value, at every K -- which is the one selection the diagram cannot
        // otherwise make: clicking a band gives you that category inside one
        // node, and this gives you the trajectory the category takes through
        // all of them. Its own key prefix, so band and category stay separate
        // toggles the way node and whole-node do.
        const pickedCat = () => (sel && sel.key.slice(0, 4) === "cat:") ? sel.key.slice(4) : null;
        const onPickCat = c => toggleSel(`cat:${c}`, SAMPLES.filter(s => valOf(s) === c),
            { source: "legend", field: FIELD, category: c });
        const content = g.append("g");

        // ---- freeze: snapshot the current selection into group A or B ---------
        // `selected_samples` is live (every click replaces it); FROZEN is not, so
        // a notebook can hold two groups still and compare them. Same write-back
        // mechanism, a different slot. HTML chrome, so it never reaches the SVG
        // export (that only serialises <svg> elements).
        const FROZEN = { A: [], B: [] };
        (function seedFrozen() {                       // survive a re-render
            const f = model.get("frozen_groups") || {};
            ["A", "B"].forEach(gname => {
                if (Array.isArray(f[gname])) FROZEN[gname] = f[gname].slice();
            });
        })();
        const FCOLOR = { A: "#2a78d6", B: "#e34948" };  // same pair as da_barplot
        const frozenSet = gname => new Set(FROZEN[gname] || []);

        function pushFrozen() {
            try {
                model.set("frozen_groups", { A: FROZEN.A.slice(), B: FROZEN.B.slice() });
                model.save_changes();
            } catch (err) { /* static export / no live kernel */ }
        }

        // No in-diagram freeze buttons. The A/B snapshot machinery below is
        // still live and still outlines the ribbons a snapshot runs through --
        // set `frozen_groups` from Python to use it -- but the two buttons and
        // their "clear" are not drawn, pending a proper design for them.
        // `syncBar` is kept as a no-op so every call site stays valid.
        function syncBar() {}

        function draw() {
            __setColLabels(model);
            content.selectAll("*").remove();
            const active = sel != null;

            // Traced sub-ribbons land exactly on the highlighted part of the node.
            __traceRibbons(subs, kList, nodePos, SLM, active ? sel.set : null, scale);

            // ---- ribbons ----
            const fg = content.append("g");
            subs.forEach(f => {
                const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`];
                if (!sn || !tn || !f.so || !f.to) return;
                const x0 = sn.x + NODE_W / 2, x1 = tn.x - NODE_W / 2;
                const hit = active ? (f.sn || 0) : 0;
                const base = active ? (hit ? 0.2 : 0.06) : 0.55;
                fg.append("path").attr("d", ribbon(x0, f.so.y0, f.so.y1, x1, f.to.y0, f.to.y1))
                    .attr("fill", fieldColor(FIELD, f.g)).attr("opacity", base)
                    .attr("stroke", "none").style("cursor", "pointer")
                    .on("mousemove", e => showTip(`K${f.ka} ${COMP}${f.a} \u2192 K${f.kb} ${COMP}${f.b}`
                        + `<br><b>${FIELD}: ${f.g}</b> \u00b7 ${f.count} samples`
                        + (hit ? `<br><b>traced here: ${hit}</b>` : "") + metaComp(f.sids), e))
                    .on("mouseleave", hideTip)
                    .on("mouseover", function () { d3.select(this).attr("opacity", Math.max(base, 0.75)); })
                    .on("mouseout", function () { d3.select(this).attr("opacity", base); })
                    .on("click", function (e) { e.stopPropagation(); hideTip();
                        toggleSel(`f:${f.ka}|${f.a}|${f.b}|${f.g}`, f.sids,
                            { source: "flow", k_from: f.ka, k_to: f.kb, mc_from: f.a, mc_to: f.b,
                              field: FIELD, category: f.g }); });
            });
            // exact sub-ribbons (selected samples only) at their true tiled positions
            if (active) subs.forEach(f => {
                if (!f.sso || !f.sto) return;
                const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`]; if (!sn || !tn) return;
                fg.append("path").attr("d", ribbon(sn.x + NODE_W / 2, f.sso.y0, f.sso.y1,
                                                   tn.x - NODE_W / 2, f.sto.y0, f.sto.y1))
                    .attr("fill", fieldColor(FIELD, f.g)).attr("opacity", 0.92).style("pointer-events", "none"); });

            // frozen groups: outline the ribbons a snapshot runs through, so you
            // can see what A and B actually are without leaving the diagram.
            ["A", "B"].forEach(gname => {
                const fset = frozenSet(gname); if (!fset.size) return;
                subs.forEach(f => {
                    if (!f.so || !f.to || !f.sids.some(s => fset.has(s))) return;
                    const sn = nodePos[`${f.ka}:${f.a}`], tn = nodePos[`${f.kb}:${f.b}`];
                    if (!sn || !tn) return;
                    fg.append("path")
                        .attr("d", ribbon(sn.x + NODE_W / 2, f.so.y0, f.so.y1,
                                          tn.x - NODE_W / 2, f.to.y0, f.to.y1))
                        .attr("fill", "none").attr("stroke", FCOLOR[gname])
                        .attr("stroke-width", 1.5).attr("opacity", 0.85)
                        .attr("stroke-dasharray", gname === "B" ? "4 3" : null)
                        .style("pointer-events", "none");
                });
            });

            // ---- nodes ----
            Object.values(nodePos).forEach(n => {
                const rel = anyIn(n.samples);
                const cut = SLM[`${n.k}:${n.mc}`] || { list: [] };
                cut.list.forEach(s => {
                    const hit = active ? s.sids.filter(i => sel.set.has(i)).length : 0;
                    const op = active ? (hit ? 0.32 : 0.12) : 1;
                    content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", s.y0)
                        .attr("width", NODE_W).attr("height", s.h)
                        .attr("fill", fieldColor(FIELD, s.group))
                        .attr("stroke", "#fff").attr("stroke-width", 0.5)
                        .attr("opacity", op).style("cursor", "pointer")
                        .on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                            + `<br>${FIELD}: <b>${s.group}</b> ${s.sids.length}`
                            + ` (${Math.round(s.sids.length / n.total * 100)}%)`
                            + (hit ? `<br><b>traced here: ${hit}</b>` : "") + metaComp(s.sids), e))
                        .on("mouseleave", hideTip)
                        .on("click", function (e) { e.stopPropagation(); hideTip();
                            // shift/alt widens the click from this one category to
                            // the whole node, exactly as in cluster_prox
                            if (e.shiftKey || e.altKey) selectWholeNode(n);
                            else toggleSel(`n:${n.k}:${n.mc}:${s.group}`, s.sids,
                                { source: "node", k: n.k, mc: n.mc, field: FIELD, category: s.group }); });
                    if (hit) content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", s.y0)
                        .attr("width", NODE_W).attr("height", hit * scale)
                        .attr("fill", fieldColor(FIELD, s.group))
                        .attr("stroke", "#111").attr("stroke-width", 0.8).style("pointer-events", "none");
                });
                content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", n.top)
                    .attr("width", NODE_W).attr("height", n.h).attr("fill", "none")
                    .attr("stroke", "#333").attr("stroke-width", 1.4)
                    .attr("opacity", active && !rel ? 0.2 : 1).style("pointer-events", "none");

                // Caption UNDER the node, cluster_prox's "LCn"; when
                // the gap cannot hold one the id goes inside the bar instead.
                // Clicking it selects the whole node -- the node body is already
                // spoken for, each band there selecting its own category. With
                // annotations it has a second part, which opens them (as in
                // cluster_prox).
                const dimTxt = active && !rel;
                const wireComp = s => s.style("cursor", "pointer")
                    .on("mousemove", e => showTip(`<b>K${n.k} ${COMP}${n.mc}</b> \u00b7 ${n.total} samples`
                        + `<br><span style="opacity:.7">click to select the whole node</span>`
                        + metaComp(n.samples), e))
                    .on("mouseleave", hideTip)
                    .on("click", function (e) { e.stopPropagation(); hideTip();
                        selectWholeNode(n); });
                const wireAnn = s => s.style("cursor", "pointer")
                    .on("mousemove", e => showTip(ANN.tip(n.k, n.mc), e))
                    .on("mouseleave", hideTip)
                    .on("click", function (e) { e.stopPropagation(); hideTip(); ANN.toggle(n.k, n.mc, e); });
                const annotated = ANN.has(n.k, n.mc);
                if (CAP_H && annotated) {
                    const capW = Math.min(STEP * 0.95, 220, 2 * (n.x - 2), 2 * (iw - n.x + m.r - 4));
                    const cap = __twoPartCaption(content, n.x, n.top + n.h + 12, `${COMP}${n.mc}`,
                        ANN.headline(n.k, n.mc), capW, dimTxt ? "#bbb" : "#333");
                    wireComp(cap.comp); wireAnn(cap.ann);
                } else if (CAP_H) wireComp(content.append("text").attr("x", n.x).attr("y", n.top + n.h + 12)
                    .attr("text-anchor", "middle").style("font-size", "12px").style("font-weight", "bold")
                    .style("fill", dimTxt ? "#bbb" : "#333").text(`${COMP}${n.mc}`));
                else if (n.h >= 9) {
                    const t = content.append("text").attr("x", n.x).attr("y", n.top + n.h / 2 + 3)
                        .attr("text-anchor", "middle").style("font-size", "9px").style("font-weight", "bold")
                        .style("fill", "#fff").style("stroke", "rgba(0,0,0,.55)").style("stroke-width", "2px")
                        .style("paint-order", "stroke").attr("opacity", dimTxt ? 0.35 : 1).text(n.mc);
                    // no room for a caption: with annotations the in-bar id opens
                    // them (shift-click a band for the whole node); without, it
                    // selects the whole node as before
                    if (annotated) wireAnn(t); else wireComp(t);
                }
            });

            // ---- the metadata key, redrawn with the diagram so a traced
            // category is ringed in it ------------------------------------
            leftLegendG.selectAll("*").remove();
            drawLeftMetaLegend(leftLegendG, FIELD,
                `${SAMPLES.length} samples, all of them`,
                "click a swatch, a band or a ribbon to trace",
                CNT, CATS, fieldColor, 12, m.t, LEGEND_W, ih,
                pickedCat(), onPickCat);
        }
        draw();
        syncBar();
        svg.on("click", () => { ANN.hide(); if (sel) { sel = null; pushSelection(null); syncBar(); draw(); } });

        // ---- K labels (top) --------------------------------------------------
        kList.forEach(k => topG.append("text").attr("x", m.l + colX(String(k))).attr("y", 20)
            .attr("text-anchor", "middle").style("font-size", "16px").style("font-weight", "bold")
            .style("fill", "#000").text(__colLabel(k)));
        __mountExport(el, "meta_sankey");
        // verification hook, same as the other two renderers expose
        el.__VOLSANKEY__ = { nodePos, SLM, subs, scale, samples: SAMPLES,
                             get sel() { return sel ? { key: sel.key, n: sel.set.size } : null; } };
    }

    // ---- hard_sankey: standalone Sankey for HARD clustering labels ----------
    // Input is NOT theta. `hard_data` carries, per ordered level (column), each
    // sample's hard cluster label. Nodes = clusters within a level; flows =
    // samples moving between consecutive levels. Colour encodes `colorby` (a
    // metadata field, or the global consensus cluster). Node height == the sum
    // of its flow widths exactly (every sample has a label in every level:
    // missing -> "NA", noise -> "noise", each its own node). min_flow_samples
    // hides ribbons carrying fewer than that many samples. Same wide stacked
    // nodes / colour-matched ribbons / click-to-trace spirit as meta_sankey.
    function drawHardSankeyAll(el, model) {
        __setColLabels(model);
        el.innerHTML = "";
        const width = model.get("width"), height = model.get("height");
        const hd = model.get("hard_data") || {};
        const levels = (hd.levels || []).map(String);
        const labels = hd.labels || {};          // {level:{sid:labelStr}}
        const color  = hd.color  || {};          // {sid:valueStr}
        const META   = hd.meta   || {};          // {sid:{field:valStr}}
        const HFIELDS = (hd.hover_fields || []).map(String).slice(0, 3);
        const COLORBY = String(hd.colorby_name || "");
        const MINFLOW = model.get("min_flow_samples") || 0;

        if (levels.length < 2) {
            el.innerHTML = '<div style="padding:20px;font-family:sans-serif">hard_sankey needs at least <b>2 ordered label columns</b> in clustering_labels.</div>';
            return;
        }
        const SAMPLES = Object.keys(labels[levels[0]] || {});
        if (!SAMPLES.length) { el.innerHTML = '<div style="padding:20px;font-family:sans-serif">no samples to plot</div>'; return; }

        // numeric-aware comparison so cluster ids 0,1,2,10 sort naturally
        const natCmp = (a, b) => { a = String(a); b = String(b); const na = parseFloat(a), nb = parseFloat(b);
            if (!isNaN(na) && !isNaN(nb) && String(na) === a && String(nb) === b) return na - nb;
            return a < b ? -1 : a > b ? 1 : 0; };
        const labOf = (lvl, s) => { const v = (labels[lvl] || {})[s]; return v == null ? "NA" : String(v); };
        const valOf = s => { const v = color[s]; return (v == null || v === "") ? "NA" : String(v); };

        const CATS = [...new Set(SAMPLES.map(valOf))].sort(natCmp);
        const pal = d3.schemeTableau10.concat(d3.schemeSet3 || []);
        const catColor = {}; CATS.forEach((c, i) => catColor[c] = (c === "noise" || c === "NA") ? "#9aa0a6" : pal[i % pal.length]);

        const svg = d3.select(el).append("svg").attr("width", width).attr("height", height).style("background", "#fafafa").style("border", "1px solid #ddd");
        const legendH = 100, m = { t: 34, r: 16, b: legendH + 10, l: 16 };
        const iw = width - m.l - m.r, ih = height - m.t - m.b;
        if (iw < 60 || ih < 60) return;
        const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
        const colX = d3.scalePoint().domain(levels).range([48, iw - 48]).padding(0.25);
        const NODE_W = Math.max(26, Math.min(64, (colX.step() || 140) * 0.28));

        // tooltip + up-to-3-field mini bar charts
        const tt = d3.select(el).append("div").style("position", "absolute").style("pointer-events", "none").style("opacity", 0)
            .style("background", "#111").style("color", "#fff").style("padding", "9px 13px").style("border-radius", "7px").style("font", "15px sans-serif").style("z-index", 10);
        const showTip = (html, e) => { tt.html(html).style("opacity", 1); __placeFloat(tt.node(), e, width, height); };
        const hideTip = () => tt.style("opacity", 0);
        const _fc = {};
        function fieldColor(field, val) {
            if (!_fc[field]) { const set = new Set(); for (const s in META) { const v = (META[s] || {})[field]; if (v != null) set.add(String(v)); }
                const cats = [...set].sort(natCmp), mp = {}; cats.forEach((c, i) => mp[c] = pal[i % pal.length]); _fc[field] = mp; }
            return _fc[field][String(val)] || "#9aa0a6";
        }
        function metaComp(sids) {
            if (!HFIELDS.length || !sids || !sids.length) return "";
            let out = "";
            HFIELDS.forEach(field => {
                const cnt = {}; sids.forEach(s => { const v = (META[s] || {})[field]; const key = (v == null ? "NA" : String(v)); cnt[key] = (cnt[key] || 0) + 1; });
                const rows = Object.entries(cnt).sort((a, b) => b[1] - a[1]);
                const mx = d3.max(rows, r => r[1]) || 1, tot = d3.sum(rows, r => r[1]) || 1, BAR = 150;
                out += `<div style="margin-top:7px;border-top:1px solid #444;padding-top:6px"><div style="opacity:.65;margin-bottom:5px;font-size:14px">${field}</div>`;
                rows.forEach(([kk, n]) => { const w = Math.max(3, (n / mx) * BAR), pct = Math.round(n / tot * 100);
                    out += `<div style="display:flex;align-items:center;gap:8px;margin:4px 0;font:14px sans-serif;line-height:1"><span style="display:inline-block;width:100px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${kk}">${kk}</span><span style="display:inline-block;height:15px;width:${w.toFixed(0)}px;background:${fieldColor(field, kk)};border-radius:3px"></span><span style="opacity:.85;white-space:nowrap">${n} (${pct}%)</span></div>`; });
                out += `</div>`;
            });
            return out;
        }

        // per-level nodes: col[level][label] = {mc,total,byCat,samples}
        const col = {};
        levels.forEach(lvl => { const nodes = {};
            SAMPLES.forEach(s => { const lab = labOf(lvl, s); const o = (nodes[lab] = nodes[lab] || { mc: lab, total: 0, byCat: {}, samples: [] });
                o.total++; const c = valOf(s); o.byCat[c] = (o.byCat[c] || 0) + 1; o.samples.push(s); });
            col[lvl] = nodes; });

        // vertical scale: most-constrained column fills the panel
        const gap = 16;
        let scale = Infinity;
        levels.forEach(lvl => { const arr = Object.values(col[lvl]); const t = d3.sum(arr, o => o.total); const avail = ih - (arr.length - 1) * gap; const sc = t > 0 ? avail / t : Infinity; scale = Math.min(scale, sc); });
        scale = Math.max(0.2, Math.min(scale, 60));

        // node positions (barycentre order) + category segments. nodePos is
        // NESTED (nodePos[level][label]) so level names / labels may contain ":".
        const nodePos = {}; let prevCenters = {};
        levels.forEach((lvl, li) => {
            let arr = Object.values(col[lvl]);
            if (li === 0) arr.sort((a, b) => natCmp(a.mc, b.mc));
            else { const prev = levels[li - 1];
                const bary = o => { let ws = 0, w = 0; o.samples.forEach(s => { const c = prevCenters[labOf(prev, s)]; if (c != null) { ws += c; w++; } }); return w ? ws / w : ih / 2; };
                arr = arr.slice().sort((a, b) => bary(a) - bary(b)); }
            const colH = d3.sum(arr, o => o.total) * scale + (arr.length - 1) * gap;
            let y = (ih - colH) / 2; const x = colX(lvl); const centers = {}; const lvlNodes = {};
            arr.forEach(o => { const h = o.total * scale; let yy = y; const catSeg = {};
                const ordCats = Object.keys(o.byCat).filter(c => o.byCat[c] > 0).sort((a, b) => o.byCat[b] - o.byCat[a]);
                ordCats.forEach(c => { const hh = o.byCat[c] * scale; catSeg[c] = { y0: yy, h: hh }; yy += hh; });
                lvlNodes[o.mc] = { x, top: y, h, lvl, mc: o.mc, total: o.total, byCat: o.byCat, samples: o.samples, catSeg };
                centers[o.mc] = y + h / 2; y += h + gap; });
            nodePos[lvl] = lvlNodes; prevCenters = centers;
        });
        const NP = (lvl, lab) => (nodePos[lvl] || {})[lab];

        // flows split by category: {la,lb,a,b,cat,count,samples}
        const flows = [];
        for (let i = 0; i < levels.length - 1; i++) { const la = levels[i], lb = levels[i + 1], map = {};
            SAMPLES.forEach(s => { const a = labOf(la, s), b = labOf(lb, s), cat = valOf(s); const o = (map[a + "|" + b + "|" + cat] = map[a + "|" + b + "|" + cat] || { la, lb, a, b, cat, count: 0, samples: [] }); o.count++; o.samples.push(s); });
            Object.values(map).forEach(f => flows.push(f)); }

        // attach ribbon offsets within each category segment (nested maps avoid
        // delimiter clashes). Ordered by the opposite node's centre to reduce crossings.
        const srcOff = new Map(), tgtOff = new Map();
        const fkey = f => f.la + "␟" + f.a + "␟" + f.b + "␟" + f.cat;
        for (let i = 0; i < levels.length - 1; i++) { const la = levels[i], lb = levels[i + 1];
            const bySrc = {}, byTgt = {};
            flows.filter(f => f.la === la).forEach(f => {
                ((bySrc[f.a] = bySrc[f.a] || {})[f.cat] = bySrc[f.a][f.cat] || []).push(f);
                ((byTgt[f.b] = byTgt[f.b] || {})[f.cat] = byTgt[f.b][f.cat] || []).push(f); });
            Object.keys(bySrc).forEach(mc => Object.keys(bySrc[mc]).forEach(cat => { const fs = bySrc[mc][cat]; const nd = NP(la, mc); const seg = nd && nd.catSeg[cat]; if (!seg) return;
                fs.sort((p, q) => { const cp = NP(lb, p.b), cq = NP(lb, q.b); return (cp ? cp.top + cp.h / 2 : 0) - (cq ? cq.top + cq.h / 2 : 0); });
                let yy = seg.y0; fs.forEach(f => { const hh = f.count * scale; srcOff.set(fkey(f), { y0: yy, y1: yy + hh }); yy += hh; }); }));
            Object.keys(byTgt).forEach(mc => Object.keys(byTgt[mc]).forEach(cat => { const fs = byTgt[mc][cat]; const nd = NP(lb, mc); const seg = nd && nd.catSeg[cat]; if (!seg) return;
                fs.sort((p, q) => { const cp = NP(la, p.a), cq = NP(la, q.a); return (cp ? cp.top + cp.h / 2 : 0) - (cq ? cq.top + cq.h / 2 : 0); });
                let yy = seg.y0; fs.forEach(f => { const hh = f.count * scale; tgtOff.set(fkey(f), { y0: yy, y1: yy + hh }); yy += hh; }); }));
        }

        // ---- interactive draw: click a segment/flow to trace its samples ------
        const ribbon = (x0, y0t, y0b, x1, y1t, y1b) => { const mx = (x0 + x1) / 2;
            return `M ${x0} ${y0t} C ${mx} ${y0t} ${mx} ${y1t} ${x1} ${y1t} L ${x1} ${y1b} C ${mx} ${y1b} ${mx} ${y0b} ${x0} ${y0b} Z`; };
        let sel = null;
        const anyIn = arr => { if (!sel) return true; for (let i = 0; i < arr.length; i++) if (sel.set.has(arr[i])) return true; return false; };
        const toggleSel = (key, samples) => { sel = (sel && sel.key === key) ? null : { key, set: new Set(samples) }; draw(); };
        const colorLine = (label, cat, extra) => COLORBY ? `<br><b>${COLORBY}: ${cat}</b>${extra || ""}` : (extra || "");
        const content = g.append("g");

        function draw() {
            __setColLabels(model);
            content.selectAll("*").remove();
            const active = sel != null;

            // selected-subset offsets: re-tile ONLY selected samples from each
            // segment's TOP with the full-layout ordering, so exact sub-ribbons
            // land on the exact segment overlays (flow & segment stay matched).
            const selSrc = new Map(), selTgt = new Map();
            if (active) {
                for (let i = 0; i < levels.length - 1; i++) { const la = levels[i], lb = levels[i + 1];
                    const bySrc = {}, byTgt = {};
                    flows.filter(f => f.la === la).forEach(f => { const sc = f.samples.filter(s => sel.set.has(s)).length; if (sc <= 0) return;
                        ((bySrc[f.a] = bySrc[f.a] || {})[f.cat] = bySrc[f.a][f.cat] || []).push([f, sc]);
                        ((byTgt[f.b] = byTgt[f.b] || {})[f.cat] = byTgt[f.b][f.cat] || []).push([f, sc]); });
                    Object.keys(bySrc).forEach(mc => Object.keys(bySrc[mc]).forEach(cat => { const fs = bySrc[mc][cat]; const nd = NP(la, mc); const seg = nd && nd.catSeg[cat]; if (!seg) return;
                        fs.sort((p, q) => { const cp = NP(lb, p[0].b), cq = NP(lb, q[0].b); return (cp ? cp.top + cp.h / 2 : 0) - (cq ? cq.top + cq.h / 2 : 0); });
                        let yy = seg.y0; fs.forEach(([f, sc]) => { const hh = sc * scale; selSrc.set(fkey(f), { y0: yy, y1: yy + hh }); yy += hh; }); }));
                    Object.keys(byTgt).forEach(mc => Object.keys(byTgt[mc]).forEach(cat => { const fs = byTgt[mc][cat]; const nd = NP(lb, mc); const seg = nd && nd.catSeg[cat]; if (!seg) return;
                        fs.sort((p, q) => { const cp = NP(la, p[0].a), cq = NP(la, q[0].a); return (cp ? cp.top + cp.h / 2 : 0) - (cq ? cq.top + cq.h / 2 : 0); });
                        let yy = seg.y0; fs.forEach(([f, sc]) => { const hh = sc * scale; selTgt.set(fkey(f), { y0: yy, y1: yy + hh }); yy += hh; }); }));
                }
            }

            // whole ribbons (faded when a selection is active; hidden below MINFLOW)
            const fg = content.append("g");
            flows.forEach(f => { if (f.count < MINFLOW) return; const sn = NP(f.la, f.a), tn = NP(f.lb, f.b), so = srcOff.get(fkey(f)), to = tgtOff.get(fkey(f)); if (!sn || !tn || !so || !to) return;
                const x0 = sn.x + NODE_W / 2, x1 = tn.x - NODE_W / 2;
                const selN = active ? f.samples.filter(s => sel.set.has(s)).length : 0;
                const base = active ? (selN > 0 ? 0.18 : 0.05) : 0.5;
                fg.append("path").attr("d", ribbon(x0, so.y0, so.y1, x1, to.y0, to.y1)).attr("fill", catColor[f.cat]).attr("opacity", base).attr("stroke", "none").style("cursor", "pointer")
                    .on("mousemove", e => showTip(`${f.la} ${f.a} → ${f.lb} ${f.b}` + colorLine(null, f.cat, ` · ${f.count} samples`) + (active && selN > 0 ? `<br><b>selected: ${selN}</b>` : ""), e)).on("mouseleave", hideTip)
                    .on("mouseover", function () { d3.select(this).attr("opacity", Math.max(base, 0.6)); }).on("mouseout", function () { d3.select(this).attr("opacity", base); })
                    .on("click", function (e) { e.stopPropagation(); toggleSel("f:" + fkey(f), f.samples); }); });

            // exact sub-ribbons (selected samples only) at their true tiled positions
            if (active) flows.forEach(f => { const so = selSrc.get(fkey(f)), to = selTgt.get(fkey(f)); if (!so || !to) return;
                const sn = NP(f.la, f.a), tn = NP(f.lb, f.b); if (!sn || !tn) return;
                const x0 = sn.x + NODE_W / 2, x1 = tn.x - NODE_W / 2;
                fg.append("path").attr("d", ribbon(x0, so.y0, so.y1, x1, to.y0, to.y1)).attr("fill", catColor[f.cat]).attr("opacity", 0.9).attr("stroke", "none").style("pointer-events", "none"); });

            // nodes (metadata-stacked, wide)
            levels.forEach(lvl => Object.values(nodePos[lvl]).forEach(n => {
                const nodeRel = anyIn(n.samples);
                CATS.forEach(c => { const seg = n.catSeg[c]; if (!seg) return;
                    const segSamples = n.samples.filter(s => valOf(s) === c);
                    const selN = active ? segSamples.filter(s => sel.set.has(s)).length : 0;
                    const op = active ? (selN > 0 ? 0.3 : 0.12) : 1;
                    content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", seg.y0).attr("width", NODE_W).attr("height", seg.h)
                        .attr("fill", catColor[c]).attr("stroke", "#fff").attr("stroke-width", 0.5).attr("opacity", op).style("cursor", "pointer")
                        .on("mousemove", e => showTip(`<b>${n.lvl} · ${n.mc}</b> · ${n.total} samples` + colorLine(null, `<b>${c}</b> ${n.byCat[c]} (${Math.round(n.byCat[c] / n.total * 100)}%)`) + (active && selN > 0 ? `<br><b>selected here: ${selN}</b>` : "") + metaComp(n.samples), e)).on("mouseleave", hideTip)
                        .on("click", function (e) { e.stopPropagation(); toggleSel("n:" + n.lvl + ":" + n.mc + ":" + c, segSamples); });
                    if (active && selN > 0) { const h = selN * scale;
                        content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", seg.y0).attr("width", NODE_W).attr("height", h)
                            .attr("fill", catColor[c]).attr("opacity", 1).attr("stroke", "#111").attr("stroke-width", 0.8).style("pointer-events", "none"); }
                });
                content.append("rect").attr("x", n.x - NODE_W / 2).attr("y", n.top).attr("width", NODE_W).attr("height", n.h).attr("fill", "none").attr("stroke", "#333").attr("stroke-width", 1.5).attr("opacity", active && !nodeRel ? 0.2 : 1).style("pointer-events", "none");
                content.append("text").attr("x", n.x).attr("y", n.top + n.h + 13).attr("text-anchor", "middle").style("font-size", "12px").style("font-weight", "bold").style("fill", active && !nodeRel ? "#bbb" : "#333").text(n.mc);
            }));
        }
        draw();
        svg.on("click", () => { if (sel) { sel = null; draw(); } });

        // ---- level labels (top) + colour legend (bottom) ----
        levels.forEach(lvl => svg.append("text").attr("x", m.l + colX(lvl)).attr("y", 20).attr("text-anchor", "middle").style("font-size", "16px").style("font-weight", "bold").style("fill", "#000").text(lvl));
        const ly = height - legendH + 22;
        const cap = (COLORBY ? COLORBY + "  ·  " : "") + `${SAMPLES.length} samples across ${levels.length} levels`;
        svg.append("text").attr("x", m.l).attr("y", ly).style("font", "bold 14px sans-serif").style("fill", "#111").text(cap);
        if (COLORBY) { let lx = m.l, lyy = ly + 26; const sw = 15;
            CATS.forEach(c => { const cnt = SAMPLES.filter(s => valOf(s) === c).length; const label = `${c} (${cnt})`, wpx = 28 + label.length * 8.2;
                if (lx + wpx > width - m.r) { lx = m.l; lyy += 24; }
                svg.append("rect").attr("x", lx).attr("y", lyy - 12).attr("width", sw).attr("height", sw).attr("rx", 3).attr("fill", catColor[c]);
                svg.append("text").attr("x", lx + sw + 5).attr("y", lyy).style("font", "13px sans-serif").style("fill", "#222").text(label);
                lx += wpx; }); }
        __mountExport(el, "hard_sankey");
    }

    function calculateMetricScales(processedData, rawData, metricConfig) {
        console.log("Calculating metric scales...");

        const perplexityValues = [];
        const coherenceValues = [];

        // Extract metric values from all nodes
        processedData.nodes.forEach(node => {
            const nodeData = rawData.nodes[node.id];
            if (nodeData) {
                // Get perplexity from model_metrics
                if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                    perplexityValues.push(nodeData.model_metrics.perplexity);
                }

                // Get coherence from mallet_diagnostics
                if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
                    coherenceValues.push(nodeData.mallet_diagnostics.coherence);
                }
            }
        });

        console.log(`Found ${perplexityValues.length} perplexity values, ${coherenceValues.length} coherence values`);

        if (perplexityValues.length === 0 || coherenceValues.length === 0) {
            console.warn("Insufficient metric data for metric mode");
            return null;
        }

        // Create scales
        const perplexityExtent = d3.extent(perplexityValues);
        const coherenceExtent = d3.extent(coherenceValues);

        console.log("Perplexity range:", perplexityExtent);
        console.log("Coherence range:", coherenceExtent);

        // Perplexity: lower is better, so we invert the scale (low perplexity = high red intensity)
        const perplexityScale = d3.scaleLinear()
            .domain(perplexityExtent)
            .range([1, 0]); // Inverted: low perplexity gets high value (more red)

        // Coherence: higher is better (less negative), but values are negative
        // More negative = worse, less negative = better
        const coherenceScale = d3.scaleLinear()
            .domain(coherenceExtent)
            .range([0, 1]); // Less negative coherence gets high value (more blue)

        return {
            perplexity: perplexityScale,
            coherence: coherenceScale,
            perplexityExtent,
            coherenceExtent
        };
    }

    function getMetricColor(nodeId, rawData, metricScales, metricConfig, colorMode) {
        if (!metricScales) return "#666";

        const nodeData = rawData.nodes[nodeId];
        if (!nodeData) return "#666";

        let perplexityValue = null;
        let coherenceValue = null;

        // Get perplexity
        if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
            perplexityValue = nodeData.model_metrics.perplexity;
        }

        // Get coherence
        if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
            coherenceValue = nodeData.mallet_diagnostics.coherence;
        }

        // If missing either metric, return gray
        if (perplexityValue === null || coherenceValue === null) {
            return "#999";
        }

        // Calculate normalized scores (0-1)
        const redIntensity = metricScales.perplexity(perplexityValue); // Low perplexity = high red
        const blueIntensity = metricScales.coherence(coherenceValue); // High coherence = high blue

        // Debug logging
        console.log(`${nodeId}: perp=${perplexityValue.toFixed(3)} (red=${redIntensity.toFixed(3)}), coh=${coherenceValue.toFixed(3)} (blue=${blueIntensity.toFixed(3)})`);

        // Ensure minimum brightness to avoid too dark colors
        const minBrightness = 0.2; // Minimum 20% brightness

        // Calculate color components with minimum brightness
        let red = 0, green = 0, blue = 0;
        if (colorMode === 'metric') {
            red = Math.round(255 * Math.max(minBrightness, redIntensity * metricConfig.red_weight));
            blue = Math.round(255 * Math.max(minBrightness, blueIntensity * metricConfig.blue_weight));
        } else if (colorMode === 'perplexity') {
            red = Math.round(255 * Math.max(minBrightness, redIntensity));
        } else if (colorMode === 'coherence') {
            blue = Math.round(255 * Math.max(minBrightness, blueIntensity));
        } else if (colorMode === 'metrics') {
            // 'metrics' mode: use coherence for node coloring (blue intensity)
            blue = Math.round(255 * Math.max(minBrightness, blueIntensity));
        }

        // Ensure values are in valid range
        const clampedRed = Math.max(0, Math.min(255, red));
        const clampedBlue = Math.max(0, Math.min(255, blue));
        const clampedGreen = 0;

        const finalColor = `rgb(${clampedRed}, ${clampedGreen}, ${clampedBlue})`;
        console.log(`${nodeId}: Final color = ${finalColor}`);

        return finalColor;
    }

    function calculateKLevelPerplexity(processedData, rawData) {
        console.log("Calculating K-level perplexity values...");
        
        const kPerplexityValues = {};
        
        // Extract one perplexity value per K level
        processedData.nodes.forEach(node => {
            const nodeData = rawData.nodes[node.id];
            if (nodeData && nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                const k = node.k;
                // Since all LCs within a K level should have the same perplexity, 
                // we only need to store it once per K
                if (kPerplexityValues[k] === undefined) {
                    kPerplexityValues[k] = nodeData.model_metrics.perplexity;
                    console.log(`K=${k}: Perplexity = ${nodeData.model_metrics.perplexity.toFixed(3)}`);
                }
            }
        });
        
        return kPerplexityValues;
    }

    function drawPerplexityBars(g, kValues, kPerplexityValues, metricScales, kSpacing, width) {
        if (!metricScales || !kPerplexityValues) {
            console.log("No metric scales or perplexity values available for bars");
            return;
        }
        
        console.log("Drawing perplexity bars above K labels...");
        
        // Bar dimensions - ensure bars don't go above SVG boundary
        const maxBarHeight = 35; // Reduced to prevent overflow
        const barWidth = Math.min(60, kSpacing * 0.8); // Adaptive width based on spacing
        const barY = -70; // Position above K labels, adjusted to prevent overflow
        
        // Find min/max perplexity for bar height scaling
        const perplexityValues = Object.values(kPerplexityValues);
        const minPerplexity = Math.min(...perplexityValues);
        const maxPerplexity = Math.max(...perplexityValues);
        const perplexityRange = maxPerplexity - minPerplexity;
        
        console.log(`Perplexity range for bars: ${minPerplexity.toFixed(3)} - ${maxPerplexity.toFixed(3)}`);
        
        // Draw bars for each K value
        kValues.forEach((k, index) => {
            const perplexityValue = kPerplexityValues[k];
            if (perplexityValue !== undefined) {
                
                // Calculate bar height (higher perplexity = taller bar)
                const normalizedHeight = perplexityRange > 0 ? 
                    (perplexityValue - minPerplexity) / perplexityRange : 0.5;
                // Ensure bar doesn't extend above the available space
                const barHeight = Math.max(5, Math.min(maxBarHeight, normalizedHeight * maxBarHeight));
                
                // Calculate color using same logic as perplexity mode
                const redIntensity = metricScales.perplexity(perplexityValue);
                const minBrightness = 0.2;
                const red = Math.round(255 * Math.max(minBrightness, redIntensity));
                const barColor = `rgb(${red}, 0, 0)`;
                
                const barX = index * kSpacing - barWidth / 2;
                
                // Draw the bar (no rounded corners)
                g.append("rect")
                    .attr("x", barX)
                    .attr("y", barY - barHeight)
                    .attr("width", barWidth)
                    .attr("height", barHeight)
                    .attr("fill", barColor)
                    .attr("stroke", "#333")
                    .attr("stroke-width", 1)
                    .style("cursor", "pointer")
                    .on("mouseover", function(event) {
                        // Show tooltip with perplexity value
                        const tooltip = g.append("g").attr("class", "perplexity-bar-tooltip");
                        const tooltipText = `K=${k}\\nPerplexity: ${perplexityValue.toFixed(3)}`;
                        const lines = tooltipText.split('\\n');
                        
                        const tooltipWidth = 120;
                        const tooltipHeight = lines.length * 15 + 10;
                        const tooltipX = barX - tooltipWidth/2 + barWidth/2;
                        const tooltipY = barY + 20; // Show below the bar instead of above
                        
                        tooltip.append("rect")
                            .attr("x", tooltipX)
                            .attr("y", tooltipY)
                            .attr("width", tooltipWidth)
                            .attr("height", tooltipHeight)
                            .attr("fill", "white")
                            .attr("stroke", "black")
                            .attr("rx", 3)
                            .attr("opacity", 0.9);
                        
                        lines.forEach((line, i) => {
                            tooltip.append("text")
                                .attr("x", tooltipX + tooltipWidth/2)
                                .attr("y", tooltipY + 15 + i * 15)
                                .attr("text-anchor", "middle")
                                .style("font-size", "11px")
                                .style("font-weight", "bold")
                                .style("fill", "black")
                                .text(line);
                        });
                    })
                    .on("mouseout", function() {
                        g.selectAll(".perplexity-bar-tooltip").remove();
                    });
                
                // Add perplexity value text below the bar
                g.append("text")
                    .attr("x", index * kSpacing)
                    .attr("y", barY + 15)
                    .attr("text-anchor", "middle")
                    .style("font-size", "10px")
                    .style("font-weight", "bold")
                    .style("fill", "#666")
                    .text(perplexityValue.toFixed(2));
            }
        });
        
        // Add title for the perplexity bars - positioned with more space to prevent overflow
        g.append("text")
            .attr("x", width / 2)
            .attr("y", barY - maxBarHeight - 5) // Increased space from -10 to -25
            .attr("text-anchor", "middle")
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Perplexity by K-value");
    }

    function drawColorLegend(g, width, height, metricMode, metricScales, colorMode) {
        // Remove any existing legends
        g.selectAll(".color-legend").remove();
        
        const legendX = 10;
        // Adjust Y position based on mode: metric mode needs more space
        const legendY = colorMode === 'metric' ? height - 180 : height - 120;
        
        const legend = g.append("g")
            .attr("class", "color-legend")
            .attr("transform", `translate(${legendX}, ${legendY})`);
        
        if (!metricMode) {
            // Default mode: K-value colors
            legend.append("text")
                .attr("x", 0)
                .attr("y", -5)
                .style("font-size", "12px")
                .style("font-weight", "bold")
                .style("fill", "#333")
                .text("Topic Colors by K-value");
        } else if (metricScales) {
            // Metric modes with interactive legends
            if (colorMode === 'perplexity') {
                drawPerplexityLegend(legend, metricScales, g);
            } else if (colorMode === 'coherence') {
                drawCoherenceLegend(legend, metricScales, g);
            } else if (colorMode === 'metric') {
                drawMetricLegend(legend, metricScales, g);
            } else if (colorMode === 'metrics') {
                // 'metrics' mode: nodes colored by coherence, bars show perplexity
                drawCoherenceLegend(legend, metricScales, g);
                // Add perplexity legend below coherence legend
                drawPerplexityLegendForMetrics(legend, metricScales, g);
            }
        }
    }
    
    function drawPerplexityLegend(legend, metricScales, g) {
        // Title
        legend.append("text")
            .attr("x", 0)
            .attr("y", -5)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Perplexity (Red Intensity)");
        
        // Create linear gradient for perplexity - access parent SVG correctly
        let svg = g;
        while (svg.node().tagName !== 'svg') {
            svg = d3.select(svg.node().parentNode);
        }
        const defs = svg.selectAll("defs").empty() ? 
                     svg.append("defs") : svg.select("defs");
        
        const gradientId = "perplexity-gradient";
        const gradient = defs.select(`#${gradientId}`).empty() ?
                        defs.append("linearGradient").attr("id", gradientId) :
                        defs.select(`#${gradientId}`);
        
        gradient
            .attr("x1", "0%")
            .attr("x2", "100%")
            .attr("y1", "0%")
            .attr("y2", "0%");
        
        gradient.selectAll("stop").remove();
        gradient.append("stop")
            .attr("offset", "0%")
            .attr("stop-color", "rgb(51, 0, 0)"); // Dark red (high perplexity = poor)
        gradient.append("stop")
            .attr("offset", "100%")
            .attr("stop-color", "rgb(255, 0, 0)"); // Bright red (low perplexity = good)
        
        const barWidth = 200;
        const barHeight = 15;
        
        // Draw gradient bar
        legend.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", barWidth)
            .attr("height", barHeight)
            .attr("fill", `url(#${gradientId})`)
            .attr("stroke", "#333")
            .attr("stroke-width", 1);
        
        // Add labels
        const extent = metricScales.perplexityExtent;
        legend.append("text")
            .attr("x", 0)
            .attr("y", barHeight + 12)
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[1].toFixed(2)} (poor)`);
        
        legend.append("text")
            .attr("x", barWidth)
            .attr("y", barHeight + 12)
            .attr("text-anchor", "end")
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[0].toFixed(2)} (good)`);
        
        // Create hover pointer
        const pointer = legend.append("g")
            .attr("class", "legend-pointer")
            .style("display", "none");
        
        pointer.append("line")
            .attr("x1", 0)
            .attr("x2", 0)
            .attr("y1", 10)
            .attr("y2", 35)
            .attr("stroke", "#ff6b35")
            .attr("stroke-width", 2);
        
        pointer.append("circle")
            .attr("cx", 0)
            .attr("cy", 22.5)
            .attr("r", 3)
            .attr("fill", "#ff6b35")
            .attr("stroke", "white")
            .attr("stroke-width", 1);
    }
    
    function drawCoherenceLegend(legend, metricScales, g) {
        // Title
        legend.append("text")
            .attr("x", 0)
            .attr("y", -5)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Coherence (Blue Intensity)");
        
        // Create linear gradient for coherence - access parent SVG correctly
        let svg = g;
        while (svg.node().tagName !== 'svg') {
            svg = d3.select(svg.node().parentNode);
        }
        const defs = svg.selectAll("defs").empty() ? 
                     svg.append("defs") : svg.select("defs");
        
        const gradientId = "coherence-gradient";
        const gradient = defs.select(`#${gradientId}`).empty() ?
                        defs.append("linearGradient").attr("id", gradientId) :
                        defs.select(`#${gradientId}`);
        
        gradient
            .attr("x1", "0%")
            .attr("x2", "100%")
            .attr("y1", "0%")
            .attr("y2", "0%");
        
        gradient.selectAll("stop").remove();
        gradient.append("stop")
            .attr("offset", "0%")
            .attr("stop-color", "rgb(0, 0, 51)"); // Dark blue (low coherence = poor)
        gradient.append("stop")
            .attr("offset", "100%")
            .attr("stop-color", "rgb(0, 0, 255)"); // Bright blue (high coherence = good)
        
        const barWidth = 200;
        const barHeight = 15;
        
        // Draw gradient bar
        legend.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", barWidth)
            .attr("height", barHeight)
            .attr("fill", `url(#${gradientId})`)
            .attr("stroke", "#333")
            .attr("stroke-width", 1);

        // Add labels
        const extent = metricScales.coherenceExtent;
        legend.append("text")
            .attr("x", 0)
            .attr("y", barHeight + 12)
            .attr("text-anchor", "start")
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[0].toFixed(2)} (poor)`);

        legend.append("text")
            .attr("x", barWidth)
            .attr("y", barHeight + 12)
            .attr("text-anchor", "end")
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[1].toFixed(2)} (good)`);
        
        // Create hover pointer
        const pointer = legend.append("g")
            .attr("class", "legend-pointer")
            .style("display", "none");
        
        pointer.append("line")
            .attr("x1", 0)
            .attr("x2", 0)
            .attr("y1", 10)
            .attr("y2", 35)
            .attr("stroke", "#ff6b35")
            .attr("stroke-width", 2);
        
        pointer.append("circle")
            .attr("cx", 0)
            .attr("cy", 22.5)
            .attr("r", 3)
            .attr("fill", "#ff6b35")
            .attr("stroke", "white")
            .attr("stroke-width", 1);
    }
    
    function drawPerplexityLegendForMetrics(legend, metricScales, g) {
        // Perplexity legend positioned below coherence legend
        const yOffset = 60; // Position below coherence legend
        
        const perplexityLegend = legend.append("g")
            .attr("class", "perplexity-legend-metrics")
            .attr("transform", `translate(0, ${yOffset})`);
            
        // Title
        perplexityLegend.append("text")
            .attr("x", 0)
            .attr("y", -5)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Perplexity (Bar Height)");
        
        // Create linear gradient for perplexity - access parent SVG correctly
        let svg = g;
        while (svg.node().tagName !== 'svg') {
            svg = d3.select(svg.node().parentNode);
        }
        const defs = svg.selectAll("defs").empty() ? 
                     svg.append("defs") : svg.select("defs");
        
        const gradientId = "perplexity-metrics-gradient";
        const gradient = defs.select(`#${gradientId}`).empty() ?
                        defs.append("linearGradient").attr("id", gradientId) :
                        defs.select(`#${gradientId}`);
        
        gradient
            .attr("x1", "0%")
            .attr("x2", "100%")
            .attr("y1", "0%")
            .attr("y2", "0%");
        
        gradient.selectAll("stop").remove();
        gradient.append("stop")
            .attr("offset", "0%")
            .attr("stop-color", "rgb(51, 0, 0)"); // Dark red (high perplexity = poor)
        gradient.append("stop")
            .attr("offset", "100%")
            .attr("stop-color", "rgb(255, 0, 0)"); // Bright red (low perplexity = good)
        
        const barWidth = 200;
        const barHeight = 15;
        
        // Draw gradient bar
        perplexityLegend.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", barWidth)
            .attr("height", barHeight)
            .attr("fill", `url(#${gradientId})`)
            .attr("stroke", "#333")
            .attr("stroke-width", 1);
        
        // Add labels
        const extent = metricScales.perplexityExtent;
        perplexityLegend.append("text")
            .attr("x", 0)
            .attr("y", barHeight + 12)
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[1].toFixed(2)} (poor)`);
        
        perplexityLegend.append("text")
            .attr("x", barWidth)
            .attr("y", barHeight + 12)
            .attr("text-anchor", "end")
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${extent[0].toFixed(2)} (good)`);
    }
    
    function drawMetricLegend(legend, metricScales, g) {
        // Title
        legend.append("text")
            .attr("x", 0)
            .attr("y", -5)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Quality: Perplexity × Coherence");
        
        const rectSize = 100;
        
        // Create 2D gradient for metric mode - access parent SVG correctly
        let svg = g;
        while (svg.node().tagName !== 'svg') {
            svg = d3.select(svg.node().parentNode);
        }
        const defs = svg.selectAll("defs").empty() ? 
                     svg.append("defs") : svg.select("defs");
        
        // Create a pattern with multiple gradients to simulate 2D color space
        const patternId = "metric-pattern";
        const pattern = defs.select(`#${patternId}`).empty() ?
                       defs.append("pattern").attr("id", patternId) :
                       defs.select(`#${patternId}`);
        
        pattern
            .attr("patternUnits", "userSpaceOnUse")
            .attr("width", rectSize)
            .attr("height", rectSize);
        
        pattern.selectAll("*").remove();
        
        // Create color matrix for 2D space - FIXED for negative coherence values
        const resolution = 20;
        for (let i = 0; i < resolution; i++) {
            for (let j = 0; j < resolution; j++) {
                const xPercent = i / (resolution - 1);  // X = perplexity (red) - left to right
                
                // For coherence: since higher (less negative) is better
                // Top of matrix should represent better coherence
                const yPercent = j / (resolution - 1);
                const coherencePercent = yPercent;  // Remove the (1 - yPercent)
                
                const red = Math.round(255 * Math.max(0.2, xPercent * 0.8));
                const blue = Math.round(255 * Math.max(0.2, coherencePercent * 0.8));
                
                pattern.append("rect")
                    .attr("x", (i / resolution) * rectSize)
                    .attr("y", (j / resolution) * rectSize)
                    .attr("width", rectSize / resolution + 0.5)  // Remove grid gaps
                    .attr("height", rectSize / resolution + 0.5) // Remove grid gaps
                    .attr("fill", `rgb(${red}, 0, ${blue})`)
                    .attr("stroke", "none");  // Remove grid lines
            }
        }
        
        // Draw the 2D color space
        legend.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", rectSize)
            .attr("height", rectSize)
            .attr("fill", `url(#${patternId})`)
            .attr("stroke", "#333")
            .attr("stroke-width", 1);
        
        // Add axis labels
        legend.append("text")
            .attr("x", rectSize / 2)
            .attr("y", rectSize + 15)
            .attr("text-anchor", "middle")
            .style("font-size", "10px")
            .style("fill", "#333")
            .text("Perplexity (Red) →");
        
        legend.append("text")
            .attr("x", -10)
            .attr("y", rectSize / 2)
            .attr("text-anchor", "middle")
            .attr("transform", `rotate(-90, -10, ${rectSize / 2})`)
            .style("font-size", "10px")
            .style("fill", "#333")
            .text("Coherence (Blue) →");
        
        // Create hover pointer for 2D space
        const pointer = legend.append("g")
            .attr("class", "legend-pointer")
            .style("display", "none");
        
        pointer.append("circle")
            .attr("cx", 0)
            .attr("cy", 0)
            .attr("r", 4)
            .attr("fill", "none")
            .attr("stroke", "#ff6b35")
            .attr("stroke-width", 2);
        
        pointer.append("circle")
            .attr("cx", 0)
            .attr("cy", 0)
            .attr("r", 2)
            .attr("fill", "#ff6b35");
    }
    
    function updateLegendPointer(nodeId, rawData, metricScales, colorMode) {
        if (!metricScales || !rawData.nodes[nodeId]) return;
        
        const nodeData = rawData.nodes[nodeId];
        let perplexityValue = null;
        let coherenceValue = null;
        
        if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
            perplexityValue = nodeData.model_metrics.perplexity;
        }
        if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
            coherenceValue = nodeData.mallet_diagnostics.coherence;
        }
        
        if (perplexityValue === null || coherenceValue === null) return;
        
        // Find the correct legend pointer based on the color mode
        const pointer = d3.select(".color-legend .legend-pointer");
        if (pointer.empty()) return;
        
        pointer.style("display", "block");
        
        if (colorMode === 'perplexity') {
            const redIntensity = metricScales.perplexity(perplexityValue);
            const x = redIntensity * 200;
            pointer.attr("transform", `translate(${x}, 0)`);
        } else if (colorMode === 'coherence') {
            const blueIntensity = metricScales.coherence(coherenceValue);
            const x = blueIntensity * 200;
            pointer.attr("transform", `translate(${x}, 0)`);
        } else if (colorMode === 'metric') {
            const redIntensity = metricScales.perplexity(perplexityValue);
            const blueIntensity = metricScales.coherence(coherenceValue);
            const x = redIntensity * 100;
            const y = (1 - blueIntensity) * 100; // No offset needed since legend now starts at y=0
            pointer.attr("transform", `translate(${x}, ${y})`);
        }
    }
    
    function hideLegendPointer() {
        const pointer = d3.select(".color-legend .legend-pointer");
        if (!pointer.empty()) {
            pointer.style("display", "none");
        }
    }

    function drawMetricLegendOld(svg, metricScales, metricConfig, width, height, margin) {
        const legend = svg.append("g")
            .attr("class", "metric-legend")
            .attr("transform", `translate(${margin.left}, ${height - margin.bottom + 10})`);

        // Title
        legend.append("text")
            .attr("x", 0)
            .attr("y", 0)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#333")
            .text("Metric Mode: Perplexity (Red) × Coherence (Blue) = Quality (Purple)");

        // Color gradient demonstration
        const gradientWidth = 200;
        const gradientHeight = 15;

        // Create gradient definition
        const defs = svg.append("defs");

        const gradient = defs.append("linearGradient")
            .attr("id", "metric-gradient")
            .attr("x1", "0%")
            .attr("x2", "100%")
            .attr("y1", "0%")
            .attr("y2", "0%");

        // Add gradient stops to show the correct color mapping
        const stops = [
            { offset: "0%", color: "rgb(255, 0, 0)" },     // Pure red (high perplexity, low coherence)
            { offset: "25%", color: "rgb(200, 0, 55)" },   // Red-purple (high perplexity, medium coherence)  
            { offset: "50%", color: "rgb(128, 0, 128)" },  // Pure purple (medium perplexity, medium coherence)
            { offset: "75%", color: "rgb(55, 0, 200)" },   // Blue-purple (low perplexity, high coherence)
            { offset: "100%", color: "rgb(0, 0, 255)" }    // Pure blue (low perplexity, high coherence)
        ];

        stops.forEach(stop => {
            gradient.append("stop")
                .attr("offset", stop.offset)
                .attr("stop-color", stop.color);
        });

        // Draw gradient bar
        legend.append("rect")
            .attr("x", 0)
            .attr("y", 0)
            .attr("width", gradientWidth)
            .attr("height", gradientHeight)
            .attr("fill", "url(#metric-gradient)")
            .attr("stroke", "#333")
            .attr("stroke-width", 1);

        // Add labels with correct interpretation
        legend.append("text")
            .attr("x", 0)
            .attr("y", 45)
            .style("font-size", "10px")
            .style("fill", "#d62728")
            .text("Poor Quality");

        legend.append("text")
            .attr("x", gradientWidth/2)
            .attr("y", 45)
            .attr("text-anchor", "middle")
            .style("font-size", "10px")
            .style("fill", "#7f4f7f")
            .text("Good Quality");

        legend.append("text")
            .attr("x", gradientWidth)
            .attr("y", 45)
            .attr("text-anchor", "end")
            .style("font-size", "10px")
            .style("fill", "#2f2fdf")
            .text("Excellent Quality");

        // Show current ranges with better formatting
        legend.append("text")
            .attr("x", gradientWidth + 20)
            .attr("y", 20)
            .style("font-size", "9px")
            .style("fill", "#666")
            .text(`Perplexity: ${metricScales.perplexityExtent[1].toFixed(2)} (poor) - ${metricScales.perplexityExtent[0].toFixed(2)} (good)`);

        legend.append("text")
            .attr("x", gradientWidth + 20)
            .attr("y", 35)
            .style("font-size", "9px")
            .style("fill", "#666")
            .text(`Coherence: ${metricScales.coherenceExtent[0].toFixed(2)} (poor) - ${metricScales.coherenceExtent[1].toFixed(2)} (good)`);
    }

    function processDataForVisualization(data) {
        const nodes = [];
        const flows = [];
        const kValues = data.k_range || [];

        // Process nodes - convert from dictionary to array
        Object.entries(data.nodes || {}).forEach(([nodeName, nodeData]) => {
            // Accepts both spellings: data written before the LC -> LC rename
            // still carries `K2_MC0` node names.
            const match = nodeName.match(/K(\d+)_(?:MC|LC)(\d+)/);
            if (match) {
                const k = parseInt(match[1]);
                const mc = parseInt(match[2]);

                nodes.push({
                    id: nodeName,
                    k: k,
                    mc: mc,
                    highCount: nodeData.high_count || 0,
                    mediumCount: nodeData.medium_count || 0,
                    totalProbability: nodeData.total_probability || 0,
                    highSamples: nodeData.high_samples || [],
                    mediumSamples: nodeData.medium_samples || []
                });
            }
        });

        // Process flows
        (data.flows || []).forEach(flow => {
            flows.push({
                source: flow.source_segment,
                target: flow.target_segment,
                sourceK: flow.source_k,
                targetK: flow.target_k,
                sampleCount: flow.sample_count || 0,
                averageProbability: flow.average_probability || 0,
                samples: flow.samples || []
            });
        });

        console.log(`Processed ${nodes.length} nodes and ${flows.length} flows`);
        return { nodes, flows, kValues };
    }

    function drawSankeyDiagram(g, data, width, height, colorSchemes, selectedFlow, model, metricMode, metricScales, metricConfig) {
        __setColLabels(model);
        const { nodes, flows, kValues } = data;
        const rawData = model.get("sankey_data");

        if (nodes.length === 0) {
            g.append("text")
                .attr("x", width / 2)
                .attr("y", height / 2)
                .attr("text-anchor", "middle")
                .style("font-size", "16px")
                .style("fill", "#666")
                .text("No nodes to display");
            return;
        }

        // Filter flows - use configurable minimum flow threshold
        const minFlowSamples = model.get("min_flow_samples") || 10;
        const significantFlows = flows.filter(flow => flow.sampleCount >= minFlowSamples);
        console.log(`Showing ${significantFlows.length} flows out of ${flows.length} (filtered flows < ${minFlowSamples} samples)`);

        // Calculate positions with barycenter optimization
        const kSpacing = width / Math.max(1, kValues.length - 1);
        const nodesByK = d3.group(nodes, d => d.k);

        // Find max total count for scaling node heights
        const maxTotalCount = d3.max(nodes, d => d.highCount + d.mediumCount) || 1;
        const minNodeHeight = 20;
        const maxNodeHeight = 120;
        const minGap = 5; // Minimum gap between nodes
        
        // ADAPTIVE SCALING: Calculate required space for densest column
        console.log("=== Adaptive Node Scaling ===");
        
        // Calculate original node heights for all nodes
        nodes.forEach(node => {
            const totalSamples = node.highCount + node.mediumCount;
            node.originalHeight = minNodeHeight + (totalSamples / maxTotalCount) * (maxNodeHeight - minNodeHeight);
        });
        
        // Calculate space requirements for each K-level column
        const columnRequirements = {};
        kValues.forEach(k => {
            const kNodes = nodesByK.get(k) || [];
            let totalHeight = 0;
            
            // Sum up all node heights in this column
            kNodes.forEach(node => {
                totalHeight += node.originalHeight;
            });
            
            // Add gaps between nodes (n-1 gaps for n nodes)
            if (kNodes.length > 1) {
                totalHeight += (kNodes.length - 1) * minGap;
            }
            
            columnRequirements[k] = totalHeight;
            console.log(`K=${k}: ${kNodes.length} nodes, required height = ${totalHeight.toFixed(1)}px`);
        });
        
        // Find the densest column (requiring most space)
        const maxRequiredHeight = Math.max(...Object.values(columnRequirements));
        const availableHeight = height - 40; // Leave margin for labels
        
        console.log(`Densest column requires: ${maxRequiredHeight.toFixed(1)}px`);
        console.log(`Available height: ${availableHeight}px`);
        
        // Calculate scaling factor
        let scalingFactor = 1.0;
        let scaledMinHeight = minNodeHeight;
        let scaledMaxHeight = maxNodeHeight;
        let scaledGap = minGap;
        
        if (maxRequiredHeight > availableHeight) {
            scalingFactor = availableHeight / maxRequiredHeight;
            scaledMinHeight = minNodeHeight * scalingFactor;
            scaledMaxHeight = maxNodeHeight * scalingFactor;
            scaledGap = minGap * scalingFactor;
            
            console.log(`Scaling factor applied: ${scalingFactor.toFixed(3)}`);
            console.log(`Scaled min height: ${scaledMinHeight.toFixed(1)}px`);
            console.log(`Scaled max height: ${scaledMaxHeight.toFixed(1)}px`);
            console.log(`Scaled gap: ${scaledGap.toFixed(1)}px`);
        } else {
            console.log("No scaling needed - nodes fit perfectly!");
        }
        
        // Apply scaled heights to all nodes
        nodes.forEach(node => {
            const totalSamples = node.highCount + node.mediumCount;
            node.height = scaledMinHeight + (totalSamples / maxTotalCount) * (scaledMaxHeight - scaledMinHeight);
        });
        
        console.log("=== Adaptive Scaling Complete ===");

        // Apply barycenter method for node ordering (with updated scaled gap)
        const optimizedNodePositions = optimizeNodeOrderWithGap(nodes, significantFlows, kValues, nodesByK, height, scaledGap);

        // Position nodes using optimized order
        nodes.forEach(node => {
            const kIndex = kValues.indexOf(node.k);
            node.x = kIndex * kSpacing;
            node.y = optimizedNodePositions[node.id];
        });

        // Calculate flow width scaling
        const maxFlowCount = d3.max(significantFlows, d => d.sampleCount) || 1;
        const minFlowWidth = 2;
        const maxFlowWidth = 25;

        // Draw flows first (behind nodes)
        const flowGroup = g.append("g").attr("class", "flows");

        significantFlows.forEach((flow, flowIndex) => {
            // Parse source and target segment names
            const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
            const targetTopicId = flow.target.replace(/_high$|_medium$/, '');
            const sourceLevel = flow.source.includes('_high') ? 'high' : 'medium';
            const targetLevel = flow.target.includes('_high') ? 'high' : 'medium';

            const sourceNode = nodes.find(n => n.id === sourceTopicId);
            const targetNode = nodes.find(n => n.id === targetTopicId);

            if (sourceNode && targetNode && flow.sampleCount > 0) {
                // Proportional flow width scaling
                const flowWidth = minFlowWidth + (flow.sampleCount / maxFlowCount) * (maxFlowWidth - minFlowWidth);

                // Calculate connection points on the stacked bars
                const sourceY = calculateSegmentY(sourceNode, sourceLevel);
                const targetY = calculateSegmentY(targetNode, targetLevel);

                // Create curved path
                const curvePath = createCurvePath(
                    sourceNode.x + 15, sourceY,
                    targetNode.x - 15, targetY
                );

                // Check if this flow is selected
                const isSelected = selectedFlow && 
                    selectedFlow.source === flow.source && 
                    selectedFlow.target === flow.target &&
                    selectedFlow.sourceK === flow.sourceK &&
                    selectedFlow.targetK === flow.targetK;

                flowGroup.append("path")
                    .attr("d", curvePath)
                    .attr("stroke", isSelected ? "#ff6b35" : "#888")
                    .attr("stroke-width", isSelected ? flowWidth + 3 : flowWidth)
                    .attr("fill", "none")
                    .attr("opacity", isSelected ? 1.0 : 0.6)
                    .attr("class", `flow-${flowIndex}`)
                    .style("cursor", "pointer")
                    .on("mouseover", function(event) {
                        if (!isSelected) {
                            d3.select(this).attr("opacity", 0.8);
                        }
                        showTooltip(g, event, flow);
                    })
                    .on("mouseout", function() {
                        if (!isSelected) {
                            d3.select(this).attr("opacity", 0.6);
                        }
                        g.selectAll(".tooltip").remove();
                    })
                    .on("click", function(event) {
                        event.stopPropagation();
                        console.log("Flow clicked:", flow);

                        // Clear previous selection or select new flow
                        if (isSelected) {
                            model.set("selected_flow", {});
                        } else {
                            model.set("selected_flow", {
                                source: flow.source,
                                target: flow.target,
                                sourceK: flow.sourceK,
                                targetK: flow.targetK,
                                samples: flow.samples,
                                sampleCount: flow.sampleCount
                            });
                        }
                        model.save_changes();
                    });
            }
        });

        // Create sample tracing layer (initially empty)
        const tracingGroup = g.append("g").attr("class", "sample-tracing");

        // Draw nodes as stacked bars
        const nodeGroup = g.append("g").attr("class", "nodes");

        nodes.forEach(node => {
            const nodeG = nodeGroup.append("g")
                .attr("class", "node")
                .attr("transform", `translate(${node.x}, ${node.y - node.height/2})`);

            // Determine base color based on mode
            let baseColor;
            if (metricMode && metricScales) {
                baseColor = getMetricColor(node.id, rawData, metricScales, metricConfig, model.get("color_mode"));
            } else {
                baseColor = colorSchemes[node.k] || "#666";
            }

            // Calculate segment heights proportionally
            const totalCount = node.highCount + node.mediumCount;
            let highHeight = 0;
            let mediumHeight = 0;

            if (totalCount > 0) {
                highHeight = (node.highCount / totalCount) * node.height;
                mediumHeight = (node.mediumCount / totalCount) * node.height;
            }

            // In metric mode, use uniform colors; in default mode, use darker/lighter
            if (highHeight > 0) {
                const highColor = metricMode ? baseColor : d3.color(baseColor).darker(0.8);

                nodeG.append("rect")
                    .attr("x", -10)
                    .attr("y", 0)
                    .attr("width", 20)
                    .attr("height", highHeight)
                    .attr("fill", highColor)
                    .attr("stroke", "white")
                    .attr("stroke-width", 1)
                    .attr("class", `segment-${node.id}-high`)
                    .style("cursor", "pointer")
                    .on("mouseover", function(event) {
                        d3.select(this).attr("opacity", 0.8);
                        showSegmentTooltip(g, event, node, 'high', node.highCount, rawData, metricMode, model);
                        // Update legend pointer if in metric mode
                        if (metricMode && metricScales) {
                            updateLegendPointer(node.id, rawData, metricScales, model.get("color_mode"));
                        }
                    })
                    .on("mouseout", function() {
                        d3.select(this).attr("opacity", 1);
                        g.selectAll(".tooltip").remove();
                        // Hide legend pointer
                        if (metricMode) {
                            hideLegendPointer();
                        }
                    });
            }

            // Draw medium representation segment with hover
            if (mediumHeight > 0) {
                const mediumColor = metricMode ? baseColor : baseColor;

                nodeG.append("rect")
                    .attr("x", -10)
                    .attr("y", highHeight)
                    .attr("width", 20)
                    .attr("height", mediumHeight)
                    .attr("fill", mediumColor)
                    .attr("stroke", "white")
                    .attr("stroke-width", 1)
                    .attr("class", `segment-${node.id}-medium`)
                    .style("cursor", "pointer")
                    .on("mouseover", function(event) {
                        d3.select(this).attr("opacity", 0.8);
                        showSegmentTooltip(g, event, node, 'medium', node.mediumCount, rawData, metricMode, model);
                        // Update legend pointer if in metric mode
                        if (metricMode && metricScales) {
                            updateLegendPointer(node.id, rawData, metricScales, model.get("color_mode"));
                        }
                    })
                    .on("mouseout", function() {
                        d3.select(this).attr("opacity", 1);
                        g.selectAll(".tooltip").remove();
                        // Hide legend pointer
                        if (metricMode) {
                            hideLegendPointer();
                        }
                    });
            }

            // Add node label (only LC number, no sample count)
            nodeG.append("text")
                .attr("x", 25)
                .attr("y", node.height / 2)
                .attr("dy", "0.35em")
                .style("font-size", "11px")
                .style("font-weight", "bold")
                .style("fill", "#333")
                .text(`LC${node.mc}`)
                .style("cursor", "pointer")
                .on("click", function() {
                    console.log("Node clicked:", node);
                });
        });

        // Add click handler to clear selection when clicking on background
        g.on("click", function() {
            model.set("selected_flow", {});
            model.save_changes();
        });

        // Add K value labels at the top
        kValues.forEach((k, index) => {
            const labelColor = metricMode ? "#333" : (colorSchemes[k] || "#333");
            g.append("text")
                .attr("x", index * kSpacing)
                .attr("y", -30)
                .attr("text-anchor", "middle")
                .style("font-size", "16px")
                .style("font-weight", "bold")
                .style("fill", labelColor)
                .text(__colLabel(k, `K=${k}`));
        });

        // Draw perplexity bars for 'metrics' mode
        if (model.get("color_mode") === 'metrics' && metricMode && metricScales) {
            const kPerplexityValues = calculateKLevelPerplexity({nodes, flows, kValues}, rawData);
            drawPerplexityBars(g, kValues, kPerplexityValues, metricScales, kSpacing, width);
        }

        // Add color legend with hover functionality
        drawColorLegend(g, width, height, metricMode, metricScales, model.get("color_mode"));

        // Initial sample tracing if there's already a selected flow
        if (selectedFlow && Object.keys(selectedFlow).length > 0) {
            updateSampleTracing(g, data, selectedFlow, nodes, significantFlows, kValues, model);
        }
    }

    function updateSampleTracing(g, data, selectedFlow, nodes, flows, kValues, model) {
        // Clear previous tracing
        g.selectAll(".sample-tracing").selectAll("*").remove();
        g.selectAll(".sample-count-badge").remove();
        g.selectAll(".sample-info-panel").remove();

        // Reset segment highlighting - set all segments back to white borders
        g.selectAll(".nodes rect").attr("stroke", "white").attr("stroke-width", 1);

        if (!selectedFlow || Object.keys(selectedFlow).length === 0) {
            return;
        }

        console.log("Tracing samples for selected flow:", selectedFlow);

        const tracingGroup = g.select(".sample-tracing");
        const samples = selectedFlow.samples || [];
        const sampleIds = samples.map(s => s.sample);

        console.log(`Tracing ${sampleIds.length} samples:`, sampleIds.slice(0, 3));

        if (sampleIds.length === 0) {
            showSampleInfo(g, selectedFlow, 0);
            return;
        }

        // Find where these samples are assigned across all K values
        const sampleAssignments = traceSampleAssignments(sampleIds, data, flows, kValues);

        // Draw sample trajectory paths with count-based line weights
        const minFlowSamples = model.get("min_flow_samples") || 10;
        drawSampleTrajectories(tracingGroup, sampleAssignments, nodes, selectedFlow, data, minFlowSamples);

        // Highlight segments containing these samples
        highlightSampleSegments(g, sampleAssignments, nodes);

        // Show detailed sample info panel
        showSampleInfo(g, selectedFlow, sampleIds.length);
    }

    function traceSampleAssignments(sampleIds, data, flows, kValues) {
        console.log("Tracing sample assignments across K values...");
        const assignments = {};

        // Initialize assignment tracking for each sample
        sampleIds.forEach(sampleId => {
            assignments[sampleId] = {};
        });

        // Go through all flows to find where samples appear
        flows.forEach(flow => {
            if (flow.samples && flow.samples.length > 0) {
                flow.samples.forEach(sampleData => {
                    const sampleId = sampleData.sample;

                    if (sampleIds.includes(sampleId)) {
                        // Extract topic and level from source segment
                        const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                        const sourceLevel = flow.source.includes('_high') ? 'high' : 'medium';

                        // Extract topic and level from target segment  
                        const targetTopicId = flow.target.replace(/_high$|_medium$/, '');
                        const targetLevel = flow.target.includes('_high') ? 'high' : 'medium';

                        // Record source assignment
                        assignments[sampleId][flow.sourceK] = {
                            topicId: sourceTopicId,
                            level: sourceLevel,
                            probability: sampleData.source_prob || 0
                        };

                        // Record target assignment
                        assignments[sampleId][flow.targetK] = {
                            topicId: targetTopicId,
                            level: targetLevel,
                            probability: sampleData.target_prob || 0
                        };
                    }
                });
            }
        });

        console.log("Sample assignments traced:", Object.keys(assignments).length, "samples");
        return assignments;
    }

    function drawSampleTrajectories(tracingGroup, sampleAssignments, nodes, selectedFlow, data, minFlowSamples) {
        const trajectoryColor = "#ff6b35";
        const sampleIds = Object.keys(sampleAssignments);

        console.log(`Drawing trajectories for ${sampleIds.length} samples`);

        // First, calculate sample counts for each segment to determine line weights
        const segmentCounts = {};
        Object.values(sampleAssignments).forEach(assignments => {
            Object.values(assignments).forEach(assignment => {
                const segmentKey = `${assignment.topicId}-${assignment.level}`;
                segmentCounts[segmentKey] = (segmentCounts[segmentKey] || 0) + 1;
            });
        });

        // Use the SAME scaling as the main sankey diagram flows - using the passed configurable threshold
        const allFlows = data.flows.filter(flow => flow.sampleCount >= minFlowSamples);
        const maxFlowCount = d3.max(allFlows, d => d.sampleCount) || 1;
        const minFlowWidth = 2;
        const maxFlowWidth = 25;
    
        // Function to get line weight using same formula as sankey flows
        const getSankeyLineWeight = (count) => {
            return minFlowWidth + (count / maxFlowCount) * (maxFlowWidth - minFlowWidth);
        };

        sampleIds.forEach((sampleId, sampleIndex) => {
            const assignments = sampleAssignments[sampleId];
            const pathPoints = [];

            // Convert assignments to path points with coordinates
            Object.entries(assignments).forEach(([k, assignment]) => {
                const node = nodes.find(n => n.id === assignment.topicId);
                if (node) {
                    const segmentY = calculateSegmentY(node, assignment.level);
                    pathPoints.push({
                        k: parseInt(k),
                        x: node.x,
                        y: segmentY,
                        topicId: assignment.topicId,
                        level: assignment.level,
                        probability: assignment.probability,
                        sampleCount: segmentCounts[`${assignment.topicId}-${assignment.level}`] || 0
                    });
                }
            });

            // Sort path points by K value
            pathPoints.sort((a, b) => a.k - b.k);

            if (pathPoints.length >= 2) {
                // Draw trajectory ONLY between adjacent K values
                for (let i = 0; i < pathPoints.length - 1; i++) {
                    const start = pathPoints[i];
                    const end = pathPoints[i + 1];

                    // CRITICAL FIX: Only draw lines between adjacent K values
                    if (end.k - start.k === 1) {
                        // Check if this segment is the selected flow
                        const isSelectedSegment = 
                            start.k === selectedFlow.sourceK && 
                            end.k === selectedFlow.targetK;

                        // Calculate line weight using same scaling as sankey diagram
                        // Use the minimum sample count as the "flow capacity" between segments
                        const trajectoryFlowCount = Math.min(start.sampleCount, end.sampleCount);
                        const lineWeight = getSankeyLineWeight(trajectoryFlowCount);

                        const curvePath = createCurvePath(
                            start.x + 15, start.y,
                            end.x - 15, end.y
                        );

                        // ALL trajectory lines are now SOLID (no dashed lines)
                        tracingGroup.append("path")
                            .attr("d", curvePath)
                            .attr("stroke", trajectoryColor)
                            .attr("stroke-width", isSelectedSegment ? lineWeight + 2 : lineWeight)
                            .attr("stroke-dasharray", "none") // Always solid lines
                            .attr("fill", "none")
                            .attr("opacity", isSelectedSegment ? 0.9 : 0.7) // Slightly higher opacity for solid lines
                            .attr("class", `trajectory-${sampleIndex}-${i}`)
                            .style("pointer-events", "none");
                    }
                    // If end.k - start.k > 1, we skip drawing the line (gap in trajectory)
                }

                // Add dots at each assignment point (size proportional to sample count)
                const maxSampleCount = Math.max(...Object.values(segmentCounts));
                pathPoints.forEach((point, pointIndex) => {
                    // Scale dot size based on sample count using sankey proportions
                    const baseDotSize = 3;
                    const maxDotSize = 8; // Slightly larger to match sankey scale
                    const dotRadius = maxSampleCount > 0 ? 
                        baseDotSize + (point.sampleCount / maxSampleCount) * (maxDotSize - baseDotSize) : 
                        baseDotSize;

                    tracingGroup.append("circle")
                        .attr("cx", point.x)
                        .attr("cy", point.y)
                        .attr("r", dotRadius)
                        .attr("fill", trajectoryColor)
                        .attr("stroke", "white")
                        .attr("stroke-width", 1.5)
                        .attr("opacity", 0.8)
                        .attr("class", `trajectory-point-${sampleIndex}-${pointIndex}`)
                        .style("pointer-events", "none");
                });
            }
        });

        console.log("Sample trajectories drawn with sankey-matching line weights (all solid)");
    }

    function highlightSampleSegments(g, sampleAssignments, nodes) {
        const highlightColor = "#ff6b35";

        // Count how many samples are in each segment
        const segmentCounts = {};

        Object.values(sampleAssignments).forEach(assignments => {
            Object.values(assignments).forEach(assignment => {
                const segmentKey = `${assignment.topicId}-${assignment.level}`;
                segmentCounts[segmentKey] = (segmentCounts[segmentKey] || 0) + 1;
            });
        });

        console.log("Segment counts:", segmentCounts);

        // Highlight segments and add count badges
        Object.entries(segmentCounts).forEach(([segmentKey, count]) => {
            const [topicId, level] = segmentKey.split('-');

            // Highlight the segment with orange border
            g.selectAll(`.segment-${topicId}-${level}`)
                .attr("stroke", highlightColor)
                .attr("stroke-width", 3);

            // Find the node to position the count badge
            const node = nodes.find(n => n.id === topicId);
            if (node) {
                const badgeY = level === 'high' ? 
                    node.y - node.height/2 + 15 : 
                    node.y + node.height/2 - 15;

                // Add count badge
                g.append("circle")
                    .attr("cx", node.x + 35)
                    .attr("cy", badgeY)
                    .attr("r", 10)
                    .attr("fill", highlightColor)
                    .attr("stroke", "white")
                    .attr("stroke-width", 2)
                    .attr("class", "sample-count-badge");

                g.append("text")
                    .attr("x", node.x + 35)
                    .attr("y", badgeY)
                    .attr("text-anchor", "middle")
                    .attr("dy", "0.35em")
                    .style("font-size", "9px")
                    .style("font-weight", "bold")
                    .style("fill", "white")
                    .text(count)
                    .attr("class", "sample-count-badge");
            }
        });
    }

    function optimizeNodeOrder(nodes, flows, kValues, nodesByK, height) {
        console.log("Applying barycenter method for node ordering...");

        const nodePositions = {};

        // Step 1: Initialize first K level with even spacing
        const firstK = kValues[0];
        const firstKNodes = nodesByK.get(firstK) || [];
        const firstKSpacing = height / Math.max(1, firstKNodes.length + 1);

        firstKNodes.forEach((node, index) => {
            nodePositions[node.id] = (index + 1) * firstKSpacing;
        });

        console.log(`Initialized K=${firstK} with ${firstKNodes.length} nodes`);

        // Step 2: For each subsequent K level, calculate barycenter positions
        for (let kIndex = 1; kIndex < kValues.length; kIndex++) {
            const currentK = kValues[kIndex];
            const prevK = kValues[kIndex - 1];
            const currentKNodes = nodesByK.get(currentK) || [];

            console.log(`Optimizing K=${currentK} (${currentKNodes.length} nodes)`);

            // Calculate barycenter for each node in current K level
            const barycenterData = currentKNodes.map(node => {
                const nodeId = node.id;
                let weightedSum = 0;
                let totalWeight = 0;

                // Find all flows coming TO this node from previous K level
                flows.forEach(flow => {
                    const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                    const targetTopicId = flow.target.replace(/_high$|_medium$/, '');

                    if (targetTopicId === nodeId && flow.sourceK === prevK) {
                        const sourcePosition = nodePositions[sourceTopicId];
                        if (sourcePosition !== undefined) {
                            const weight = flow.sampleCount;
                            weightedSum += sourcePosition * weight;
                            totalWeight += weight;
                        }
                    }
                });

                // Calculate barycenter (weighted average position)
                const barycenter = totalWeight > 0 ? weightedSum / totalWeight : height / 2;

                return {
                    node: node,
                    barycenter: barycenter,
                    totalWeight: totalWeight
                };
            });

            // Sort nodes by barycenter value
            barycenterData.sort((a, b) => a.barycenter - b.barycenter);

            // Assign positions based on sorted order with even spacing
            const kSpacing = height / Math.max(1, currentKNodes.length + 1);
            barycenterData.forEach((data, index) => {
                nodePositions[data.node.id] = (index + 1) * kSpacing;
            });
        }

        console.log("Barycenter optimization complete!");
        return nodePositions;
    }

    function optimizeNodeOrderWithGap(nodes, flows, kValues, nodesByK, height, scaledGap) {
        console.log("Applying gap-aware barycenter method for node ordering...");
        console.log(`Using scaled gap: ${scaledGap.toFixed(1)}px`);

        const nodePositions = {};
        const marginTop = 20; // Top margin

        // Step 1: Initialize first K level with proper gap-aware spacing
        const firstK = kValues[0];
        const firstKNodes = nodesByK.get(firstK) || [];
        
        // Calculate total height needed for first K level
        let totalFirstKHeight = 0;
        firstKNodes.forEach(node => {
            totalFirstKHeight += node.height;
        });
        totalFirstKHeight += (firstKNodes.length - 1) * scaledGap;
        
        // Position first K level nodes with proper gaps
        let currentY = marginTop;
        firstKNodes.forEach((node, index) => {
            nodePositions[node.id] = currentY + node.height / 2;
            currentY += node.height + scaledGap;
        });

        console.log(`Initialized K=${firstK} with ${firstKNodes.length} nodes using gap-aware spacing`);

        // Step 2: For each subsequent K level, calculate barycenter positions with gap awareness
        for (let kIndex = 1; kIndex < kValues.length; kIndex++) {
            const currentK = kValues[kIndex];
            const prevK = kValues[kIndex - 1];
            const currentKNodes = nodesByK.get(currentK) || [];

            console.log(`Optimizing K=${currentK} (${currentKNodes.length} nodes)`);

            // Calculate barycenter for each node in current K level
            const barycenterData = currentKNodes.map(node => {
                const nodeId = node.id;
                let weightedSum = 0;
                let totalWeight = 0;

                // Find all flows coming TO this node from previous K level
                flows.forEach(flow => {
                    const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                    const targetTopicId = flow.target.replace(/_high$|_medium$/, '');

                    if (targetTopicId === nodeId && flow.sourceK === prevK) {
                        const sourcePosition = nodePositions[sourceTopicId];
                        if (sourcePosition !== undefined) {
                            const weight = flow.sampleCount;
                            weightedSum += sourcePosition * weight;
                            totalWeight += weight;
                        }
                    }
                });

                // Calculate barycenter (weighted average position)
                const barycenter = totalWeight > 0 ? weightedSum / totalWeight : height / 2;

                return {
                    node: node,
                    barycenter: barycenter,
                    totalWeight: totalWeight
                };
            });

            // Sort nodes by barycenter value
            barycenterData.sort((a, b) => a.barycenter - b.barycenter);

            // Position nodes with proper gap-aware spacing
            let currentY = marginTop;
            barycenterData.forEach((data, index) => {
                nodePositions[data.node.id] = currentY + data.node.height / 2;
                currentY += data.node.height + scaledGap;
            });
        }

        console.log("Gap-aware barycenter optimization complete!");
        return nodePositions;
    }

    function calculateSegmentY(node, level) {
        const totalCount = node.highCount + node.mediumCount;
        if (totalCount === 0) return node.y;

        const highHeight = (node.highCount / totalCount) * node.height;

        if (level === 'high') {
            return node.y - node.height/2 + highHeight/2;
        } else {
            return node.y - node.height/2 + highHeight + (node.height - highHeight)/2;
        }
    }

    function createCurvePath(x1, y1, x2, y2) {
        const midX = (x1 + x2) / 2;
        return `M ${x1} ${y1} C ${midX} ${y1} ${midX} ${y2} ${x2} ${y2}`;
    }

    function showTooltip(g, event, flow) {
        const tooltip = g.append("g").attr("class", "tooltip");

        const tooltipText = `${flow.sampleCount} samples\\n${flow.source} → ${flow.target}`;
        const lines = tooltipText.split('\\n');

        const tooltipWidth = 160;
        const tooltipHeight = 35;

        // Get the chart dimensions to ensure tooltip stays within bounds
        const chartWidth = g.node().getBBox().width || 1000;

        // Calculate tooltip position with bounds checking - show below by default
        let tooltipX = event.layerX || 0;
        let tooltipY = (event.layerY || 0) + 20; // Show below cursor by default

        // Adjust X position if tooltip would go off the right edge
        if (tooltipX + tooltipWidth > chartWidth) {
            tooltipX = chartWidth - tooltipWidth - 10;
        }

        // Get chart bounds to check bottom edge
        const chartBounds = g.node().getBBox();
        const chartHeight = chartBounds.height || 600;
        
        // Adjust Y position if tooltip would go off the bottom edge
        if (tooltipY + tooltipHeight > chartHeight) {
            tooltipY = (event.layerY || 0) - tooltipHeight - 10; // Show above cursor if no room below
        }

        const rect = tooltip.append("rect")
            .attr("x", tooltipX)
            .attr("y", tooltipY)
            .attr("width", tooltipWidth)
            .attr("height", tooltipHeight)
            .attr("fill", "white")
            .attr("stroke", "black")
            .attr("rx", 3)
            .attr("opacity", 0.9);

        lines.forEach((line, i) => {
            tooltip.append("text")
                .attr("x", tooltipX + 5)
                .attr("y", tooltipY + 15 + i * 12)
                .style("font-size", "10px")
                .style("fill", "black")
                .text(line);
        });
    }

    function showSampleInfo(g, selectedFlow, sampleCount) {
        // Position the info panel above the legend with a small gap
        const chartBounds = g.node().getBBox();
        const panelHeight = 60;
        
        // Calculate position based on legend position
        // Legends are positioned at different heights based on color mode
        const colorLegend = g.select(".color-legend");
        let legendY = chartBounds.height - 120; // Default legend position
        
        if (!colorLegend.empty()) {
            // Get the actual legend position from its transform
            const legendTransform = colorLegend.attr("transform");
            const matches = legendTransform.match(/translate\((\d+),\s*(\d+)\)/);
            if (matches) {
                legendY = parseInt(matches[2]);
            }
        }
        
        // Position panel below legend with 20px gap
        // Add space for legend content - estimate legend height based on color mode
        let legendHeight = 40; // Default legend height
        if (!colorLegend.empty()) {
            // For different legend types, estimate the height
            if (g.select(".perplexity-legend-metrics").empty() === false) {
                legendHeight = 120; // metrics mode has two legends stacked
            } else {
                legendHeight = 60; // single legend height
            }
        }
        const panelY = legendY + legendHeight -10;
        
        const infoPanel = g.append("g").attr("class", "sample-info-panel");

        // Background panel positioned at bottom-left
        infoPanel.append("rect")
            .attr("x", 10)
            .attr("y", panelY)
            .attr("width", 200)
            .attr("height", panelHeight)
            .attr("fill", "white")
            .attr("stroke", "#ff6b35")
            .attr("stroke-width", 2)
            .attr("rx", 5)
            .attr("opacity", 0.95);

        // Title
        infoPanel.append("text")
            .attr("x", 20)
            .attr("y", panelY + 20)
            .style("font-size", "12px")
            .style("font-weight", "bold")
            .style("fill", "#ff6b35")
            .text(`Selected: ${sampleCount} Samples`);

        // Flow info
        infoPanel.append("text")
            .attr("x", 20)
            .attr("y", panelY + 35)
            .style("font-size", "10px")
            .style("fill", "#333")
            .text(`${selectedFlow.source} → ${selectedFlow.target}`);

        // Instructions
        infoPanel.append("text")
            .attr("x", 20)
            .attr("y", panelY + 48)
            .style("font-size", "9px")
            .style("fill", "#666")
            .text("Click flow again or background to clear");
    }

    function showSegmentTooltip(g, event, node, level, count, rawData, metricMode, model) {
        const tooltip = g.append("g").attr("class", "tooltip");

        // Get configurable thresholds from the model
        const thresholds = model.get("probability_thresholds") || { high_threshold: 0.67, medium_threshold: 0.33 };
        const highThreshold = thresholds.high_threshold;
        const mediumThreshold = thresholds.medium_threshold;
        
        const levelText = level === 'high' ? 
            `High (≥${highThreshold})` : 
            `Medium (${mediumThreshold}-${highThreshold.toFixed(2)})`;
        let tooltipLines = [`${node.id}`, levelText, `${count} samples`];

        // Add metric information if in metric mode
        if (metricMode && rawData && rawData.nodes[node.id]) {
            const nodeData = rawData.nodes[node.id];

            if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                tooltipLines.push(`Perplexity: ${nodeData.model_metrics.perplexity.toFixed(3)}`);
            }

            if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
                tooltipLines.push(`Coherence: ${nodeData.mallet_diagnostics.coherence.toFixed(3)}`);
            }
        }

        const tooltipHeight = tooltipLines.length * 12 + 10;
        const tooltipWidth = Math.max(140, Math.max(...tooltipLines.map(line => line.length * 6 + 10)));

        // Get the chart dimensions to ensure tooltip stays within bounds
        const chartWidth = g.node().getBBox().width || 1000;

        // Calculate tooltip position relative to the node's actual position
        // Use node position instead of event coordinates for more accurate positioning
        let tooltipX = node.x + 25; // Position to the right of the node
        let tooltipY = node.y + 10; // Slightly below node center

        // Adjust X position if tooltip would go off the right edge
        if (tooltipX + tooltipWidth > chartWidth) {
            tooltipX = chartWidth - tooltipWidth - 10;
        }

        // Get chart bounds to check bottom edge
        const chartBounds = g.node().getBBox();
        const chartHeight = chartBounds.height || 600;
        
        // Adjust Y position if tooltip would go off the bottom edge
        if (tooltipY + tooltipHeight > chartHeight) {
            tooltipY = (event.layerY || 0) - tooltipHeight - 10; // Show above cursor if no room below
        }

        const rect = tooltip.append("rect")
            .attr("x", tooltipX)
            .attr("y", tooltipY)
            .attr("width", tooltipWidth)
            .attr("height", tooltipHeight)
            .attr("fill", "white")
            .attr("stroke", "black")
            .attr("rx", 3)
            .attr("opacity", 0.9);

        tooltipLines.forEach((line, i) => {
            tooltip.append("text")
                .attr("x", tooltipX + 5)
                .attr("y", tooltipY + 15 + i * 12)
                .style("font-size", "10px")
                .style("fill", "black")
                .text(line);
        });
    }

    export default { render };
    """

    _css = """
    .widget-container {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    }

    .sample-tracing {
        pointer-events: none;
    }

    .sample-info-panel {
        pointer-events: none;
    }

    .metric-legend {
        pointer-events: none;
    }
    """

    # Widget traits
    sankey_data = traitlets.Dict(default_value={}).tag(sync=True)
    width = traitlets.Int(default_value=1200).tag(sync=True)
    height = traitlets.Int(default_value=800).tag(sync=True)

    # Add trait for tracking selected flow
    selected_flow = traitlets.Dict(default_value={}).tag(sync=True)

    # Add traits for metric mode
    metric_mode = traitlets.Bool(default_value=False).tag(sync=True)
    color_mode = traitlets.Unicode(default_value="default").tag(sync=True)  # "default", "metric", "perplexity", "coherence", "metrics", "cluster_prox", "meta_sankey"
    metric_config = traitlets.Dict(default_value={
        'red_weight': 0.8,    # Weight for perplexity (red component)
        'blue_weight': 0.8,   # Weight for coherence (blue component)
        'min_saturation': 0.3  # Minimum color saturation to keep colors visible
    }).tag(sync=True)
    
    # Add traits for probability thresholds
    probability_thresholds = traitlets.Dict(default_value={
        'high_threshold': 0.67,   # Threshold for high representation (≥ this value)
        'medium_threshold': 0.33  # Threshold for medium representation (≥ this value)
    }).tag(sync=True)
    
    # Add trait for minimum flow threshold
    min_flow_samples = traitlets.Int(default_value=10).tag(sync=True)  # Minimum samples required to show a flow

    # Which K columns to show (gapped / non-contiguous allowed); empty = all K in the data
    k_list = traitlets.List(default_value=[]).tag(sync=True)

    # --- cluster_prox appearance -------------------------------------------
    # gradient: "" (default) = the OKLCH hue-lineage strategy. Any CSS colour
    # ("black", "#2166ac") switches the cluster colours to a single-hue
    # light->dark ramp over the same dendrogram leaf order, so the figure
    # survives greyscale printing. node_width: LC node width in px; 0 = auto
    # from the column step. Both are ignored by the other renderers.
    gradient = traitlets.Unicode(default_value="").tag(sync=True)
    node_width = traitlets.Int(default_value=0).tag(sync=True)
    # How hard the layout searches for a stack order with fewer ribbon
    # crossings (see __orderColumns). 0 = the plain forward barycentre pass,
    # 1.0 = the default (tens of ms, and the run-axis figures come out with no
    # crossings at all), 10-20 = for a figure being exported once, where a
    # second of search buys another 30-50% on the hardest K sweeps. The search
    # only ever accepts a strict improvement, so raising this can never make a
    # figure worse -- and the answer does not depend on machine speed.
    layout_effort = traitlets.Float(default_value=1.0).tag(sync=True)
    # How the single-hue ramp spaces the clusters. 0.0 = faithful (darkness is
    # exactly proportional to cumulative dendrogram distance, so near-identical
    # clusters get near-identical tints); 1.0 = pure rank (even steps along the
    # leaf order, maximally separable but distance is no longer readable).
    gradient_spread = traitlets.Float(default_value=0.0).tag(sync=True)
    # Pale end of that ramp as a CIE L* value (0 = black, 100 = white), clamped
    # to 40-97. 82 (~#c9c9c9) keeps the lightest cluster clearly separated from
    # the #fafafa panel background and from the white noise band; raise it for a
    # softer figure, lower it (e.g. 70) when many clusters need pulling apart.
    gradient_light = traitlets.Float(default_value=82.0).tag(sync=True)

    # Optional override of __clusterLineage's own OKLCH colours, {cluster_id:
    # css_colour}. Empty (default) = unchanged behaviour, the ad-hoc cosine
    # dendrogram below picks every colour itself. Only clusters present as
    # keys are overridden (Object.assign onto LIN.color) -- anything absent
    # falls back to the computed hue, so a partial map is safe. This is how a
    # caller keeps the ribbon colours in agreement with a colour computed
    # elsewhere from the SAME chance-corrected Q (see
    # `lda4microbiome.mr_consensus.lineage_palette`), instead of this widget's
    # own cosine-distance one, without touching `__clusterLineage` itself --
    # layout/geometry (leaf order, family, barycentre rank) still comes from
    # it unchanged; only the paint lookup is redirected.
    cluster_colors = traitlets.Dict(default_value={}).tag(sync=True)

    # Optional replacement for the bottom-band "consensus clusters" legend
    # (title + `__clusterLineage`'s own cosine-distance dendrogram + chips):
    # the SAME layout dict `lda4microbiome.cluster_dendrogram.dendrogram_layout`
    # produces -- {"n", "leaves":[{"pos","id","x","y","size","color","label"}],
    # "links":[{"x1","y1","x2","y2"}], "root_y"} -- built from
    # `mr_consensus.coarse_linkage`, i.e. the SAME chance-corrected Q as
    # `cluster_colors`, not a third distance. Empty (default) = unchanged
    # behaviour, the bottom band stays as it is. Non-empty moves the legend to
    # a LEFT column instead (leaves stacked top-to-bottom, height growing
    # right-to-left so 0 sits against the diagram it labels, each leaf a
    # circle at its own first-merge height rather than a shared baseline —
    # see `cluster_dendrogram.py`'s module docstring for why) and removes the
    # bottom one, since the two would otherwise show two different trees for
    # the same clusters. Colour still comes from `lineageColor`/`cluster_colors`
    # at draw time, not from this dict's own `color` field, so the legend and
    # the ribbons can never show two different colours for one cluster.
    cluster_legend = traitlets.Dict(default_value={}).tag(sync=True)

    # Optional replacement for the "K = <n>" column headings, as
    # {column index (str): label}. Every renderer indexes its columns by an
    # integer that is normally K; this keeps that integer as a plain column
    # INDEX and prints something else over it, which is what makes a non-K
    # x-axis possible without a second copy of the layout code -- see
    # `lda4microbiome.modes`, whose columns are replicate RUNS at one fixed K,
    # headed "k7r2 * M0". Empty (default) = headings stay "K = <n>"; an index
    # with no entry keeps the default, so a partial map is safe.
    # Top-to-bottom order the cluster bands are stacked in, as a list of cluster
    # ids. Empty (default) = the order the renderer derives itself from the data.
    # Set it when the colours come from outside the diagram and carry an order of
    # their own -- a metadata field whose categories the legend lists in a fixed
    # sequence -- so a band and its legend entry are in the same place in both.
    cluster_order = traitlets.List(default_value=[]).tag(sync=True)

    column_labels = traitlets.Dict(default_value={}).tag(sync=True)

    # Optional SECOND heading line, as {column index (str): text}, drawn small and
    # grey under `column_labels`. It qualifies a column instead of naming it, so
    # tooltips and focus banners keep showing the main label alone. The mode axis
    # of `lda4microbiome.modes` is what this is for: with one column per MODE the
    # name on top is "K = 6 · M1" and the line under it says which of pong's modes
    # that is and on what evidence -- "minor mode · rep. k6r1 · 2 of 8 runs".
    # Empty (default) = one-line headings and the original top margin.
    column_sublabels = traitlets.Dict(default_value={}).tag(sync=True)

    # Optional metadata overlay for cluster_prox hover composition.
    # metadata = {sample_id: {field: value}}; hover_field = the column(s) to break
    # down on hover -- a single name (str) or up to 3 names (list). In cluster_prox
    # focus mode (click a K label) the FIRST field drives the node restack.
    metadata = traitlets.Dict(default_value={}).tag(sync=True)
    hover_field = traitlets.Union([traitlets.List(), traitlets.Unicode()],
                                  default_value="").tag(sync=True)

    # Per-component annotations, supplied by the caller (cluster_prox and
    # meta_sankey): {"<k>": {"<lc>": [[label, weight], ...]}}, best first. The
    # widget shows exactly these rows and never reads a feature table -- what
    # they are and which ones are left out is the caller's decision. A component
    # with rows gets a two-part caption "LC3 · Prevotella" (the top row's name):
    # clicking the component part selects the whole node (as without
    # annotations), clicking the annotation part opens a popup listing the rows
    # and selects nothing. Empty (default) = captions exactly as before.
    lc_annotations = traitlets.Dict(default_value={}).tag(sync=True)
    # What the annotations are ("Genus", "gene", ...): named in the annotation
    # part's tooltip and the popup heading ("top 5 Genus"), not in the caption.
    annotation_label = traitlets.Unicode(default_value="").tag(sync=True)
    # What a component is called in captions and tooltips. "LC" (latent
    # component) by default; a domain package can say e.g. "MC".
    component_label = traitlets.Unicode(default_value="LC").tag(sync=True)

    # Which panels a color_mode='small_multiples' figure draws, left to right:
    # 'cluster' (consensus cluster, the stripesankey's OKLCH lineage) and/or
    # metadata column names. Every panel shares ONE node layout -- same samples,
    # same K, same scale, same node y-position and order -- so only the colouring
    # differs and the panels are directly comparable. Ignored by every other
    # renderer.
    panels = traitlets.List(default_value=[]).tag(sync=True)
    # How many small-multiple panels per row. 0 (default) = choose automatically:
    # every feasible column count is scored on how close it puts each panel to the
    # aspect ratio a Sankey of this many K columns wants, and the closest wins.
    panel_cols = traitlets.Int(default_value=0).tag(sync=True)

    # No `mc_features` / `feature_level`: the per-LC top-taxa panel they fed is
    # gone, because it needs a feature x annotation table and this package never
    # sees features. See API_stripesankey.md, "Still open".

    # --- selection written BACK to Python (meta_sankey) ---------------------
    # Click a flow or a node segment and these update in the live kernel:
    #   selected_samples -> ['S001', 'S042', ...] (sorted sample ids)
    #   selection_info   -> {source:'flow'|'node', k/.., mc/.., field, category, n}
    # Both reset to empty when the selection is cleared. In a static HTML export
    # they stay empty (model.set is a no-op there).
    selected_samples = traitlets.List(default_value=[]).tag(sync=True)
    selection_info = traitlets.Dict(default_value={}).tag(sync=True)

    # Two SNAPSHOTS of the selection, taken with the in-diagram "Freeze" buttons:
    # {'A': [sample_id, ...], 'B': [...]}. Unlike selected_samples these do NOT
    # change when you click elsewhere -- that is the whole point, it is what lets
    # a notebook hold two groups still and compare them. Live kernel only.
    frozen_groups = traitlets.Dict(default_value={}).tag(sync=True)

    # Payload for the standalone hard-clustering renderer (color_mode='hard_sankey').
    # {levels:[...], labels:{level:{sid:labelStr}}, color:{sid:valStr},
    #  meta:{sid:{field:valStr}}, hover_fields:[...], colorby_name:str}
    hard_data = traitlets.Dict(default_value={}).tag(sync=True)


    color_schemes = traitlets.Dict(default_value={
        2: "#1f77b4", 3: "#ff7f0e", 4: "#2ca02c", 5: "#d62728", 6: "#9467bd",
        7: "#8c564b", 8: "#e377c2", 9: "#7f7f7f", 10: "#bcbd22"
    }).tag(sync=True)

    def __init__(self, sankey_data=None, mode="default", high_threshold=None, medium_threshold=None, min_flow_samples=None, k_list=None, metadata=None, hover_field=None, hard_data=None, panels=None, panel_cols=None, column_labels=None, column_sublabels=None, cluster_order=None, **kwargs):
        super().__init__(**kwargs)
        if sankey_data:
            self.sankey_data = sankey_data
        # Payload for the standalone hard-clustering renderer (mode='hard_sankey')
        if hard_data is not None:
            self.hard_data = hard_data
        # Set metric_mode based on the mode parameter
        self.metric_mode = (mode in ["metric", "perplexity", "coherence", "metrics"])
        # Store the specific mode type ("cluster_prox" uses its own renderer)
        self.color_mode = mode
        # Which K columns to show (gapped / non-contiguous allowed)
        if k_list is not None:
            self.k_list = list(k_list)
        # Which panels a small_multiples figure draws (row-major) and how many
        # go on a row (0 = auto)
        if panels is not None:
            self.panels = [str(x) for x in panels]
        if panel_cols is not None:
            self.panel_cols = int(panel_cols)
        # Non-K column headings, {column index: label} -- see the trait
        if column_labels is not None:
            self.column_labels = {str(c): str(v) for c, v in column_labels.items()}
        # Band stacking order -- see the trait
        if cluster_order is not None:
            self.cluster_order = [int(c) for c in cluster_order]
        # Second heading line per column -- see the trait
        if column_sublabels is not None:
            self.column_sublabels = {str(c): str(v) for c, v in column_sublabels.items()}
        # Optional metadata overlay for cluster_prox hover composition
        if metadata is not None:
            self.metadata = metadata
        if hover_field is not None:
            # accept a single column name or up to 3 (max enforced with a warning)
            if isinstance(hover_field, (list, tuple)):
                fields = list(hover_field)
                if len(fields) > 3:
                    print(f"⚠️ hover_field: only the first 3 of {len(fields)} fields "
                          f"are shown; dropping {fields[3:]}.")
                    fields = fields[:3]
                self.hover_field = fields
            else:
                self.hover_field = hover_field
        
        # Set custom thresholds if provided
        if high_threshold is not None or medium_threshold is not None:
            thresholds = self.probability_thresholds.copy()
            if high_threshold is not None:
                thresholds['high_threshold'] = high_threshold
            if medium_threshold is not None:
                thresholds['medium_threshold'] = medium_threshold
            self.probability_thresholds = thresholds
        
        # Set custom minimum flow samples threshold if provided
        if min_flow_samples is not None:
            self.min_flow_samples = min_flow_samples

    def set_mode(self, mode):
        """Set visualization mode: 'default', 'metric', 'perplexity', 'coherence', or 'metrics'"""
        self.metric_mode = (mode in ["metric", "perplexity", "coherence", "metrics"])
        self.color_mode = mode
        return self  # Return self for chaining

    def update_metric_config(self, red_weight=None, blue_weight=None, min_saturation=None):
        """Update metric mode configuration"""
        config = self.metric_config.copy()
        if red_weight is not None:
            config['red_weight'] = red_weight
        if blue_weight is not None:
            config['blue_weight'] = blue_weight
        if min_saturation is not None:
            config['min_saturation'] = min_saturation
        self.metric_config = config
        return self  # Return self for chaining
    
    def update_probability_thresholds(self, high_threshold=None, medium_threshold=None):
        """Update probability thresholds for high and medium representation levels"""
        thresholds = self.probability_thresholds.copy()
        if high_threshold is not None:
            thresholds['high_threshold'] = high_threshold
        if medium_threshold is not None:
            thresholds['medium_threshold'] = medium_threshold
        self.probability_thresholds = thresholds
        return self  # Return self for chaining

    def selected(self, df=None):
        """The samples currently selected in the widget (meta_sankey).

        Click a ribbon or a node segment in the diagram, then call this from a
        later cell. With no argument it returns the sample ids; pass a
        sample-indexed DataFrame (e.g. your metadata) to get those rows back.

        In a *marimo* notebook the widget must be wrapped for the value to reach
        Python: ``w = mo.ui.anywidget(k_evaluation(..., plot='meta_sankey'))``,
        then read ``w.value['selected_samples']`` (or ``w.widget.selected()``).
        In Jupyter the widget object itself works, and
        ``w.observe(cb, names='selected_samples')`` gives you a callback.
        """
        ids = list(self.selected_samples)
        if df is None:
            return ids
        idx = df.index.map(str)
        return df[idx.isin(set(ids))]


def save_widget_html(widget, path):
    """Save an anywidget (D3) instance as a self-contained, interactive HTML file.

    Interactive plots can't be rasterised headlessly, so this writes a standalone
    ``.html`` that inlines the widget's ESM + its synced trait values and renders
    it exactly as in the notebook (d3 is still fetched from its CDN at open time).
    Open it in a browser to view / screenshot / print-to-PDF for publication.
    """
    import json
    import os

    # instance access -> the actual ESM/CSS strings (class access returns traits)
    esm = str(widget._esm)
    css = str(getattr(widget, "_css", "") or "")
    # every trait tagged sync=True is what the ESM reads via model.get(...)
    traits = {name: getattr(widget, name)
              for name, tr in widget.traits().items()
              if tr.metadata.get("sync") and not name.startswith("_")}

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    html = (
        '<!doctype html>\n<html><head><meta charset="utf-8">\n'
        '<style>html,body{margin:0;padding:0}\n' + css + '</style></head>\n'
        '<body><div id="w"></div>\n'
        '<script type="module">\n'
        'const MODEL_DATA = ' + json.dumps(traits, default=str) + ';\n'
        # static export: model.get returns the saved values; on/set are no-ops
        'const model = { get:(k)=>MODEL_DATA[k], set:()=>{}, save_changes:()=>{},'
        ' on:()=>{}, off:()=>{} };\n'
        'const esmCode = ' + json.dumps(esm) + ';\n'
        'const _url = URL.createObjectURL(new Blob([esmCode], {type:"text/javascript"}));\n'
        'const _mod = await import(_url);\n'
        'await _mod.default.render({ model, el: document.getElementById("w") });\n'
        '</script></body></html>\n'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Interactive HTML saved: {path}")
    return path


def hardstripe(clustering_labels, colorby=None, metadata_df=None,
               hover_field=None, column_order=None, min_flow_samples=5,
               save_path=None, width=1200, height=800, min_samples=5,
               n_clusters=None, consensus_method="pcc", verbose=True):
    """One-step interactive StripeSankey for HARD clustering labels.

    Computes (when needed) and plots in a single call, returning the widget.
    Nodes are clusters within each level (column); flows are samples moving
    between consecutive levels; node height == the sum of its flow widths
    exactly. Colour encodes ``colorby`` -- a metadata field, or the global
    consensus cluster (which is computed here from the label ensemble).

    This is standalone from training (like :func:`a_heatmap`): the input is a
    plain DataFrame of hard labels, not a model output folder.

    Parameters
    ----------
    consensus_method : {"pcc", "coassociation"}
        Backend for ``colorby="consensus"``. ``"pcc"`` (default) fits
        probabilistic consensus clustering, which reads the co-association
        matrix as counts of Bernoulli events and picks its own cluster count;
        ``"coassociation"`` is the older PLSCAN / average-linkage route, and is
        the only one that can label a sample as noise. Ignored for any other
        ``colorby``. See :func:`~stripesankey.consensus_hard_labels`.
    clustering_labels : DataFrame
        index = sample id, columns = ordered levels (e.g. k-means at k=2,3,4).
        Values are hard labels; NaN -> "NA", -1 -> "noise" (each its own node).
        Column order is the left-to-right level order, unless ``column_order``
        overrides it.
    colorby : str, optional
        ``None`` -> single-colour ribbons (a plain flow diagram). A metadata
        column name -> colour by that field (needs ``metadata_df``). The literal
        string ``'consensus'`` -> colour by the global consensus cluster, which
        is computed here via co-association clustering of the label ensemble
        (PLSCAN when available, scipy average-linkage otherwise).
    metadata_df : DataFrame, optional
        Sample-indexed metadata (index aligned to ``clustering_labels``). Needed
        when ``colorby`` is a metadata field and/or ``hover_field`` is given.
    hover_field : str or list of str, optional
        Up to 3 metadata columns whose composition is shown in the hover
        tooltip. When ``colorby='consensus'`` the consensus cluster is added as
        the first hover field automatically.
    column_order : list, optional
        Which ``clustering_labels`` columns to draw, left to right. ``None``
        (default) keeps the DataFrame's own column order. Entries may name a
        **subset** -- unlisted columns are dropped -- so this doubles as a
        column filter, e.g. ``column_order=['k2', 'k5', 'k8']`` on a k2..k10
        frame. Names are matched exactly first, then by ``str()``, so
        ``['4', '2']`` resolves against integer columns ``[2, 3, 4]``. At least
        2 columns must survive. When ``colorby='consensus'`` the consensus is
        computed over the columns kept here, so it matches the ribbons drawn.
    min_flow_samples : int
        Ribbons carrying fewer than this many samples are hidden (declutter).
    save_path : str, optional
        If given, also save a self-contained interactive ``.html`` there.
    width, height : int
        Widget pixel size.
    min_samples : int
        Consensus clustering ``min_samples`` (only used for ``colorby='consensus'``).
    n_clusters : int, optional
        Consensus scipy-fallback only -- force this many clusters.
    verbose : bool
        Print consensus-clustering progress.

    Returns
    -------
    StripeSankeyInline
        The interactive widget (display it in a notebook cell).
    """
    import pandas as pd
    from .clustering import normalize_hard_labels, consensus_hard_labels

    norm = normalize_hard_labels(clustering_labels)      # str index + values

    # ---- level order (and optional subset) ---------------------------------
    if column_order is not None:
        if isinstance(column_order, str) or not isinstance(column_order, (list, tuple)):
            raise TypeError(
                f"column_order must be a list of column names, got "
                f"{type(column_order).__name__}."
            )
        by_str = {str(c): c for c in norm.columns}       # for int columns etc.
        picked = []
        for want in column_order:
            if want in norm.columns:
                col = want
            elif str(want) in by_str:
                col = by_str[str(want)]
            else:
                raise KeyError(
                    f"column_order entry {want!r} is not a column of "
                    f"clustering_labels (available: {list(norm.columns)})."
                )
            if col in picked:
                raise ValueError(f"column_order lists {want!r} more than once.")
            picked.append(col)
        if len(picked) < 2:
            raise ValueError(
                f"column_order kept {len(picked)} column(s); the Sankey needs at "
                f"least 2 ordered levels to draw flows between."
            )
        norm = norm[picked]

    levels = [str(lvl) for lvl in norm.columns]
    labels = {str(lvl): {sid: norm.at[sid, lvl] for sid in norm.index}
              for lvl in norm.columns}

    # metadata (str index) for colouring / hover
    md = None
    if metadata_df is not None:
        md = metadata_df.copy()
        md.index = md.index.map(str)

    # ---- colour per sample -------------------------------------------------
    color, colorby_name = {}, ""
    if colorby is None:
        pass  # single-colour flow diagram
    elif colorby == "consensus":
        # over `norm`, not the raw input, so a column_order subset colours by
        # the consensus of the levels actually drawn
        cons = consensus_hard_labels(norm, method=consensus_method,
                                     min_samples=min_samples,
                                     n_clusters=n_clusters, verbose=verbose)
        color = {str(sid): ("noise" if int(c) == -1 else f"C{int(c)}")
                 for sid, c in cons.items()}
        colorby_name = "consensus"
    else:
        if md is None or colorby not in md.columns:
            raise KeyError(
                f"colorby={colorby!r} needs a metadata_df column with that name "
                f"(available: {list(md.columns) if md is not None else None}); "
                f"or pass colorby='consensus'."
            )
        color = {sid: ("NA" if pd.isna(md.at[sid, colorby]) else str(md.at[sid, colorby]))
                 for sid in norm.index if sid in md.index}
        colorby_name = str(colorby)

    # ---- hover fields (up to 3; consensus first when colouring by it) -------
    hf = [] if hover_field is None else ([hover_field] if isinstance(hover_field, str) else list(hover_field))
    if md is not None:
        missing = [f for f in hf if f not in md.columns]
        if missing:
            print(f"⚠️ hover_field: {missing} not in metadata_df; skipping.")
    hover_fields = []
    if colorby == "consensus":
        hover_fields.append("consensus")
    for f in hf:
        if md is not None and f in md.columns and f not in hover_fields:
            hover_fields.append(f)
    hover_fields = hover_fields[:3]

    meta = {}
    for sid in norm.index:
        d = {}
        for f in hover_fields:
            if f == "consensus":
                d["consensus"] = color.get(sid, "NA")
            elif md is not None and f in md.columns and sid in md.index:
                v = md.at[sid, f]
                d[f] = "NA" if pd.isna(v) else str(v)
        meta[sid] = d

    hard_data = {
        "levels": levels,
        "labels": labels,
        "color": color,
        "meta": meta,
        "hover_fields": hover_fields,
        "colorby_name": colorby_name,
    }
    widget = StripeSankeyInline(
        mode="hard_sankey", hard_data=hard_data,
        min_flow_samples=min_flow_samples, width=width, height=height,
    )
    if save_path:
        save_widget_html(widget, save_path)
    return widget
