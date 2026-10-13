# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "anywidget==0.11.0",
#     "leidenalg==0.12.0",
#     "matplotlib==3.11.2",
#     "numpy==2.5.4",
#     "pandas==3.0.6",
#     "python-igraph==1.0.0",
#     "scikit-learn==1.9.1",
# ]
# ///

import marimo

__generated_with = "0.17.0"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    # 1000 Genomes Phase 3

    Precomputed ADMIXTURE results (K=2…8, 2,426 individuals) from
    [pong](https://github.com/ramachandran-lab/pong)'s example. The true grouping
    (5 continental regions) is known, so we can check the result.

    1. **stripesankey**: clusters across K
    2. **metasankey**: the same view, coloured by metadata
    3. **affinity heatmap**: what the clusters are built from
    """
    )
    return


@app.cell
def _():
    import sys
    from pathlib import Path

    HERE = Path(__file__).resolve().parent
    POP = HERE.parent                      # example/population
    sys.path.insert(0, str(POP.parent.parent / "src"))        # the local stripesankey

    import marimo as mo
    import numpy as np
    import pandas as pd

    import stripesankey as ss

    BASE = POP / "stripesankey_output"
    return BASE, POP, mo, pd, ss


@app.cell
def _(BASE, pd):
    # W is sample x LC. Read straight off disk -- no reader needed for a CSV.
    W = {int(p.stem.split("_")[1]): pd.read_csv(p, index_col=0)
         for p in sorted((BASE / "results" / "W").glob("W_*.csv"))}
    K_LIST = sorted(W)
    print(f"W: K={K_LIST}, {W[K_LIST[0]].shape[0]} individuals")
    print(f"   row sums: {W[5].sum(axis=1).round(4).unique()[:3]}")
    return K_LIST, W


@app.cell
def _(BASE, POP, pd):
    import json

    metadata = pd.read_csv(POP / "data" / "metadata.csv", index_col=0)
    with open(BASE / "results" / "consensus.json") as _f:
        consensus = json.load(_f)
    clusters = {s: int(c) for s, c in consensus["sample_to_cluster"].items()}

    print(f"consensus across K={consensus['k_pooled']}: {consensus['sizes']}")
    print(f"metadata: {metadata['population'].nunique()} populations in "
          f"{metadata['region'].nunique()} regions")
    metadata.head()
    return clusters, metadata


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ### Does the consensus match the regions?

    The consensus never sees `region`.
    """
    )
    return


@app.cell
def _(clusters, metadata, pd):
    from sklearn.metrics import adjusted_rand_score

    _cl = pd.Series(clusters, name="consensus")
    meta_plus = metadata.join(_cl)
    print("ARI(consensus, region) = "
          f"{adjusted_rand_score(meta_plus['consensus'], meta_plus['region']):.4f}")
    pd.crosstab(meta_plus["consensus"], meta_plus["region"])
    return (meta_plus,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    AFR, EAS and SAS are recovered; EUR and AMR merge (they share ancestry).

    ## 1 — stripesankey

    One column per K, coloured by consensus cluster.
    Click a ribbon or a band to trace those individuals across K.
    """
    )
    return


@app.cell
def _(BASE, metadata, mo, ss):
    HOVER = ["region", "population"]

    # The palette and the legend tree are not passed: `stripesankey` builds both
    # from the same chance-corrected Q it clustered, so the left-column legend
    # agrees with the ribbons by construction. Override that pair only together
    # -- a palette without a matching tree is how the two start disagreeing.
    stripe = mo.ui.anywidget(ss.stripesankey(
        BASE, metadata_df=metadata, hover_field=HOVER, figsize=(3, 5.2)))
    stripe
    return (stripe,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""Click something above, then re-run this cell.""")
    return


@app.cell
def _(meta_plus, pd, stripe):
    _sel = (stripe.value or {}).get("selected_samples") or []
    if _sel:
        _sub = meta_plus.reindex([s for s in _sel if s in meta_plus.index])
        print(f"{len(_sel)} individuals selected")
        selection = pd.concat([_sub[c].value_counts().rename("n").to_frame().assign(field=c)
                               for c in ("region", "population", "consensus")])
    else:
        print("nothing selected yet — click a ribbon or a node band above")
        selection = pd.DataFrame()
    selection
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 2 — metasankey

    Same layout, coloured by a metadata field instead.
    """
    )
    return


@app.cell
def _(mo):
    field = mo.ui.dropdown(options=["region", "population"], value="region",
                           label="colour nodes and flows by: ")
    field
    return (field,)


@app.cell
def _(BASE, field, metadata, mo, ss):
    # The FIRST hover_field is what nodes and flows are coloured by.
    fields = [field.value] + [f for f in ("region", "population") if f != field.value]
    meta_stripe = mo.ui.anywidget(ss.metasankey(
        BASE, metadata_df=metadata, hover_field=fields, figsize=(3, 5.2)))
    meta_stripe
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## 3 — Affinity heatmap

    How often two individuals share components across K (positive = more than chance).
    The blocks are the consensus clusters.
    """
    )
    return


@app.cell
def _(W, meta_plus, pd, ss):
    Q = ss.consensus_affinity({k: w.to_numpy() for k, w in W.items()})
    Q = pd.DataFrame(Q, index=W[2].index, columns=W[2].index)
    print(f"Q: {Q.shape}, {Q.to_numpy().nbytes / 1e6:.0f} MB in memory")

    fig, order, labels = ss.affinity_heatmap(
        Q,
        above=meta_plus[["region"]],
        annotations=["region"],
        figsize=(3,4),
        title="1000 Genomes Phase 3 — consensus affinity across K=2…8",
    )
    fig
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ### Regenerating the data

    ```bash
    python ../scripts/build_from_pong.py <path to 1kg_p3>
    ```
    """
    )
    return


if __name__ == "__main__":
    app.run()
