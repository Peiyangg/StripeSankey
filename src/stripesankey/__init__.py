"""
StripeSankey -- the volume-accurate k-sweep figure, and the consensus behind it.

The unit of input is one sweep of soft assignments: ``W_by_k``, a dict
``{k: DataFrame(sample x LC)}``. ``W`` is the sample-side matrix of
``X ~ W . H``, as the paper and sklearn both name it; this package never sees
``H``, because it never sees features.

Two views, one layout::

    stripesankey   each census column coloured by consensus cluster
    metasankey     the same columns cut by a metadata field instead

"Same layout" is literal: both go through one census/cut/ribbon path, so a bar
at a given height in one render is the same bar in the other.

Nothing here reads a results folder -- callers pass objects. ``lda4microbiome``
owns the cache-folder translation.
"""

__version__ = "1.0.0.dev0"

# --- the pipeline: prepare -> sweep -> read it back -> draw ---------------
from .prep import validate_tables, prepare, load_manifest, load_features
from .fit import sweep, verify_pass_loop
from .cache import (load_W, load_H, load_run_info, load_consensus,
                    load_topic_diff, convergence_report, unsettled_k)
from .plots import sweep_figure, load_sweep_figure_inputs

from .api import stripesankey, metasankey, build_sankey_data, cluster_lineage
from .stripesankey import StripeSankeyInline, hardstripe, save_widget_html
from .affinity_heatmap import affinity_heatmap
from .cluster_dendrogram import ClusterDendrogram, dendrogram_layout
from .clustering import consensus_clusters, consensus_hard_labels
from .mr_consensus import (
    consensus_affinity,
    cluster_from_affinity,
    coarse_affinity,
    coarse_linkage,
    coarse_sizes,
    lineage_palette,
    coherent_cluster_palette,
)
# Replicate-run analysis: run-to-run similarity, mode detection, the run-axis
# figure. Not reached by the k-sweep, which fits one model per k -- see
# API_stripesankey.md, "What moves in".
from .modes import (
    mode_analysis,
    modestripe,
    run_similarity,
    detect_modes,
    widest_gap,
    consensus_from_runs,
    load_pong_filemap,
    ModeAnalysis,
)
from .clumppling import clumppling_modes

__all__ = [
    # the pipeline
    "prepare",
    "validate_tables",
    "sweep",
    "verify_pass_loop",
    "load_W",
    "load_H",
    "load_run_info",
    "load_consensus",
    "load_topic_diff",
    "load_manifest",
    "load_features",
    "convergence_report",
    "unsettled_k",
    "sweep_figure",
    "load_sweep_figure_inputs",
    # the figures
    "stripesankey",
    "metasankey",
    "build_sankey_data",
    "StripeSankeyInline",
    "hardstripe",
    "save_widget_html",
    "affinity_heatmap",
    "ClusterDendrogram",
    "dendrogram_layout",
    "consensus_clusters",
    "consensus_hard_labels",
    "consensus_affinity",
    "cluster_from_affinity",
    "coarse_affinity",
    "coarse_linkage",
    "coarse_sizes",
    "lineage_palette",
    "coherent_cluster_palette",
    "mode_analysis",
    "modestripe",
    "run_similarity",
    "detect_modes",
    "widest_gap",
    "consensus_from_runs",
    "load_pong_filemap",
    "ModeAnalysis",
    "clumppling_modes",
]
