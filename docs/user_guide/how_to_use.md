# How to use StripeSankey

## Install

```bash
pip install stripesankey
```

The figures are interactive widgets ([anywidget](https://anywidget.dev)), so
they display in Jupyter, JupyterLab, VS Code notebooks and
[marimo](https://marimo.io).

## The workflow

Everything happens in one **base folder**. Each step reads what the previous
one wrote, so a step can be re-run on its own and a sweep fitted once can be
plotted many times.

```
prepare(base, ...)        1. check the tables, write the feature table
sweep(base, k_range)      2. fit one model per k, then the consensus across k
stripesankey(base, ...)   3. draw it
```

If your sweep was fitted somewhere else (in R, or with ADMIXTURE), skip step 1
and the fitting: see
[How to apply StripeSankey to ADMIXTURE/STRUCTURE](admixture_structure.md).

## Your input: three tables

| table | index | columns | values |
|---|---|---|---|
| `counts` | sample id | feature id | counts (non-negative integers) |
| `feature_annotation` | feature id | annotation levels | e.g. taxonomy |
| `metadata` | sample id | sample variables | anything |

The tables are linked through their indices: the rows of `counts` are the rows
of `metadata`, and the columns of `counts` are the rows of
`feature_annotation`. All three are pandas DataFrames.

```python
import pandas as pd

counts = pd.read_csv("asv_table.csv", index_col=0)          # sample x feature
feature_annotation = pd.read_csv("taxonomy.csv", index_col=0)  # feature x level
metadata = pd.read_csv("metadata.csv", index_col=0)         # sample x variable
```

## Step 1: `prepare`

```python
import stripesankey as ss

base = "my_sweep"
ss.prepare(base, counts, feature_annotation, metadata, level="genus")
```

`prepare` checks that the tables line up, collapses the counts to one
annotation `level` if you give one, and writes the result to
`base/intermediate/`. If the tables don't line up it raises an error that says
what is wrong; a transposed count table is detected and reported as such. See
[How to fit models](fit_models.md) for the details.

## Step 2: `sweep`

```python
ss.sweep(base, k_range=range(2, 11), implementation="nmf", random_state=42)
```

One fit per *k*, each saved to disk as it finishes, then the consensus across
*k*. A *k* that is already on disk is not fitted again, so re-running the cell
is cheap.

```{important}
In a **script** on macOS or Windows, put the call under
`if __name__ == "__main__":`. The fits run in parallel worker processes, and
each worker re-imports your script. Notebooks don't need this.
```

## Step 3: plot

```python
fig = ss.stripesankey(base, metadata_df=metadata, hover_field=["group"])
fig
```

`hover_field` takes up to three columns of `metadata`; their composition shows
in the tooltip. The other two views read the same folder:

```python
fig = ss.metasankey(base, metadata_df=metadata, hover_field=["group"])

Q = ss.consensus_affinity(ss.load_W(base))
heatmap, order, labels = ss.affinity_heatmap(Q, above=metadata, annotations=["group"])
```

[How to interpret the results](interpret.md) explains what each view shows.

## Interacting with the figure

- **Click a band, a ribbon or a cluster chip** to trace those samples across
  every *k*.
- **Click a `K =` label** to focus that column. It restacks by the first
  `hover_field`.

The selection comes back to Python:

```python
fig.selected_samples          # the selected sample ids
fig.selected(metadata)        # the metadata rows of those samples
```

In **marimo**, wrap the widget so its value reaches Python:

```python
import marimo as mo

stripe = mo.ui.anywidget(ss.stripesankey(base, metadata_df=metadata, hover_field=["group"]))
stripe
```

and read the selection in another cell with
`stripe.value["selected_samples"]`.

## Saving a figure

```python
ss.save_widget_html(fig, "stripesankey.html")
```

This writes a self-contained, interactive HTML file that opens in any browser
(the D3 library is loaded from its CDN when the file is opened). The figure
stays interactive, but a selection no longer reaches Python. For a
publication figure, open the file in a browser and take a screenshot or print
it to PDF.

The affinity heatmap is a matplotlib figure: pass `save_path="heatmap.pdf"` or
call `heatmap.savefig(...)`.

## What ends up in the base folder

```
base/
├── intermediate/                       # written by prepare
│   ├── features.csv                    # the sample x feature table that is fitted
│   ├── feature_annotation.csv
│   └── manifest.json                   # level, shapes, validation report
└── results/                            # written by sweep
    ├── W/W_{k}.csv                     # sample x LC, one file per k
    ├── H/H_{k}.csv                     # LC x feature, one file per k
    ├── diagnostics/topic_diff_{k}.csv  # LDA (gensim) only
    ├── consensus.json                  # consensus cluster of each sample
    ├── run_info.json                   # k list, implementation, convergence per k
    └── metrics.csv                     # coherence and loss per k
```

Read any of it back with the loaders:

```python
W = ss.load_W(base)                 # {k: DataFrame}, sample x LC
H = ss.load_H(base, k=5)            # LC x feature at k = 5
consensus = ss.load_consensus(base) # includes "sample_to_cluster"
ss.convergence_report(base)         # did each fit settle?
```
