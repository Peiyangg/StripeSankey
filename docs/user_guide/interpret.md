# How to interpret the results

## Reading the stripesankey

### A column is a census of one *k*

Every sample is counted once in each column, in the latent component (LC) that
holds its largest proportion at that *k*. A node's height is the number of
samples counted there.

The census uses no confidence threshold, so a sample split 0.51 / 0.49 between
two LCs counts the same as one at 0.99. The figure shows where samples land,
not how sure the model is about them.

### A ribbon is a group of samples moving between columns

A ribbon joins an LC in one column to an LC in the next, and its thickness is
the number of samples that sit in both. Because node heights and ribbon widths
are the same head count, the ribbons leaving a node add up to exactly that
node. Some patterns to look for as *k* grows:

- **A component persists:** one wide ribbon carries most of a node into a
  single node in the next column.
- **A component splits:** a node sends large ribbons into two or more nodes.
- **Samples are reassigned:** a node receives large ribbons from several nodes
  in the previous column.

When `k_list` skips some *k*, ribbons join the neighbouring columns that are
drawn.

### The stripes are the consensus clusters

Each node is sliced by the consensus cluster of its samples. The consensus
pools every *k* in the sweep, including any that aren't drawn, so a sample has
the same colour in every column.

- A node in **one colour** holds samples that also group together across the
  rest of the sweep.
- A node in **several colours** holds samples that share a component at this
  *k* but separate at other *k*.
- A colour that **stays together** from column to column is a group that is
  stable across *k*.

The legend on the left is a tree of the clusters, built from the same affinity
`Q` as the clusters themselves. Clusters that are close in the tree are alike,
and the palette follows the tree, so similar hues mean related clusters.

Samples labelled `-1` (noise) are not together with any cluster more often
than chance.

### Columns that are missing

A *k* whose fit did not settle is left out of the figure by default, with a
warning. A column built from an unsettled fit says more about the fit than the
data. Pass `exclude_unsettled=False` to draw it anyway, and check
`ss.convergence_report(base)` to see why it was flagged.

## Reading the metasankey

The metasankey has the same columns, the same order and the same node
positions as the stripesankey. Only the slicing changes: nodes and ribbons are
coloured by the categories of the first `hover_field` instead of by cluster.

Because the layout is identical, a bar at a given height is the same bar in
both figures. Switching between the two shows by eye whether a cluster
corresponds to a metadata category.

## Reading the affinity heatmap

The heatmap shows `Q`, the matrix the consensus clusters were cut from.
Entry `(i, j)` is how often samples *i* and *j* draw the same component across
the sweep, minus what chance alone would give:

- **positive**: together more often than chance;
- **around 0**: at chance;
- **negative**: together less often than chance.

Samples are ordered by consensus cluster, so the clusters appear as blocks
along the diagonal. The strip nearest the heatmap labels the clusters, and
metadata columns passed as `annotations` are drawn above it. Pass
`sort="column_name"` to order by a metadata column instead, which shows
whether a known grouping is recovered.

What to look for:

- **Well-separated blocks:** clusters that are distinct across the sweep.
- **Positive entries between two blocks:** clusters that are related.
- **Faint rows inside a block:** samples that belong to their cluster only
  weakly.

The colour scale is capped at the 99th percentile of |Q| by default (`vmax`),
so a few extreme pairs don't wash out the rest.

## Checking against what you know

The consensus never sees your metadata, so comparing the two is a fair check:

```python
import pandas as pd
from sklearn.metrics import adjusted_rand_score

consensus = ss.load_consensus(base)
clusters = pd.Series(consensus["sample_to_cluster"], name="consensus")
clusters.index = clusters.index.astype(str)
metadata.index = metadata.index.astype(str)

table = metadata.join(clusters)
pd.crosstab(table["consensus"], table["group"])
adjusted_rand_score(table["consensus"], table["group"])
```

To look at a group you found in the figure, click it and read
`fig.selected(metadata)`.

## Changing the clustering

If the clusters are too coarse or too fine, change `resolution` (higher means
more, smaller clusters) and re-run `sweep`. Nothing is refitted:

```python
ss.sweep(base, resolution=0.1)
```

See [How to fit models](fit_models.md#the-consensus).
