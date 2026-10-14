# StripeSankey

StripeSankey fits a mixed membership model (LDA, NMF, or your own) at several
values of *k* and draws the whole sweep as one figure. Every ribbon entering or
leaving a node sums to exactly that node, and a ribbon's thickness is a number
of samples you can read off.

It was built for microbiome count tables but isn't limited to them. Results
computed elsewhere, such as ADMIXTURE or STRUCTURE ancestry proportions or a
model fitted in R, go through the same figures.

```{image} ../example/population/viz/stripesankey_population.png
:alt: StripeSankey of an ADMIXTURE sweep of the 1000 Genomes Project, K = 2 to 8, coloured by consensus cluster
```

*An ADMIXTURE sweep of the 1000 Genomes Project, K = 2…8. See the
[human genomic data example](examples/human_genomics.md).*

## Installation

```bash
pip install stripesankey
```

## Quick start

```python
import stripesankey as ss

base = "my_sweep"                      # a folder; StripeSankey keeps everything here

ss.prepare(base, counts, feature_annotation, metadata)       # 1. check the tables
ss.sweep(base, k_range=range(2, 11), implementation="nmf")   # 2. one fit per k + consensus
ss.stripesankey(base, metadata_df=metadata, hover_field=["group"])  # 3. the figure
```

New here? Start with [What is StripeSankey?](user_guide/what_is.md), then
[How to use StripeSankey](user_guide/how_to_use.md).

```{toctree}
:maxdepth: 1
:caption: User Guide

user_guide/what_is
user_guide/how_to_use
user_guide/fit_models
user_guide/custom_models
user_guide/admixture_structure
user_guide/interpret
```

```{toctree}
:maxdepth: 1
:caption: Examples of StripeSankey Usage

examples/human_genomics
examples/microbiome
```

```{toctree}
:maxdepth: 1
:caption: API Reference

api/index
```
