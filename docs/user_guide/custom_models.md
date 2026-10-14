# How to customize the model in Python

`sweep` accepts your own model in place of the built-ins. It fits it at every
*k*, saves `W` and `H`, checks convergence and computes the consensus, just as
it does for `"lda_gensim"` and `"nmf"`.

## The contract

Pass a function that takes `k` and a seed and returns an **unfitted** model:

```python
def my_model(k, seed):
    return ...   # an unfitted estimator with k components
```

The model needs scikit-learn's decomposition interface:

| | must give | shape |
|---|---|---|
| `fit_transform(X)` | returns `W` | samples × *k* |
| `components_` | holds `H` after fitting | *k* × features |

`X` is the sample × feature table that {func}`~stripesankey.prepare` wrote.
`sweep` passes its `random_state` in as `seed`, and normalises each row of `W`
to sum to 1 before saving it.

## Example: NMF with your own settings

```python
from sklearn.decomposition import NMF
import stripesankey as ss

def my_nmf(k, seed):
    return NMF(n_components=k, beta_loss="kullback-leibler", solver="mu",
               init="nndsvdar", max_iter=3000, random_state=seed)

ss.sweep(base, k_range=range(2, 11), implementation=my_nmf, random_state=42)
```

## Example: scikit-learn's LDA

```python
from sklearn.decomposition import LatentDirichletAllocation

def my_lda(k, seed):
    return LatentDirichletAllocation(
        n_components=k,
        learning_method="batch",
        max_iter=500,
        evaluate_every=1,
        random_state=seed,
    )

ss.sweep(base, k_range=range(2, 11), implementation=my_lda, random_state=42)
```

`evaluate_every=1` matters. scikit-learn's LDA only checks for convergence when
it evaluates perplexity, and by default it never does, so every fit runs to
`max_iter`. `sweep` would then flag every *k* as not settled, and the figures
would leave them all out.

## Example: a model from another library

Any object with `fit_transform` and `components_` works, so a model that
doesn't follow scikit-learn's interface needs only a thin wrapper:

```python
class MyModel:
    def __init__(self, k, seed):
        self.k, self.seed = k, seed

    def fit_transform(self, X):
        W, H = my_factorisation(X, self.k, self.seed)   # your code
        self.components_ = H                              # k x features
        return W                                          # samples x k

ss.sweep(base, k_range=range(2, 11), implementation=MyModel)
```

A class works directly as the factory, because `MyModel(k, seed)` returns an
unfitted model.

## Convergence of your model

How `sweep` judges a custom model:

- If fitting raises scikit-learn's `ConvergenceWarning`, the fit is flagged
  as not settled.
- If the model has an `n_iter_` attribute after fitting, a fit that used all of
  `max_iter` is flagged as not settled. If you set `n_iter_` in your own
  wrapper, set `max_iter` too.

Whether these signals are enough for your model is up to you. A flagged *k*
stays on disk and in the consensus, but the figures leave it out unless you
pass `exclude_unsettled=False`. See
[How to fit models](fit_models.md#did-each-fit-converge).

## Functions defined in a notebook

The fits run in separate worker processes, and `sweep` sends your function to
them by value (with [cloudpickle](https://github.com/cloudpipe/cloudpickle)).
A `def` in a notebook cell, a lambda or a closure all work. Anything the
function refers to has to be picklable, so open files, database connections or
locks must be created *inside* the function, not outside it.

## Models in other languages

If your model runs in R or another language, fit the sweep there, save each
`W` as `base/results/W/W_{k}.csv`, and call `ss.sweep(base)` with no `k_range`.
[How to apply StripeSankey to ADMIXTURE/STRUCTURE](admixture_structure.md)
walks through this.
