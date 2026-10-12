"""
Probabilistic Consensus Clustering (Lourenco, Rota Bulo, Rebagliati, Fred,
Figueiredo & Pelillo, *Machine Learning* 98:331-357, 2013).

The EAC family (Fred & Jain 2005) summarises a clustering ensemble as a
co-association matrix and then hands it to a generic pairwise clustering
algorithm. The 2013 paper's objection is that this throws away the *statistical
interpretation* of those numbers: they are counts of Bernoulli events, not
arbitrary similarities. Its model instead says

    y_i in simplex_K            soft membership of sample i over K clusters
    P[i and j co-clustered]  =  y_i . y_j
    C_ij ~ Binomial(N_ij, y_i . y_j)

and estimates ``Y`` by maximum likelihood. Two consequences matter here:

* ``K`` is an **upper bound**, not a target. Unused clusters converge to zero
  mass, so the method does its own model selection.
* the output is **soft**, so a sample sitting at ``[0.3, 0.7]`` stays that way
  instead of being forced into one side.

Generalised (paper's Sect. 4) to any double-convex Bregman divergence::

    f(Y) = sum_{i<j} N_ij * d_phi( C_ij / N_ij ,  y_i . y_j )

``phi = -H`` recovers the KL / maximum-likelihood form; ``phi = ||.||^2`` gives a
weighted least squares fit, which has a closed-form step size. The ``N_ij``
weight is the point of the parametrisation: under sub-sampling a pair observed
45 times is better evidence than one observed 18 times, and plain EAC — which
stores only the fraction ``C_ij / N_ij`` — cannot tell them apart.

Optimiser: the paper's greedy coordinate descent on the simplex (Sect. 5). Each
step moves mass for a single sample from one cluster to another, along the
steepest feasible descent direction, with an exact line search. ``Y^T Y`` and the
gradient are maintained incrementally so an iteration costs O(nK) rather than
O(n^2 K).

An addition that is **not** in the paper is available via ``e_k``: neither Fred &
Jain nor Lourenco et al. correct for the fact that a coarse partition co-clusters
everything by chance. Passing the per-layer chance levels models the observed
co-clustering probability as ``e_k + (1 - e_k) * y_i . y_j`` instead, i.e. the
inverse of the debiasing already used elsewhere in this project.
"""
import numpy as np


def observed_from_soft(usage_matrices, weights=None):
    """Co-association frequency + weights from *soft* per-k usage matrices.

    Returns ``(O, W, e_k)`` where ``O[i,j]`` is the weighted mean of the per-k
    soft co-membership ``B_k = P_k P_k^T`` (so it lies in [0, 1] and is a
    legitimate Bernoulli rate), ``W`` is the per-pair weight matrix (constant
    here — every pair is observed at every k), and ``e_k`` the per-layer chance
    levels for the optional debiased variant.

    Hardening the usage to argmax labels first, as the papers assume, would
    discard exactly the mixture information LDA/NMF exists to produce.
    """
    ks = sorted(usage_matrices)
    P_list, e_k = [], []
    for k in ks:
        P = np.asarray(usage_matrices[k], dtype=np.float64)
        P = np.clip(P, 0, None)
        P = P / np.clip(P.sum(axis=1, keepdims=True), 1e-12, None)
        P_list.append(P)
        e_k.append(float((P.mean(axis=0) ** 2).sum()))
    e_k = np.array(e_k)
    w = np.ones(len(ks)) if weights is None else np.asarray(weights, dtype=float)
    w = w / w.sum()
    n = P_list[0].shape[0]
    O = np.zeros((n, n))
    for wi, P in zip(w, P_list):
        O += wi * (P @ P.T)
    O = (O + O.T) / 2.0
    np.clip(O, 0.0, 1.0, out=O)
    return O, np.full((n, n), float(len(ks))), e_k


