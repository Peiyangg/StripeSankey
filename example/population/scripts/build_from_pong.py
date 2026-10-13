"""
Turn pong's own worked example into the layout the API reads.

pong (Behr et al. 2016, Bioinformatics 32:2817) ships 8 independent ADMIXTURE
runs at each of K=2..8 on 2,426 unrelated 1000 Genomes Phase 3 individuals.
Its CLI finds the **major mode** at each K -- Munkres-matched similarity between
the replicates, disjoint cliques at >= 0.97, the clique with the most runs wins
-- and that mode's Q matrix is what lands here.

Why this example exists: pong solves, for ADMIXTURE output on genotypes, the
same three problems this package solves for a k-sweep -- label switching,
multimodality, and alignment across K. So its published result is a control
with a known answer, and an ancestry Q matrix is a `W` by another name:
individuals x components, rows summing to 1.

Only the precomputed major modes are stored, not all 59 .Q files (6.5 MB) --
re-deriving a published major mode is not what the example is for.

    python scripts/build_from_pong.py <path to 1kg_p3> 
"""
import sys
from pathlib import Path

import pandas as pd

import stripesankey as ss

HERE = Path(__file__).resolve().parent.parent          # example/population
# The readers expect `<base>/results/...`, because a sweep's base directory
# also holds `intermediate/`. An imported dataset has nothing to preprocess, so
# the extra level is pure structure here -- kept anyway so the same reader works
# on a pong import and on a sweep without a special case.
BASE = HERE / "stripesankey_output"
OUT = BASE / "results"
DATA = HERE / "data"


def main(src: Path):
    (OUT / "W").mkdir(parents=True, exist_ok=True)
    DATA.mkdir(exist_ok=True)

    mc_dir = src / "results" / "MC_Sample"
    ks = sorted(int(p.stem.replace("MC_Sample_probabilities", ""))
                for p in mc_dir.glob("MC_Sample_probabilities*.csv"))
    if not ks:
        raise SystemExit(f"no MC_Sample_probabilities*.csv under {mc_dir}")

    Ws = {}
    for k in ks:
        # On disk the old layout is components x individuals, indexed `K2_MC0`.
        # `W` is individuals x components, indexed `LC0`.
        raw = pd.read_csv(mc_dir / f"MC_Sample_probabilities{k}.csv", index_col=0)
        W = raw.T
        W.columns = [f"LC{i}" for i in range(W.shape[1])]
        W.index.name = "sample"
        W = W.div(W.sum(axis=1), axis=0)               # rows sum to 1
        # 6 decimals is already finer than ADMIXTURE reports; full float repr
        # triples the file for no information.
        W.round(6).to_csv(OUT / "W" / f"W_{k}.csv")
        Ws[k] = W
        print(f"  W_{k}.csv  {W.shape[0]} individuals x {W.shape[1]} components")

    # ---- consensus across K ----------------------------------------------
    # Every W is on disk, so `sweep` fits nothing: it checks the tables line
    # up, then writes consensus.json and run_info.json next to them. The fits
    # were not made here, so there is no convergence for it to judge.
    ss.sweep(BASE)

    # ---- the individuals' labels, as metadata ----------------------------
    index = Ws[ks[0]].index
    # Three columns, and `region` is the superpopulation: AFR / AMR / EAS /
    # EUR / SAS, the 5-way grouping of the 26 `population` codes.
    src_meta = src / "data" / "metadata.csv"
    if src_meta.exists():
        meta = pd.read_csv(src_meta, index_col=0)
        meta = meta.reindex(index)
        meta.index.name = "sample"
        meta.to_csv(DATA / "metadata.csv")
        print(f"  metadata.csv  {len(meta)} individuals | "
              f"{meta['population'].nunique()} populations in "
              f"{meta['region'].nunique()} regions")
    else:
        print(f"  ! no metadata at {src_meta}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).expanduser())
