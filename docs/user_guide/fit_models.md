# How to fit models with StripeSankey

Fitting is two calls: {func}`~stripesankey.prepare` checks the tables and
writes the feature table, and {func}`~stripesankey.sweep` fits one model per
*k* and computes the consensus across *k*.

## `prepare`: check and collapse the tables

```python
import stripesankey as ss

ss.prepare(base, counts, feature_annotation, metadata, level="genus")
```

### What is checked

`prepare` checks structure, not content:

- `counts` holds numbers, with no missing or negative values and no duplicate
  sample or feature ids.
- Every column of `counts` has a row in `feature_annotation`, and every row of
  `counts` has a row in `metadata`.
- Counts are rounded to integers, since LDA needs them, and no sample may be
  left empty by the rounding. A relative-abundance table, with values between
  0 and 1, fails here: rounding can't bring back the library sizes, so supply
  raw counts.

If the ids match only when `counts` is flipped, the error says the table looks
transposed and tells you to pass `counts.T`. To run the checks without writing
anything, call {func}`~stripesankey.validate_tables` with the same arguments.

### Choosing `level`

`level` is any column of `feature_annotation`. The counts of all features that
share a value at that level are summed. For a 16S table you might collapse
ASVs to `"genus"`; a PR2 18S table has other columns, such as `"Division"`.
`level=None` (the default) keeps one feature per column of `counts`.

One base folder holds one preparation. Preparing it again with a different
`level` or different samples removes `results/`, because those fits describe
the old table. Preparing again with the same inputs changes nothing.

## `sweep`: one fit per *k*

```python
ss.sweep(base, k_range=range(2, 11), implementation="lda_gensim", random_state=42)
```

### Built-in models

| `implementation` | model | library |
|---|---|---|
| `"lda_gensim"` (default) | LDA, variational Bayes | [gensim](https://radimrehurek.com/gensim/) |
| `"nmf"` | NMF, generalized Kullback-Leibler loss, *nndsvdar* initialisation | [scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.NMF.html) |
| a function `(k, seed) -> model` | your own | see [How to customize the model](custom_models.md) |

### Options you will use

`k_range`
: The *k* values to fit, e.g. `range(2, 11)` or `[2, 4, 6, 8]`.

`random_state`
: The seed. There is one fit per *k*, so the seed fixes the result.

`force`
: `True` refits *k* values that are already on disk. By default a *k* whose
  `results/W/W_{k}.csv` exists is skipped, so you can extend a sweep (fit
  `range(2, 11)`, then `range(2, 16)`) without refitting the first part.

`workers`
: How many processes fit in parallel (default: the number of CPUs, at most
  10). `workers=1` fits in the current process with no pool. Use it in a REPL
  or any setup where the worker processes fail to start.

```{important}
The fits run in a process pool. On macOS and Windows each worker re-imports the
calling module, so a **script** that calls `sweep` must do so under
`if __name__ == "__main__":`, or it will start new workers forever. Notebooks
don't need this.
```

### Did each fit converge?

`sweep` prints a convergence table when it finishes. Get it back at any time
with:

```python
ss.convergence_report(base)
ss.unsettled_k(base)          # the k values whose fit did not settle
```

For **LDA (gensim)**, a fit counts as settled when the change in the topics
over the last pass drops below `rel_tol` (default `1e-3`) of the largest change
the fit made. The fit stops as soon as that happens. The report shows the
number of passes used, the fraction of documents whose per-document step
converged, and the final ratio. The budgets (`max_passes=1000`,
`iterations=5000`) are ceilings, not costs, so a fit only takes as long as it
needs. You can override them with keyword arguments to `sweep`
(`max_passes`, `iterations`, `alpha`, `eta`), though you should not need to.

For **NMF**, a fit counts as settled when scikit-learn reports convergence
before reaching `max_iter`.

A *k* that did not settle is kept on disk and flagged in `run_info.json`. It
is still part of the consensus, but the figures leave it out unless you pass
`exclude_unsettled=False`.

### The consensus

After the fits, `sweep` computes the consensus across every *k* on disk and
writes `results/consensus.json`. Two options shape it:

`resolution`
: Higher values give more, smaller clusters. The default `0.0` groups samples
  that are together more often than chance.

`noise_threshold`
: A sample whose mean affinity to the rest of its own cluster is at or below
  this value is labelled `-1` (noise). Default `0.0`.

Changing them refits nothing. Every *k* is already on disk, so this only
recomputes the consensus:

```python
ss.sweep(base, resolution=0.1)
```

## What `sweep` writes

| file | contents |
|---|---|
| `results/W/W_{k}.csv` | sample × LC proportions; each row sums to 1 |
| `results/H/H_{k}.csv` | LC × feature profiles |
| `results/consensus.json` | the consensus cluster of each sample, cluster sizes, the *k* pooled |
| `results/run_info.json` | implementation, *k* list, seed, budgets, convergence per *k* |
| `results/metrics.csv` | per *k*: topic coherence (`c_v`), plus perplexity (gensim LDA) or reconstruction error (NMF) |
| `results/diagnostics/topic_diff_{k}.csv` | LDA (gensim) only: the change in the topics at every pass |

`sweep` also returns the contents of `run_info.json` as a dict.