def observed_from_hard(labels_by_layer, layer_weights="one_minus_e"):
    """Co-association from *hard* labels: the literal EAC input.

    ``labels_by_layer`` is an iterable of label vectors (``-1``/NaN allowed as
    ordinary categories). Returns ``(O, W, e_k)``: ``O`` is the co-association
    rate, ``W[i,j]`` the number of layers in which both i and j were present —
    the ``N_ij`` of Lourenco et al. — and ``e_k`` the per-layer chance levels.

    ``layer_weights``:
      * ``None`` — the plain EAC / PCC observation, every layer equal.
      * ``"one_minus_e"`` (default) — each layer weighted by ``1 - e_k``, so a
        coarse partition, which co-clusters most pairs by chance, does not drown
        out a fine one.

    **Why weight rather than subtract.** ``e_k = sum_t p_t^2`` is by definition
    the probability that two random samples share a cluster at that layer, so
    ``mean(B_k) == e_k`` is an identity. Subtracting it — the debiasing used on
    the CPM side of this project — therefore forces the *average* excess
    co-clustering to zero, and since ``y_i . y_j >= 0`` averages to ``1/C`` for C
    equal clusters, a debiased PCC can only satisfy that with ``C -> infinity``.
    It saturates ``K`` instead of converging. Re-weighting corrects the same
    imbalance while keeping ``O`` a genuine rate in [0, 1], which is what the
    Binomial model requires.
    """
    L = [np.asarray(v) for v in labels_by_layer]
    n = len(L[0])
    N = np.zeros((n, n))
    rates, e_k = [], []
    for v in L:
        present = np.array([x is not None and x == x for x in v])   # not NaN
        idx = np.flatnonzero(present)
        N[np.ix_(idx, idx)] += 1
        _B = np.zeros((n, n))
        _B[np.ix_(idx, idx)] = (v[idx][:, None] == v[idx][None, :])
        rates.append(_B)
        _, counts = np.unique(v[idx], return_counts=True)
        p = counts / counts.sum()
        e_k.append(float((p ** 2).sum()))
    e_k = np.array(e_k)

    if layer_weights is None:
        w = np.ones(len(L))
    elif layer_weights == "one_minus_e":
        w = 1.0 - e_k
    else:
        w = np.asarray(layer_weights, dtype=float)
    w = w / w.sum()

    O = np.zeros((n, n))
    for wi, B in zip(w, rates):
        O += wi * B
    O = (O + O.T) / 2.0
    np.clip(O, 0.0, 1.0, out=O)
    return O, N, e_k


