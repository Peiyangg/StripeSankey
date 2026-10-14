# How to apply StripeSankey to ADMIXTURE/STRUCTURE results

An ancestry matrix from ADMIXTURE or STRUCTURE (individuals × *K*, each row
summing to 1) is a `W` matrix under another name. StripeSankey doesn't need to
fit anything: save one matrix per *K* in the base folder and let `sweep`
compute the consensus over them.

## The steps

1. **Run the tool at every *K*** you want to compare, e.g. *K* = 2…8.
2. **Keep one result per *K*.** If you ran several replicates per *K*,
   choose one representative per *K* first, for example the major mode that
   [pong](https://github.com/ramachandran-lab/pong) or
   [CLUMPAK](https://clumpak.tau.ac.il) reports.
3. **Save each matrix** as `base/results/W/W_{K}.csv`:
   - the individual id in the first column (the index), then one column per
     component;
   - each row summing to 1;
   - the same individuals in the same order at every *K*.
4. **Run `sweep` without `k_range`.** It finds the matrices on disk, checks
   that they line up, and writes `consensus.json` and `run_info.json`. Nothing
   is fitted and `prepare` is not needed.
5. **Plot**, with a metadata table indexed by the same individual ids.

## ADMIXTURE

ADMIXTURE writes one `<prefix>.<K>.Q` file per run: whitespace-separated, no
header, one row per individual in the order of the `.fam` file.

```python
from pathlib import Path

import pandas as pd
import stripesankey as ss

base = Path("admixture_sweep")
(base / "results" / "W").mkdir(parents=True, exist_ok=True)

# Individual ids from the .fam file: family id, then individual id.
fam = pd.read_csv("mydata.fam", sep=r"\s+", header=None)
ids = fam[1].astype(str)

for K in range(2, 9):
    W = pd.read_csv(f"mydata.{K}.Q", sep=r"\s+", header=None)
    W.index = ids
    W.index.name = "sample"
    W.columns = [f"LC{i}" for i in range(K)]
    W = W.div(W.sum(axis=1), axis=0)          # rows sum to 1
    W.to_csv(base / "results" / "W" / f"W_{K}.csv")

ss.sweep(base)
```

If individual ids repeat across families, build the index from both columns,
e.g. `fam[0].astype(str) + "_" + fam[1].astype(str)`.

fastSTRUCTURE writes its ancestry proportions as `<prefix>.<K>.meanQ` in the
same layout, so the same loop works with the file name changed.

## STRUCTURE

STRUCTURE writes the ancestry proportions inside each run's `_f` results file,
in the section *Inferred ancestry of individuals*. Tools that post-process
STRUCTURE runs, such as CLUMPAK and the R package
[pophelper](https://www.royfrancis.com/pophelper/), read these files and
align the replicates. Once you have one individuals × *K* table per *K*, the
steps are the same as for ADMIXTURE: save it as `W_{K}.csv` and run
`ss.sweep(base)`.

## From R

```r
# Q: a matrix or data frame, individuals x K, rownames = individual ids
dir.create("admixture_sweep/results/W", recursive = TRUE)
write.csv(Q, sprintf("admixture_sweep/results/W/W_%d.csv", ncol(Q)))
```

Then, in Python, `ss.sweep("admixture_sweep")`.

## Plot

```python
metadata = pd.read_csv("metadata.csv", index_col=0)   # indexed by individual id

ss.stripesankey(base, metadata_df=metadata, hover_field=["region", "population"])
ss.metasankey(base, metadata_df=metadata, hover_field=["region", "population"])
```

`run_info.json` records the implementation as `"external"`, since the fits
weren't made here. There is no convergence to check, so every *K* is drawn.

The [human genomic data example](../examples/human_genomics.md) does all of
this with pong's precomputed ADMIXTURE results for the 1000 Genomes Project.
