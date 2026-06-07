"""Emissions-archetype strategy labelling.

Each pathway is mapped to a composite strategy label that is a **pure,
deterministic function** of the per-pathway features computed in
:mod:`ar7_ch5.archetype_features` and the thresholds declared in
``schemes/clustered.json``::

    cluster_label = f"{ce_bin}-{drawdown_band}-{suffix}"

* ``ce_bin``         threshold bucket of ``cum_co2_net_to_nz``
* ``drawdown_band``  precomputed per pathway (``pos`` / ``nz`` / ``over``)
* ``suffix``         the pathway's dominant strategy, picked by a priority
                     cascade over the ``suffix_rules`` (each a threshold
                     test on a single feature)

The resulting list is kept short and communicable by two declarative knobs
in ``schemes/clustered.json`` — ``suffix_rules.mode`` (``"dominant"`` =
one strategy per pathway) and ``min_cluster_size`` (an occupancy floor that
folds rare archetypes into their cell's residual ``base`` label).  No
clustering / random seed is involved, so the count is tuned entirely from
JSON.  The exploratory k-means analysis that originally *chose* these
thresholds lives in the scenariocompass repository.

Public API
----------
``assign_ce_bin``    Vectorised CE-bin label assignment.
``match_suffix``     Per-pathway feature dict → strategy suffix string.
``fit_clusters``     Apply the declarative scheme → labelled DataFrame.
"""

from __future__ import annotations

import operator
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CE-bin assignment
# ---------------------------------------------------------------------------


def assign_ce_bin(
    values: pd.Series | np.ndarray,
    thresholds: list[float],
    labels: list[str],
) -> np.ndarray:
    """Map ``cum_co2_net_to_nz`` values to CE-bin label strings.

    Parameters
    ----------
    values
        1-D array of cumulative net CO2 values (Gt CO2).
    thresholds
        Ascending list of bin edges, e.g. ``[1000, 1500, 3000]``.
    labels
        One more label than thresholds; ``labels[0]`` is applied when
        ``value < thresholds[0]``, the last label when ``value >=
        thresholds[-1]``.
    """
    arr = np.asarray(values, dtype=float)
    out = np.empty(len(arr), dtype=object)
    thresholds = sorted(thresholds)
    for i, val in enumerate(arr):
        assigned = False
        for t, lbl in zip(thresholds, labels, strict=False):
            if val < t:
                out[i] = lbl
                assigned = True
                break
        if not assigned:
            out[i] = labels[-1]
    return out


# ---------------------------------------------------------------------------
# Suffix labelling
# ---------------------------------------------------------------------------

_OPS: dict[str, Any] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


def _rule_fires(rule: dict, feature_values: dict[str, float]) -> bool:
    """True if every condition of ``rule`` holds for ``feature_values``."""
    return all(
        _OPS[cond["op"]](
            feature_values.get(cond["feature"], float("nan")), cond["threshold"]
        )
        for cond in rule.get("conditions", [])
    )


def match_suffix(
    feature_values: dict[str, float],
    suffix_rules: dict[str, Any],
) -> str:
    """Return the strategy suffix string for a single pathway.

    ``feature_values`` maps feature name → scalar value for one pathway.
    ``suffix_rules`` is the ``suffix_rules`` block from
    ``schemes/clustered.json``.  All behaviour is declared in that block:

    ``mode``
        ``"dominant"`` (default) returns the single highest-priority flag
        that fires — yielding one strategy per pathway, which is far easier
        to communicate.  ``"additive"`` returns every firing flag joined by
        ``"+"`` (the historical behaviour).
    ``display_order``
        Priority order of the rules.  In ``"dominant"`` mode the first
        firing rule wins; in ``"additive"`` mode it sets the join order.
    ``merge``
        Optional ``{flag: family}`` map applied after a flag is selected,
        collapsing related strategies (e.g. ``deepcdr`` → ``cdr``).
    ``residual_label``
        Returned when no rule fires (default ``"base"``).

    Each rule fires when **all** its conditions are satisfied; a ``NaN``
    feature never satisfies a threshold.
    """
    display_order: list[str] = suffix_rules.get("display_order", [])
    rules: dict[str, dict] = suffix_rules.get("rules", {})
    merge: dict[str, str] = suffix_rules.get("merge", {})
    residual: str = suffix_rules.get("residual_label", "base")
    mode: str = suffix_rules.get("mode", "additive")

    active: list[str] = [
        name
        for name in display_order
        if name in rules and _rule_fires(rules[name], feature_values)
    ]
    if not active:
        return residual

    if mode == "dominant":
        return merge.get(active[0], active[0])

    # additive: collapse via merge map, de-duplicate while preserving order
    merged: list[str] = []
    for name in active:
        fam = merge.get(name, name)
        if fam not in merged:
            merged.append(fam)
    return "+".join(merged)


