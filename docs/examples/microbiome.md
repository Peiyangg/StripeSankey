# Microbiome

This example fits a sweep to a 16S rRNA amplicon table: bacterial communities
on tomato roots in hydroponic greenhouses affected by hairy root disease
(HRD), 289 samples and 6,866 ASVs. Unlike the
[human genomic example](human_genomics.md), the models are fitted by
StripeSankey itself.

```{note}
The HRD data are not yet distributed with the repository. The code below shows
the full workflow; figures will be added once the data are public.
```

## The tables

```python
import pandas as pd
import stripesankey as ss

counts = pd.read_csv("HRD/asv_table.csv", index_col=0)    # sample x ASV, raw counts
taxonomy = pd.read_csv("HRD/taxonomy.csv", index_col=0)   # ASV x taxonomic level
metadata = pd.read_csv("HRD/metadata.csv", index_col=0)   # sample x variable
```

`metadata` has, among others, the columns `Diagnosis`, `Stage` and `Treatment`.

## Prepare: collapse the ASVs to genus

```python
base = "hrd_sweep"
ss.prepare(base, counts, taxonomy, metadata, level="Genus")
```

`level` is any column of `taxonomy`. Collapsing to genus sums the counts of all
ASVs in one genus, which gives fewer, denser features to fit.

## Sweep

With the built-in NMF:

```python
ss.sweep(base, k_range=range(2, 11), implementation="nmf", random_state=42)
ss.convergence_report(base)
```

Or with scikit-learn's LDA, passed as your own model (see
[How to customize the model](../user_guide/custom_models.md)):

```python
from sklearn.decomposition import LatentDirichletAllocation

def my_lda(k, seed):
    return LatentDirichletAllocation(n_components=k, learning_method="batch",
                                     max_iter=500, evaluate_every=1,
                                     random_state=seed)

ss.sweep("hrd_sweep_lda", k_range=range(2, 11), implementation=my_lda, random_state=42)
```

Each implementation needs its own base folder, and `prepare` must be run on
that folder first.

## Compare the consensus with the diagnosis

```python
consensus = ss.load_consensus(base)
clusters = pd.Series(consensus["sample_to_cluster"], name="consensus cluster")
pd.crosstab(clusters, metadata["Diagnosis"])
```

## Plot

```python
HOVER = ["Diagnosis", "Stage", "Treatment"]

ss.stripesankey(base, metadata_df=metadata, hover_field=HOVER)
ss.metasankey(base, metadata_df=metadata, hover_field=HOVER)

Q = ss.consensus_affinity(ss.load_W(base))
heatmap, order, labels = ss.affinity_heatmap(Q, above=metadata, annotations=["Diagnosis"])
```

## Which taxa make up a component?

`H` holds each component's profile over the genera. The top genera of every
component at *k* = 5:

```python
H = ss.load_H(base, k=5)            # LC x genus
H.apply(lambda row: row.nlargest(10).index.tolist(), axis=1)
```
