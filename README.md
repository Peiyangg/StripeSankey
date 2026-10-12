<p align="center">
  <img src="https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/raw/main/docs/StripeSankey_logo.png" alt="StripeSankey" width="420">
</p>

<p align="center">
  <em>The volume-accurate k-sweep figure, and the consensus behind it.</em>
</p>

---

Fit a soft-clustering model at several `k` and you get several answers, with no
way to see how they relate. StripeSankey fits the sweep and draws all of it as
one figure: each column is a **full census** of one `k`, and node height and
ribbon width are the same head count — so every ribbon entering or leaving a
node sums to exactly that node, and a ribbon's thickness is a number of samples
you can read off.

It was built for microbiome count tables and is not limited to them: the
pipeline needs a count matrix, a per-feature annotation and per-sample
metadata, and nothing in it knows what the features are. The worked example is
population genetics.

![From a count table to the StripeSankey: one model per k, a chance-corrected consensus across k, and the figure coloured by it](https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/raw/main/docs/methodology.png)

```bash
pip install StripeSankey
```

## Four steps

```python
import stripesankey as ss

ss.prepare(base, counts, feature_annotation, metadata, level="family")
ss.sweep(base, k_range=range(2, 11))          # one fit per k, early-stopped
W_by_k = ss.load_W(base)                      # {k: DataFrame(sample x LC)}
fig = ss.sweep_figure(base, metadata_df=metadata, hover_field=["group"])
```

Already have a sweep from somewhere else? Skip the first two — the figures take
a dict of DataFrames, however it was produced. See *Bring your own sweep*.

### 1 — `prepare`

Checks that the three tables line up, collapses features to one annotation
level, and writes the feature table plus a manifest.

| table | index | columns |
|---|---|---|
| `counts` | sample id | feature id |
| `feature_annotation` | feature id | annotation levels |
| `metadata` | sample id | sample variables |

The checks are **structural only**: there is no way to look at a matrix of
numbers and tell what it is, so nothing tries. What it can know is that the
indices agree — and those two statements also settle orientation, which no
heuristic can. A transposed table fails both, and its transpose passing is the
proof, so the error says so outright. Counts are handled by rounding and then
checking the result is usable, which is also what catches a 0–1
relative-abundance table.

`level` is **any column of `feature_annotation`**, not a fixed taxonomy enum —
annotation schemes belong to the dataset.

### 2 — `sweep`

One fit per k from a fixed seed, written to disk as each lands.

```python
ss.sweep(base, k_range=range(2, 11),
         implementation="lda_gensim",     # or "nmf", or a callable (k, seed) -> estimator
         random_state=42)
```

Both fitting limits are **ceilings with an early exit**, so they are set high
and each fit takes only as long as it needs. Whether a ceiling was reached is
measured, not assumed:

```python
ss.convergence_report(base)
```

| column | low/high means |
|---|---|
| `docs_converged` | the per-document cap `iterations` is too small |
| `passes` at the ceiling | `max_passes` is too small |

A fit that did not settle stays on disk and is flagged; anything pooling across
k refuses it, because one unsettled fit poisons the consensus for every cluster.

### 3 — `load_W` / `load_H`

`X ≈ W · H`, which is also scikit-learn's convention:

| | shape | on disk |
|---|---|---|
| `W` | sample × LC | `results/W/W_{k}.csv` |
| `H` | LC × feature | `results/H/H_{k}.csv` |

A column of `W` is a **latent component (LC)**. `W` is all the figures need.

### Bring your own sweep

Any model giving a per-sample mixture will do. With scikit-learn's NMF:

```python
from sklearn.decomposition import NMF

W_by_k = {}
for k in range(2, 11):
    model = NMF(n_components=k, beta_loss="kullback-leibler", solver="mu",
                init="nndsvdar", max_iter=3000, random_state=42)
    W = model.fit_transform(counts.to_numpy())
    W_by_k[k] = pd.DataFrame(W / W.sum(axis=1, keepdims=True),
                             index=counts.index,
                             columns=[f"LC{i}" for i in range(k)])
```

Rows must be the **same sample index at every k** — the census and the ribbon
identity both assume every column describes the same population. Nothing is
written to disk; pass `W_by_k` straight to the calls below.

## Plotting

![stripesankey (top) and metasankey by region (bottom) on the 1000 Genomes example, K=2…8](https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/raw/main/example/population/viz/population_new_figure.png)

*The [1000 Genomes example](#example): stripesankey on top, metasankey by
`region` below — same layout, so each bar lines up across the two.*

### stripesankey — coloured by consensus cluster

```python
fig = ss.stripesankey(W_by_k, metadata_df=metadata, hover_field=["group"])
# or, straight from a sweep on disk:
fig = ss.sweep_figure(base, metadata_df=metadata, hover_field=["group"])
```

Colour is the **consensus cluster**: the `k`-agnostic grouping, computed here by
removing the co-membership expected by chance at each `k` before averaging, so
it does not drift when the `k` range changes.

Click a band, a ribbon or a cluster chip to trace those samples across every
`k`. Click a `K =` label to focus that column — it restacks by the first
`hover_field`. Read the selection back from `fig.selected_samples`.

### metasankey — the same figure, cut by metadata

```python
fig = ss.metasankey(W_by_k, metadata_df=metadata, hover_field=["group"])
fig = ss.sweep_figure(base, view="metasankey",
                      metadata_df=metadata, hover_field=["group"])
```

Identical layout, one thing changed: a node is sliced into a metadata field's
categories instead of into clusters. "Identical" is literal — both views come
out of one layout path, so a bar at a given height in one render is the same bar
in the other, and flipping between them answers *"is this cluster that
category?"* by eye.

### affinity heatmap — the matrix the clusters came from

```python
Q = ss.consensus_affinity({k: W.to_numpy() for k, W in W_by_k.items()})
Q = pd.DataFrame(Q, index=metadata.index, columns=metadata.index)

fig, order, labels = ss.affinity_heatmap(Q, above=metadata,
                                         annotations=["group"])
```

<p align="center">
  <img src="https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/raw/main/example/population/viz/affinity_K2-8.png" alt="Consensus affinity Q for the 1000 Genomes example, ordered by consensus cluster, with cluster and region strips" width="600">
</p>

`Q` is the signed, chance-corrected co-membership: positive means two samples
share components *more* than chance, negative *less*. Samples are ordered by
consensus cluster by default, and within a cluster by how core each member is,
so a gradient between neighbouring blocks stays visible rather than scrambled.

The **consensus cluster is drawn as the strip nearest the heatmap by default**,
coloured from the same `Q` — the blocks are what the ordering is built from, so
leaving them unlabelled makes the figure hard to read. Pass
`cluster_strip=False` to omit it. Add one or two coarse metadata fields beyond
that; a 26-level field above a 2,000-wide heatmap is a band of confetti.

## Example

[`example/population/`](example/population) runs all three figures on
[pong](https://github.com/ramachandran-lab/pong)'s published 1000 Genomes
Phase 3 result (2,426 individuals, ADMIXTURE at K=2…8), as marimo and Jupyter
notebooks. It is a control with a known answer: the consensus recovers the five
continental regions at **ARI 0.84** without ever seeing them, merging EUR and
AMR — which is correct, since those panels share ancestry.

## Hard labels

For an ensemble of **hard** labels instead of soft assignments — k-means at
several `k`, or different algorithms at one `k`:

```python
fig = ss.hardstripe(labels_df, colorby="consensus", metadata_df=metadata)
```

## Citation

If StripeSankey is useful in your work, please cite the paper (in preparation).

## License

MIT
