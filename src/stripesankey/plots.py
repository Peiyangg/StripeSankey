"""
The folder route: read a run from disk and draw it.

``api.stripesankey`` / ``api.metasankey`` take objects and know nothing about
folders. These two do the folder half -- read ``base_directory``, drop any k
whose fit did not settle, and hand the rest over. Everything about how the
figure looks is decided there, so the two routes cannot drift apart.
"""

from __future__ import annotations

import warnings
from typing import Iterable

import pandas as pd

from .api import metasankey, stripesankey
from .cache import _report_convergence, load_consensus, load_run_info, load_W

__all__ = ["sweep_figure", "load_sweep_figure_inputs"]


def load_sweep_figure_inputs(base_directory: str,
                             k_list: Iterable[int] | None = None,
                             *, exclude_unsettled: bool = True):
    """
    ``(W_by_k, clusters)`` from a finished run.

    Args:
        exclude_unsettled: drop k values with a fit that did not settle. On by
            default, and for the same reason the consensus refuses them: a
            column built from an unsettled fit is not a statement about the
            data. Pass ``False`` to look at one anyway.
    """
    info = load_run_info(base_directory)
    ks = sorted(int(k) for k in (k_list if k_list is not None else info["k_list"]))

    if exclude_unsettled:
        bad = set(_report_convergence(info, verbose=False))
        dropped = sorted(set(ks) & bad)
        ks = [k for k in ks if k not in bad]
        if dropped:
            warnings.warn(
                f"k={dropped} dropped: the fit did not settle. Pass "
                "exclude_unsettled=False to include them anyway.",
                stacklevel=2,
            )
        if not ks:
            raise ValueError(
                "every k has an unsettled fit; nothing left to draw. Raise "
                "`max_passes`, or pass exclude_unsettled=False to look anyway."
            )

    W_by_k = load_W(base_directory, ks)
    clusters = {str(s): int(c)
                for s, c in load_consensus(base_directory)["sample_to_cluster"].items()}
    return W_by_k, clusters


def sweep_figure(base_directory: str,
                 view: str = "stripesankey",
                 *,
                 k_list: Iterable[int] | None = None,
                 metadata_df: pd.DataFrame | None = None,
                 hover_field=None,
                 exclude_unsettled: bool = True,
                 **kwargs):
    """
    Read a run from ``base_directory`` and draw it.

    ``view='stripesankey'`` colours each census column by the consensus cluster;
    ``view='metasankey'`` colours it by the first ``hover_field``'s categories.
    Same layout, different cut. Every other keyword is passed through to
    :func:`~stripesankey.stripesankey` or :func:`~stripesankey.metasankey`, so
    the folder route and the object route take the same options.
    """
    if view not in ("stripesankey", "metasankey"):
        raise ValueError(f"view={view!r}: expected 'stripesankey' or 'metasankey'")
    W_by_k, clusters = load_sweep_figure_inputs(
        base_directory, k_list, exclude_unsettled=exclude_unsettled)
    fn = stripesankey if view == "stripesankey" else metasankey
    return fn(W_by_k, clusters=clusters, metadata_df=metadata_df,
              hover_field=hover_field, **kwargs)
