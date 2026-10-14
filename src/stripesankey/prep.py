"""
Step 1 -- check the input tables and write the feature table.

Structure only: there is no way to look at a matrix of numbers and tell whether
it is a microbiome ASV table, so nothing here tries. What it checks is what is
knowable -- that the three tables' indices agree, which also settles
orientation.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import warnings
from datetime import datetime, timezone
from typing import Iterable

import numpy as np
import pandas as pd

from .mallet import write_corpus


_FORMAT = """Expected format:
  asv_df              index = sample id,  columns = feature id,  values = counts
  feature_annotation  index = feature id, columns = annotation levels
  metadata            index = sample id,  columns = sample variables
The three are linked by those indices: asv_df's rows must be metadata's rows,
and asv_df's columns must be feature_annotation's rows."""


def validate_tables(asv_df: pd.DataFrame,
                    feature_annotation: pd.DataFrame | None = None,
                    metadata: pd.DataFrame | None = None,
                    *, level: str | None = None) -> dict:
    """
    Check that the tables line up. Structure only -- never content.

    There is no way to look at a matrix of numbers and tell whether it is a
    microbiome ASV table, so this does not try. What it checks is what is
    actually knowable: that the indices agree. ``asv_df``'s rows have to be
    ``metadata``'s rows, and ``asv_df``'s columns have to be
    ``feature_annotation``'s rows. Those two statements also settle
    orientation, which no heuristic can: a transposed table fails both, and
    its transpose passing is the proof, so the message says so outright
    instead of guessing from the shape.

    Counts are handled by rounding (LDA needs integers) and then checking no
    sample was emptied by it -- which is also what catches a 0-1
    relative-abundance table, with no need to classify the input first.

    Returns a report dict; raises ``ValueError`` with the expected layout on
    any failure.
    """
    report: dict = {}
    problems: list[str] = []

    if not isinstance(asv_df, pd.DataFrame):
        raise TypeError("asv_df must be a DataFrame.\n" + _FORMAT)
    report["n_samples"], report["n_features"] = asv_df.shape

    if not np.issubdtype(asv_df.to_numpy().dtype, np.number):
        problems.append("asv_df holds non-numeric values; it must be a count matrix")
        raise ValueError("table validation failed:\n  - " + problems[0] + "\n\n" + _FORMAT)

    X = np.nan_to_num(asv_df.to_numpy())
    if np.isnan(asv_df.to_numpy()).any():
        problems.append(f"asv_df has {int(np.isnan(asv_df.to_numpy()).sum())} NaN value(s)")
    if (X < 0).any():
        problems.append(f"asv_df has {int((X < 0).sum())} negative value(s)")
    if asv_df.index.duplicated().any():
        problems.append(f"asv_df has {int(asv_df.index.duplicated().sum())} duplicate "
                        "sample id(s) in its index")
    if asv_df.columns.duplicated().any():
        problems.append(f"asv_df has {int(asv_df.columns.duplicated().sum())} duplicate "
                        "feature id(s) in its columns")

    # --- the alignment checks, which also settle orientation ---------------
    def _overlap(a, b):
        return len(set(a) & set(b))

    transposed_would_fit = False
    if feature_annotation is not None:
        hit = _overlap(asv_df.columns, feature_annotation.index)
        report["features_annotated"] = hit
        if hit < asv_df.shape[1]:
            if _overlap(asv_df.index, feature_annotation.index) > hit:
                transposed_would_fit = True
            else:
                missing = [str(c) for c in asv_df.columns
                           if c not in feature_annotation.index][:5]
                problems.append(
                    f"{asv_df.shape[1] - hit} of asv_df's {asv_df.shape[1]} columns "
                    f"are not in feature_annotation's index (e.g. {missing}). "
                    "Every feature column needs an annotation row, or the "
                    "collapse mixes annotated and unannotated features under "
                    "colliding names."
                )
        if level is not None and level not in feature_annotation.columns:
            problems.append(
                f"level={level!r} is not a column of feature_annotation. "
                f"Available: {list(feature_annotation.columns)}"
            )

    if metadata is not None:
        hit = _overlap(asv_df.index, metadata.index)
        report["samples_with_metadata"] = hit
        if hit < asv_df.shape[0]:
            if _overlap(asv_df.columns, metadata.index) > hit:
                transposed_would_fit = True
            else:
                missing = [str(i) for i in asv_df.index if i not in metadata.index][:5]
                problems.append(
                    f"{asv_df.shape[0] - hit} of asv_df's {asv_df.shape[0]} rows "
                    f"are not in metadata's index (e.g. {missing})."
                )

    if transposed_would_fit:
        problems = [
            "asv_df looks transposed: its ROWS match the feature/sample ids that "
            "should be matching its COLUMNS, and vice versa. Pass `asv_df.T`."
        ]

    # --- counts: round, then check the result is usable --------------------
    rounded = np.rint(X)
    report["rounded"] = bool(not np.array_equal(X, rounded))
    totals = rounded.sum(axis=1)
    report["count_min"] = float(totals.min())
    report["count_median"] = float(np.median(totals))

    empty = [str(s) for s in asv_df.index[totals == 0]]
    report["empty_samples"] = len(empty)
    if empty and not transposed_would_fit:
        problems.append(
            f"{len(empty)} sample(s) hold no counts once rounded to integers "
            f"(e.g. {empty[:5]}). A 0-1 relative-abundance table does this: the "
            "library sizes are gone and rounding cannot invent them. Supply raw "
            "counts, or fit NMF, which does not need them."
        )

    report["ok"] = not problems
    report["problems"] = problems
    if problems:
        raise ValueError("table validation failed:\n  - "
                         + "\n  - ".join(problems) + "\n\n" + _FORMAT)
    return report


#: Back-compat alias.
validate_counts = validate_tables


#: Annotation columns that are never a grouping level (sequences, provenance).
_NON_LEVEL_COLUMNS = {"Sequence", "Source_database", "Sequence_Type"}


def prepare(base_directory: str,
            asv_df: pd.DataFrame,
            feature_annotation: pd.DataFrame,
            metadata: pd.DataFrame | None = None,
            *,
            level: str | None = None,
            verbose: bool = True) -> dict:
    """
    Validate, collapse to one annotation ``level``, and write the cache.

    ``level`` is **any column of** ``feature_annotation`` -- not a fixed
    taxonomic enum. Annotation schemes are dataset-specific (a PR2 18S table
    has ``Supergroup`` and ``Division``; a SILVA 16S table does not), so the
    library cannot know them in advance. ``level=None`` keeps one feature per
    input column.

    Writes ``intermediate/{features.csv, feature_annotation.csv, manifest.json}``
    -- plus ``intermediate/mallet/corpus.txt``, the same table as the document
    file MALLET reads -- and returns the manifest. One folder holds one preprocessing, so the
    feature table is always ``features.csv`` and the manifest records which
    level produced it. Preparing the folder again replaces it. If the feature
    table changed -- another level, other samples -- ``results/`` is removed
    too: those fits describe the old table, and ``sweep`` would otherwise skip
    their k and draw them as fits of the new one. Re-running with the same
    inputs keeps everything.
    """
    inter = os.path.join(base_directory, "intermediate")
    os.makedirs(inter, exist_ok=True)

    if level is not None and level in _NON_LEVEL_COLUMNS:
        raise ValueError(f"level={level!r} is not a grouping level "
                         f"(it is per-feature data, not a taxon)")

    report = validate_tables(asv_df, feature_annotation, metadata, level=level)
    X = asv_df.round().astype(np.int64)

    if level is None:
        features = X
        feature_column = None
    else:
        keys = feature_annotation.loc[X.columns, level]
        keys = keys.fillna(f"unassigned_{level}").astype(str)
        features = X.T.groupby(keys.to_numpy(), sort=False).sum().T
        feature_column = level

    # Rounding can empty a feature that held only sub-0.5 values.
    nonempty = features.sum(axis=0) > 0
    dropped = int((~nonempty).sum())
    features = features.loc[:, nonempty]

    manifest = {
        "level": level,
        "feature_column": feature_column,
        "n_samples": int(features.shape[0]),
        "n_features": int(features.shape[1]),
        "features_dropped_empty": dropped,
        "total_count": int(features.to_numpy().sum()),
        "validation": report,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # Compared as the exact bytes written, so re-running a notebook cell with
    # the same inputs is a no-op rather than a refit.
    table = features.to_csv().encode()
    fpath = os.path.join(inter, "features.csv")
    res = os.path.join(base_directory, "results")
    if os.path.exists(fpath) and os.path.isdir(res):
        with open(fpath, "rb") as f:
            changed = f.read() != table
        if changed:
            shutil.rmtree(res)
            # The MALLET corpus is this table as tokens, imported for the old one.
            shutil.rmtree(os.path.join(inter, "mallet"), ignore_errors=True)
            warnings.warn(
                f"the feature table in {base_directory} changed (level={level!r}), "
                "so results/ was removed: those fits describe the old table. "
                "Run sweep() again.",
                stacklevel=2,
            )

    with open(fpath, "wb") as f:
        f.write(table)
    # The same table as a MALLET document file, for sweep(implementation=
    # "lda_mallet"). Skipped when it already matches; see mallet.write_corpus.
    write_corpus(base_directory, features.to_numpy(), hashlib.sha256(table).hexdigest())
    feature_annotation.to_csv(os.path.join(inter, "feature_annotation.csv"))
    with open(os.path.join(inter, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    if verbose:
        print(f"[prepare] {features.shape[0]} samples x {features.shape[1]} features "
              f"(level={level!r}"
              f"{', rounded' if report['rounded'] else ''}"
              f"{f', {dropped} features emptied by rounding' if dropped else ''})")
        print(f"[prepare] total counts: {manifest['total_count']:,}  "
              f"mean/sample: {manifest['total_count'] / features.shape[0]:,.0f}")
    return manifest


def load_manifest(base_directory: str) -> dict:
    """What :func:`prepare` recorded: level, shapes, validation report."""
    with open(os.path.join(base_directory, "intermediate", "manifest.json")) as f:
        return json.load(f)


def load_features(base_directory: str) -> pd.DataFrame:
    """The sample x feature count matrix the sweep actually fits."""
    return pd.read_csv(
        os.path.join(base_directory, "intermediate", "features.csv"), index_col=0)


__all__ = ["validate_tables", "validate_counts", "prepare",
           "load_manifest", "load_features"]
