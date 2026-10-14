# Human genomic data: 1000 Genomes

This example draws an ADMIXTURE sweep of the 1000 Genomes Project Phase 3:
2,426 individuals from 26 populations in 5 continental regions (AFR, AMR, EAS,
EUR, SAS), at *K* = 2…8. Because the regions are known, they give a check on
the result.

The ancestry proportions are the precomputed results that ship with
[pong](https://github.com/ramachandran-lab/pong) (Behr et al. 2016,
*Bioinformatics* 32:2817). pong ran 8 ADMIXTURE replicates at each *K* and
reports a major mode per *K*; that mode's matrix is what is used here. Nothing
is fitted by StripeSankey.

Everything below is in the repository under
[`example/population`](https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/tree/main/example/population).

## 1. Turn the ADMIXTURE results into a sweep

Each *K* becomes one `W_{K}.csv` (individuals × components, rows summing to 1),
and `sweep` computes the consensus across *K* without fitting anything. The
script
[`scripts/build_from_pong.py`](https://gitlab.kuleuven.be/aida-lab/public/StripeSankey/-/blob/main/example/population/scripts/build_from_pong.py)
does this from pong's example folder. Its core is:

```python
import pandas as pd
import stripesankey as ss

BASE = "example/population/stripesankey_output"

for K in range(2, 9):
    raw = pd.read_csv(f"MC_Sample_probabilities{K}.csv", index_col=0)
    W = raw.T                                        # individuals x components
    W.columns = [f"LC{i}" for i in range(W.shape[1])]
    W.index.name = "sample"
    W = W.div(W.sum(axis=1), axis=0)                 # rows sum to 1
    W.round(6).to_csv(f"{BASE}/results/W/W_{K}.csv")

ss.sweep(BASE)
```

The repository already contains the result, so you can start from step 2.

## 2. Does the consensus match the regions?

```python
import pandas as pd
from sklearn.metrics import adjusted_rand_score

metadata = pd.read_csv("example/population/data/metadata.csv", index_col=0)
consensus = ss.load_consensus(BASE)
clusters = pd.Series(consensus["sample_to_cluster"], name="consensus")

table = metadata.join(clusters)
adjusted_rand_score(table["consensus"], table["region"])   # 0.84
pd.crosstab(table["consensus"], table["region"])
```

| consensus cluster | AFR | AMR | EAS | EUR | SAS |
|---|---:|---:|---:|---:|---:|
| 0 | 3 | 329 | 0 | 496 | 0 |
| 1 | 629 | 2 | 0 | 0 | 0 |
| 2 | 0 | 1 | 492 | 0 | 0 |
| 3 | 0 | 0 | 0 | 0 | 474 |

The consensus never sees `region`, yet it recovers AFR, EAS and SAS as
separate clusters. EUR and AMR end up together in cluster 0, since many AMR
individuals share European ancestry.

## 3. stripesankey

```python
fig = ss.stripesankey(BASE, metadata_df=metadata,
                      hover_field=["region", "population"], figsize=(3, 5.2))
fig
```

![stripesankey of the 1000 Genomes ADMIXTURE sweep, K = 2 to 8, coloured by consensus cluster](../../example/population/viz/stripesankey_population.png)

```{raw} html
<p><a href="../_static/stripesankey_K2-8.html" target="_blank" rel="noopener">Open the interactive figure ↗</a>
Click a band or a ribbon to trace those individuals across <em>K</em>.</p>
```

## 4. metasankey by region

The same layout, with nodes and ribbons coloured by the first `hover_field`:

```python
fig = ss.metasankey(BASE, metadata_df=metadata,
                    hover_field=["region", "population"], figsize=(3, 5.2))
fig
```

![metasankey of the same sweep, coloured by continental region](../../example/population/viz/metasankey_population.png)

```{raw} html
<p><a href="../_static/metasankey_K2-8.html" target="_blank" rel="noopener">Open the interactive figure ↗</a></p>
```

Put the two figures side by side: the bars sit at the same heights in both,
so you can read off which region each consensus cluster corresponds to.

## 5. Affinity heatmap

```python
Q = ss.consensus_affinity(ss.load_W(BASE))
heatmap, order, labels = ss.affinity_heatmap(
    Q, above=table[["region"]], annotations=["region"], figsize=(3, 4),
    title="1000 Genomes Phase 3 — consensus affinity across K=2…8",
)
```

```{image} ../../example/population/viz/affinity_K2-8.png
:alt: Consensus affinity Q for the 1000 Genomes example, ordered by consensus cluster, with cluster and region strips
:width: 560px
:align: center
```

## Run it yourself

The example is a [marimo](https://marimo.io) notebook, also saved as a Jupyter
notebook:

```bash
marimo edit example/population/notebooks/population.py
# or
jupyter lab example/population/notebooks/population.ipynb
```
