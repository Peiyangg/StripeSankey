# What is StripeSankey?

Mixed membership models describe every sample as a mixture of *k* latent
components (LCs). LDA and NMF on a microbiome table do this, and so do
ADMIXTURE and STRUCTURE on genotypes. Each of them asks you for *k*, and the
answer changes with it: a component at *k* = 3 can split in two at *k* = 4, or
samples can move from one component to another.

StripeSankey fits the model at a range of *k* (a **sweep**) and draws the whole
sweep as one figure, so you can see what persists, what splits and what merges
as *k* grows.

```{image} ../methodology.png
:alt: From a count table to the StripeSankey, through one model per k, a chance-corrected consensus across k, and the figure coloured by it
```

## The figure

- **One column per *k*.** Each column is a census: every sample is counted
  once, in the LC that holds its largest proportion at that *k*. A node is one
  LC, and its height is the number of samples counted there.
- **Ribbons between neighbouring columns.** A ribbon carries the samples that
  sit in one LC at one *k* and in another LC at the next. Node heights and
  ribbon widths are the same head count, so every ribbon entering or leaving a
  node sums to exactly that node.
- **Stripes coloured by consensus cluster.** Each node is sliced into the
  consensus clusters of its samples. The consensus is computed once across the
  whole sweep, so a sample has the same colour in every column.

## The consensus across *k*

At each *k*, StripeSankey measures how often two samples draw the same
component, subtracts what chance alone would give at that *k*, and averages the
result over all *k*. This gives a signed, sample-by-sample affinity `Q`:
positive means two samples share components more often than chance, negative
less often.

The chance correction is what makes the average meaningful. Without it, small
*k* (where any two samples often share a component) and large *k* (where they
rarely do) pull the average in opposite directions, and the answer moves when
the *k* range moves.

`Q` is then partitioned into clusters with the Leiden algorithm under a
Constant Potts objective. No number of clusters is needed: two samples are
grouped when they are together more often than chance. Samples that belong to
no cluster above chance are labelled `-1` (noise). The colours and the legend
tree of the figure are both built from the same `Q`, so they agree with the
clustering.

The method follows Jeub, Sporns & Fortunato, *Multiresolution Consensus
Clustering in Networks*, Scientific Reports (2018).

## Three views of one sweep

| View | Function | Shows |
|---|---|---|
| stripesankey | {func}`stripesankey.stripesankey` | the census, nodes sliced by consensus cluster |
| metasankey | {func}`stripesankey.metasankey` | the same layout, nodes sliced by a metadata field |
| affinity heatmap | {func}`stripesankey.affinity_heatmap` | the matrix `Q` the clusters came from |

For an ensemble of **hard** labels instead of soft proportions (for instance
k-means at several *k*), use {func}`stripesankey.hardstripe`.

## Terms used in this guide

*k*
: The number of latent components a model is fitted with.

LC (latent component)
: One component of a model: a topic in LDA, a factor in NMF, an ancestral
  population in ADMIXTURE.

`W` and `H`
: The two matrices of `X ≈ W · H`. `W` is sample × LC (each sample's
  proportions), `H` is LC × feature (each component's profile). This is also
  scikit-learn's naming.

sweep
: One fit per *k* over a range of *k*.

base folder
: The folder that holds a sweep: the prepared input under `intermediate/` and
  the results under `results/`. Every StripeSankey function takes it as its
  first argument.

consensus cluster
: A group of samples that share components more often than chance across the
  whole sweep. `-1` marks noise.