def pcc(O, W, K=20, e_k=None, max_iter=None, tol=1e-10, random_state=0,
        init_noise=1e-3, verbose=False):
    """Fit probabilistic consensus assignments by weighted least squares.

    This is the ``phi = ||.||^2`` member of the paper's Bregman family::

        min_Y  sum_{i<j} W_ij ( O_ij - y_i . y_j )^2

    which the paper reports as PCC-l2. It is used here rather than PCC-KL
    because the line search has a closed form, and the paper finds the two
    perform comparably.

    Args:
        O: (n, n) observed co-association rate in [0, 1], zero diagonal ignored.
        W: (n, n) per-pair weight — ``N_ij``, the number of times the pair was
            actually observed. This is what plain EAC discards.
        K: maximum number of clusters. Not a target: unused columns decay to
            zero mass, so set it comfortably above any plausible answer.
        e_k: optional per-layer chance levels. When given, the model becomes
            ``O_ij ~ mean_k[e_k] + (1 - mean_k[e_k]) * y_i . y_j``, i.e. the
            debiasing this project applies elsewhere, folded into the fit.
            NOT part of the original paper.
        max_iter: default ``30 * n``; the paper notes ~Omega(nK) steps are needed
            since every entry of Y must move at least once.
        tol: stop when the best available descent is smaller than this.
        init_noise: symmetry-breaking jitter on the uniform start. With an
            exactly uniform Y every sample is identical and every direction ties.

    Returns:
        dict with ``Y`` (K, n) column-stochastic, ``labels`` (argmax), ``n_iter``,
        ``objective`` history, and ``used`` (clusters holding real mass).
    """
    O = np.asarray(O, dtype=np.float64)
    W = np.asarray(W, dtype=np.float64).copy()
    n = O.shape[0]
    np.fill_diagonal(W, 0.0)              # the objective runs over distinct pairs

    # affine rescaling for the debiased variant: O = a + b * (y.y)
    if e_k is None:
        a, b = 0.0, 1.0
    else:
        a = float(np.mean(e_k))
        b = 1.0 - a

    rng = np.random.default_rng(random_state)
    Y = np.full((K, n), 1.0 / K) + init_noise * rng.random((K, n))
    Y /= Y.sum(axis=0, keepdims=True)

    A = Y.T @ Y                            # (n, n) current y_i . y_j
    R = O - (a + b * A)                    # residual
    WR = W * R
    G = -2.0 * b * (Y @ WR)                # (K, n) gradient wrt each y_j

    obj = [float((W * R * R).sum() / 2.0)]
    max_iter = int(30 * n) if max_iter is None else int(max_iter)

    for it in range(max_iter):
        # steepest feasible direction: for each j, move mass from the worst
        # supported cluster V to the best cluster U
        U = G.argmin(axis=0)
        Gsup = np.where(Y > 1e-12, G, -np.inf)
        V = Gsup.argmax(axis=0)
        gain = G[U, np.arange(n)] - Gsup[V, np.arange(n)]
        J = int(gain.argmin())
        if not np.isfinite(gain[J]) or gain[J] > -tol:
            break
        u, v = int(U[J]), int(V[J])

        # exact line search: f(eps) is quadratic in eps for phi = ||.||^2
        delta = Y[u] - Y[v]                                  # (n,) = y_i . d
        delta[J] = 0.0
        wj = W[J]
        num = float((wj * delta * R[J]).sum())
        den = float(b * (wj * delta * delta).sum())
        if den <= 0:
            break
        eps = num / den
        eps = float(np.clip(eps, 0.0, Y[v, J]))
        if eps <= 0:
            break

        # incremental updates: only column/row J of A and R move
        Y[u, J] += eps
        Y[v, J] -= eps
        A[J, :] += eps * delta
        A[:, J] += eps * delta
        A[J, J] = float(Y[:, J] @ Y[:, J])
        R[J, :] = O[J, :] - (a + b * A[J, :])
        R[:, J] = R[J, :]
        WR[J, :] = W[J, :] * R[J, :]
        WR[:, J] = WR[J, :]
        G = -2.0 * b * (Y @ WR)

        obj.append(float((W * R * R).sum() / 2.0))
        if verbose and it % 500 == 0:
            print(f"  iter {it:>6}  objective {obj[-1]:.6f}  "
                  f"clusters in use {(Y.max(axis=1) > 1e-6).sum()}")

    # Which of the K slots a cluster ends up in is an artefact of the
    # optimisation path -- with K an upper bound the survivors are scattered
    # (e.g. {0, 1, 4, 5, 14}), so raw argmax indices would name clusters "C14".
    # Reorder the rows of Y by cluster size, biggest first, so the labels read
    # 0, 1, 2, ... and match the convention on the CPM side
    # (mr_consensus._renumber_by_size). Y keeps its (K, n) shape: the empty rows
    # move to the bottom rather than being dropped, since "K is an upper bound
    # and most of it went unused" is part of the result.
    _raw = Y.argmax(axis=0)
    _sizes = np.bincount(_raw, minlength=K)
    _order = np.argsort(-_sizes, kind="stable")
    Y = Y[_order]
    _inv = np.empty(K, dtype=int)
    _inv[_order] = np.arange(K)
    labels = _inv[_raw]

    return {"Y": Y, "labels": labels, "n_iter": len(obj) - 1,
            "objective": np.array(obj),
            # rows holding any mass at all vs. rows that actually win a sample:
            # a slot can carry a sliver of probability and never be anyone's best
            "used": int((Y.max(axis=1) > 1e-6).sum()),
            "n_clusters": int(len(np.unique(labels)))}
