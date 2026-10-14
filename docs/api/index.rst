StripeSankey API Guide
======================

.. currentmodule:: stripesankey

Everything is imported from the top-level package:

.. code-block:: python

   import stripesankey as ss

Most work needs only the first three sections: fit a sweep, read it back, and
draw it. The rest is for building figures from your own pieces.


Fitting a sweep
---------------

.. autosummary::

   prepare
   validate_tables
   sweep

.. autofunction:: prepare
.. autofunction:: validate_tables
.. autofunction:: sweep


Reading a sweep back
--------------------

.. autosummary::

   load_W
   load_H
   load_consensus
   load_run_info
   load_manifest
   load_features
   convergence_report
   unsettled_k
   load_topic_diff

.. autofunction:: load_W
.. autofunction:: load_H
.. autofunction:: load_consensus
.. autofunction:: load_run_info
.. autofunction:: load_manifest
.. autofunction:: load_features
.. autofunction:: convergence_report
.. autofunction:: unsettled_k
.. autofunction:: load_topic_diff


Figures
-------

.. autosummary::

   stripesankey
   metasankey
   affinity_heatmap
   hardstripe
   save_widget_html
   StripeSankeyInline

.. autofunction:: stripesankey
.. autofunction:: metasankey
.. autofunction:: affinity_heatmap
.. autofunction:: hardstripe
.. autofunction:: save_widget_html

.. autoclass:: StripeSankeyInline
   :members: selected

   The widget every figure function returns. Display it in a notebook cell.
   After a click in the figure, ``selected_samples`` holds the selected sample
   ids.


The consensus
-------------

How the consensus clusters, their colours and the legend tree are computed.
:func:`sweep` and the figure functions call these for you.

.. autosummary::

   consensus_affinity
   cluster_from_affinity
   consensus_hard_labels
   coherent_cluster_palette
   lineage_palette
   coarse_affinity
   coarse_linkage
   coarse_sizes
   cluster_lineage
   build_sankey_data
   dendrogram_layout

.. autofunction:: consensus_affinity
.. autofunction:: cluster_from_affinity
.. autofunction:: consensus_hard_labels
.. autofunction:: coherent_cluster_palette
.. autofunction:: lineage_palette
.. autofunction:: coarse_affinity
.. autofunction:: coarse_linkage
.. autofunction:: coarse_sizes
.. autofunction:: cluster_lineage
.. autofunction:: build_sankey_data
.. autofunction:: dendrogram_layout

.. autoclass:: ClusterDendrogram


Replicate runs at one *k*
-------------------------

For several runs of a model at the same *k* (for instance ADMIXTURE
replicates): how similar the runs are, and whether they fall into distinct
modes. The k-sweep does not use these.

.. autosummary::

   mode_analysis
   modestripe
   run_similarity
   detect_modes
   widest_gap
   consensus_from_runs
   clumppling_modes
   load_pong_filemap
   ModeAnalysis

.. autofunction:: mode_analysis
.. autofunction:: modestripe
.. autofunction:: run_similarity
.. autofunction:: detect_modes
.. autofunction:: widest_gap
.. autofunction:: consensus_from_runs
.. autofunction:: clumppling_modes
.. autofunction:: load_pong_filemap

.. autoclass:: ModeAnalysis
   :members:


Maintenance
-----------

.. autofunction:: verify_pass_loop
