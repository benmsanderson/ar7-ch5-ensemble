"""Emissions-archetype strategy labelling.

Each pathway is mapped to a composite strategy label that is a **pure,
deterministic function** of the per-pathway features computed in
:mod:`ar7_ch5.archetype_features` and the thresholds declared in
``schemes/clustered.json``::

    cluster_label = f"{ce_bin}-{drawdown_band}-{suffix}"

* ``ce_bin``         threshold bucket of ``cum_co2_net_to_nz``
* ``drawdown_band``  precomputed per pathway (``pos`` / ``nz`` / ``over``)
* ``suffix``         composite of the ``suffix_rules`` (each a threshold
                     test on a single feature)

The exploratory k-means analysis that originally *chose* those thresholds
lives in the scenariocompass repository; here the archetype definitions are
simply stated declaratively, so labelling is fast, reproducible (no random
seed) and self-documenting.

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
        for t, lbl in zip(thresholds, labels):
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


def match_suffix(
    feature_values: dict[str, float],
    suffix_rules: dict[str, Any],
) -> str:
    """Return a composite suffix string for a single pathway.

    ``feature_values`` maps feature name → scalar value for one pathway.
    ``suffix_rules`` is the ``suffix_rules`` block from
    ``schemes/clustered.json``.

    Priority order is given by ``display_order``; each rule is included in
    the suffix if **all** its conditions are satisfied.  Returns ``"base"``
    if no rule fires.
    """
    display_order: list[str] = suffix_rules.get("display_order", [])
    rules: dict[str, dict] = suffix_rules.get("rules", {})
    active: list[str] = []
    for name in display_order:
        rule = rules.get(name)
        if rule is None:
            continue
        conditions = rule.get("conditions", [])
        if all(
            _OPS[cond["op"]](
                feature_values.get(cond["feature"], float("nan")), cond["threshold"]
            )
            for cond in conditions
        ):
            active.append(name)
    return "+".join(active) if active else "base"


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
      ``cluster_label``   Full composite label, e.g. ``CC1000-nz-cdr+ch4``
      ``centroid_*``      Group-mean feature values for the pathway's label

    The ``centroid_*`` columns give, for each pathway, the mean of every
    pathway sharing its ``cluster_label`` (computed over the combined
    SCI + ScenarioMIP set), providing a deterministic representative point.
    """
    ce_cfg = scheme["ce_bins"]
    cluster_features: list[str] = scheme["cluster_features"]
    suffix_rules = scheme["suffix_rules"]

    centroid_features = cluster_features + ["cum_co2_afolu"]

    combined = pd.concat([sci_features, smip_features], ignore_index=True)

    # --- CE bin (threshold bucket of cumulative net CO2) ---
    combined["ce_bin"] = assign_ce_bin(
        combined["cum_co2_net_to_nz"],
        ce_cfg["thresholds"],
        ce_cfg["labels"],
    )

    # --- Composite label, evaluated per pathway on its own features ---
    def _label(row: pd.Series) -> str:
        suffix = match_suffix(
            {f: row.get(f, float("nan")) for f in cluster_features}, suffix_rules
        )
        return f"{row['ce_bin']}-{row['drawdown_band']}-{suffix}"

    combined["cluster_label"] = combined.apply(_label, axis=1)

    # --- Deterministic centroids: group mean per label ---
    group_means = combined.groupby("cluster_label")[centroid_features].transform("mean")
    for f in centroid_features:
        combined[f"centroid_{f}"] = group_means[f]

    return combined
