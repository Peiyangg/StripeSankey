"""
Reading a finished run back.

Two matrices per k, named as the paper names them -- ``X ~ W . H``:

====  ==================  ==============================
name  shape               on disk
====  ==================  ==============================
W     ``sample x LC``     ``results/W/W_{k}.csv``
H     ``LC x feature``    ``results/H/H_{k}.csv``
====  ==================  ==============================

This is also sklearn's convention, so a sklearn-shaped backend maps straight
across. A column of ``W`` is a **latent component (LC)**: nothing in the name
is specific to microbes.
"""

from __future__ import annotations

import json
import os
import re
from typing import Iterable

import numpy as np
import pandas as pd

__all__ = ["load_W", "load_H", "load_run_info", "load_consensus",
           "load_topic_diff", "convergence_report", "unsettled_k"]


def load_W(base_directory: str,
           k_list: Iterable[int] | None = None) -> dict:
    """``{k: W}`` -- the sample x LC loading matrices, one fit per k.

    ``W`` and ``H`` follow the paper, which is also sklearn's convention:
    ``X ~ W . H`` with ``W`` the sample x LC loadings and ``H`` the
    LC x feature profiles.
    """
    ks = sorted(int(k) for k in (k_list if k_list is not None
                                 else load_run_info(base_directory)["k_list"]))
    out = {}
    for k in ks:
        path = os.path.join(base_directory, "results", "W", f"W_{k}.csv")
        if os.path.exists(path):
            out[k] = pd.read_csv(path, index_col=0)
    if not out:
        raise FileNotFoundError(
            f"no W tables in {base_directory}/results/W -- run sweep() first")
    return out


def _ks_on_disk(base_directory: str) -> list[int]:
    """The k values with a ``results/W/W_{k}.csv``, whoever wrote it."""
    wdir = os.path.join(base_directory, "results", "W")
    if not os.path.isdir(wdir):
        return []
    found = (re.fullmatch(r"W_(\d+)\.csv", name) for name in os.listdir(wdir))
    return sorted(int(m.group(1)) for m in found if m)


def load_run_info(base_directory: str) -> dict:
    with open(os.path.join(base_directory, "results", "run_info.json")) as f:
        return json.load(f)


def load_consensus(base_directory: str) -> dict:
    with open(os.path.join(base_directory, "results", "consensus.json")) as f:
        return json.load(f)


def load_H(base_directory: str, k: int) -> pd.DataFrame:
    """``H`` -- the LC x feature profile matrix at this k."""
    return pd.read_csv(
        os.path.join(base_directory, "results", "H", f"H_{k}.csv"),
        index_col=0)


def _report_convergence(run_info: dict, *, verbose: bool = True) -> list[int]:
    """
    Print the per-k convergence verdict and return the k values that failed.

    Nothing is refused here. A k that did not settle stays on disk, because
    throwing away the k values that *did* settle -- along with the time they
    cost -- is worse than carrying a flagged one. The consensus pools every k
    as it is; the figures leave a flagged k out unless told not to
    (``exclude_unsettled``). The built-in budgets are set high enough that a
    flagged k should be rare.
    """
    conv = run_info.get("convergence", {})
    rows, bad = [], []
    for k, d in sorted(conv.items(), key=lambda kv: int(kv[0])):
        ok = d.get("converged")
        rows.append((int(k), d, ok))
        if ok is False:
            bad.append(int(k))

    # The two backends report convergence through different quantities, so the
    # table shows whichever ones exist rather than a column of dashes.
    gensim_style = any("passes_run" in d for _k, d, _ok in rows)

    if verbose and rows:
        params = run_info.get("params", {})
        if gensim_style:
            print(f"\n[sweep] convergence (rel_tol={params.get('rel_tol')}, "
                  f"max_passes={params.get('max_passes')}):")
            print(f"  {'k':>4} {'passes':>7} {'docs_conv':>10} {'diff_ratio':>11}  verdict")
            for k, d, ok in rows:
                pr, fr = d.get("passes_run"), d.get("docs_converged_frac")
                ra = d.get("topic_diff_ratio")
                print(f"  {k:>4} {('-' if pr is None else pr):>7} "
                      f"{('-' if fr is None else f'{fr:.3f}'):>10} "
                      f"{('-' if ra is None else f'{ra:.2e}'):>11}  "
                      f"{'settled' if ok else 'NOT settled'}")
        else:
            print("\n[sweep] convergence (the estimator's own criterion):")
            print(f"  {'k':>4} {'n_iter':>7} {'max_iter':>9} {'loss':>12}  verdict")
            for k, d, ok in rows:
                ni, mi = d.get("n_iter"), d.get("max_iter")
                err = d.get("reconstruction_err")
                print(f"  {k:>4} {('-' if ni is None else ni):>7} "
                      f"{('-' if mi is None else mi):>9} "
                      f"{('-' if err is None else f'{err:.2f}'):>12}  "
                      f"{'settled' if ok else 'NOT settled'}")
    if bad and verbose:
        print(f"\n[sweep] WARNING: k={bad} did not settle within the fitting "
              f"budget. They are on disk, flagged in "
              f"run_info.json['convergence'] and included in the consensus; "
              f"the figures leave them out unless exclude_unsettled=False.")
    return bad