# ---------------------------------------------------------------------------
# Full labelling pipeline
# ---------------------------------------------------------------------------

# Features evaluated by the suffix rules / reported as cluster centroids.
CLUSTER_FEATURES = [
    "cum_co2_eip",
    "cdr_fraction",
    "ch4_reduction",
    "so2_2050_rel",
    "eip_2050_rel",
    "eip_2100_rel",
]


def fit_clusters(
    sci_features: pd.DataFrame,
    smip_features: pd.DataFrame,
    scheme: dict,
) -> pd.DataFrame:
    """Apply the declarative archetype scheme to every pathway.

    Parameters
    ----------
    sci_features, smip_features
        DataFrames produced by :mod:`ar7_ch5.archetype_features`; must have
        columns ``[Model, Scenario, source, cum_co2_eip, cdr_fraction,
        ch4_reduction, so2_2050_rel, eip_2050_rel, eip_2100_rel,
        cum_co2_afolu, cum_co2_net_to_nz, drawdown_band]``.
    scheme
        Parsed ``schemes/clustered.json`` dict.

    Returns
    -------
    DataFrame with all input columns plus:
      ``ce_bin``          CE-bin label (CC1000 / CC1500 / CC3000 / CC3000+)
      ``cluster_label``   Full composite label, e.g. ``CC1000-nz-cdr``
      ``centroid_*``      Group-mean feature values for the pathway's label

    The ``centroid_*`` columns give, for each pathway, the mean of every
    pathway sharing its ``cluster_label`` (computed over the combined
    SCI + ScenarioMIP set), providing a deterministic representative point.

    Two declarative knobs in ``scheme`` shape the resulting list so it stays
    short and communicable, with no clustering step:

    * ``suffix_rules.mode`` — ``"dominant"`` gives one strategy per pathway
      (see :func:`match_suffix`).
    * ``min_cluster_size`` — occupancy floor.  Any archetype with fewer than
      this many pathways has its strategy folded into the cell residual
      (``suffix_rules.residual_label``), so rare niche labels disappear into
      the "base" archetype of their (CE-bin, drawdown) cell.  Set to ``0`` /
      omit to keep every label.
    """
    ce_cfg = scheme["ce_bins"]
    cluster_features: list[str] = scheme["cluster_features"]
    suffix_rules = scheme["suffix_rules"]
    min_cluster_size = int(scheme.get("min_cluster_size", 0) or 0)
    residual_label = suffix_rules.get("residual_label", "base")

    centroid_features = cluster_features + ["cum_co2_afolu"]

    combined = pd.concat([sci_features, smip_features], ignore_index=True)

    # --- CE bin (threshold bucket of cumulative net CO2) ---
    combined["ce_bin"] = assign_ce_bin(
        combined["cum_co2_net_to_nz"],
        ce_cfg["thresholds"],
        ce_cfg["labels"],
    )

    # --- Composite label, evaluated per pathway on its own features ---
    def _suffix(row: pd.Series) -> str:
        return match_suffix(
            {f: row.get(f, float("nan")) for f in cluster_features}, suffix_rules
        )

    combined["_cell"] = (
        combined["ce_bin"].astype(str) + "-" + combined["drawdown_band"].astype(str)
    )
    combined["_suffix"] = combined.apply(_suffix, axis=1)
    combined["cluster_label"] = combined["_cell"] + "-" + combined["_suffix"]

    # --- Occupancy floor: fold rare strategies into the cell residual ---
    if min_cluster_size > 1:
        counts = combined["cluster_label"].value_counts()
        rare = set(counts[counts < min_cluster_size].index)
        is_rare = combined["cluster_label"].isin(rare) & (
            combined["_suffix"] != residual_label
        )
        combined.loc[is_rare, "cluster_label"] = (
            combined.loc[is_rare, "_cell"] + "-" + residual_label
        )

    combined = combined.drop(columns=["_cell", "_suffix"])

    # --- Deterministic centroids: group mean per label ---
    group_means = combined.groupby("cluster_label")[centroid_features].transform("mean")
    for f in centroid_features:
        combined[f"centroid_{f}"] = group_means[f]

    return combined