def unsettled_k(base_directory: str) -> list[int]:
    """The k values with at least one run that did not settle."""
    return _report_convergence(load_run_info(base_directory), verbose=False)


def load_topic_diff(base_directory: str, k: int) -> pd.Series:
    """gensim's own ``topic diff`` per pass, for this k's fit.

    The shape of it is the argument against an absolute convergence tolerance:
    it decays as a power law, so it keeps falling and never plateaus. Where the
    series ends is where the pass loop stopped.
    """
    return pd.read_csv(
        os.path.join(base_directory, "results", "diagnostics", f"topic_diff_{k}.csv"),
        index_col=0).squeeze("columns")


def convergence_report(base_directory: str) -> pd.DataFrame:
    """
    One row per k: did the fit settle, and was each ceiling enough?

    The two columns answer two different questions about two different limits:

    ``docs_converged``
        Fraction of documents whose inner E-step reached ``gamma_threshold``
        before hitting the ``iterations`` cap. Low means **`iterations`** is
        too small. It separates cleanly -- 0.54 at 400, 0.95-0.99 at 5000 on
        real tables -- so it is easy to read.
    ``passes``
        How many passes the fit needed. **This is the informative column.** At
        the ceiling (``max_passes``) the fit ran out of budget; well below it,
        the fit settled on its own and the number is what this data costs --
        measured 60-332 on one real table, 43-53 on another.
    ``diff_ratio``
        How much the topics moved on the final pass as a fraction of the
        largest move the fit ever made. Note this is also the **stopping
        condition**, so for a fit that settled it sits just under ``rel_tol``
        by construction and carries no extra information; it is only worth
        reading when ``settled`` is False, where it says how far short the fit
        fell. (It is a ratio, not a raw value, because the raw number is a mean
        absolute change in ``Elogbeta``, whose size depends on the vocabulary
        and so does not compare between datasets.)
    """
    info = load_run_info(base_directory)
    params = info.get("params", {})
    rows = []
    for k, d in sorted(info.get("convergence", {}).items(), key=lambda kv: int(kv[0])):
        rows.append({
            "k": int(k),
            "settled": d.get("converged"),
            # gensim's route
            "passes": d.get("passes_run"),
            "docs_converged": d.get("docs_converged_frac"),
            "diff_ratio": d.get("topic_diff_ratio"),
            # an sklearn estimator's own route
            "n_iter": d.get("n_iter"),
            "max_iter": d.get("max_iter"),
            "loss": d.get("reconstruction_err"),
            "seconds": d.get("seconds"),
        })
    # Only one backend's columns are ever populated; dropping the empty ones
    # keeps the table from being half dashes.
    out = pd.DataFrame(rows).dropna(axis=1, how="all")
    out.attrs["rel_tol"] = params.get("rel_tol")
    out.attrs["max_passes"] = params.get("max_passes")
    return out
