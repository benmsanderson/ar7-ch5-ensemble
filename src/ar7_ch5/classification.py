"""Warming categorisation for the SCI 2025 ensemble (Table SI.3).

Ported from scenariocompass ``src/classification.py`` (Riahi et al. 2026 SI).
Assigns each scenario to a Global Warming (GW) main category and subcategory
based on peak warming (PW) and end-of-century warming (EoCW) at the 50th and
67th percentiles.

This file is the **regression path**: percentiles come from the MAGICC v7.5.3
timeseries baked into the SCI xlsx (``Climate Assessment|Surface Temperature
(GSAT)|Median`` and ``|67th Percentile``). It exactly reproduces the
scenariocompass output and is what the port regression test pins against.

The chapter's emissions-based extension, where percentiles come from the
three-SCM ensemble we run here, lands in a follow-up commit on top of
:mod:`ar7_ch5.metrics`. The choice of pooled-vs-per-model percentiles is the
open science decision flagged in
``project_classification_warming_contract`` (see brief / memory).
"""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .runners import repo_root

# ---------------------------------------------------------------------------
# Declarative GW scheme (schemes/gw/<name>.json)
# ---------------------------------------------------------------------------

# Directory holding the warming-classification schemes; one JSON per variant.
GW_SCHEME_DIR = "schemes/gw"
DEFAULT_GW_SCHEME = "si3"

_OPS: dict[str, Any] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


def _condition_ok(cond: dict, metrics: dict[str, Any]) -> bool:
    """Evaluate a single ``{feature, op, threshold}`` condition.

    A missing / NaN feature value yields ``False`` (a NaN never satisfies a
    threshold), which reproduces the ``pd.notna(...) and ...`` guards of the
    original hand-written cascade.
    """
    val = metrics.get(cond["feature"])
    try:
        return bool(_OPS[cond["op"]](val, cond["threshold"]))
    except TypeError:
        return False


@dataclass(frozen=True)
class GwScheme:
    """A self-contained warming-classification scheme.

    Parsed from ``schemes/gw/<name>.json``.  The scheme owns everything a
    taxonomy needs: the ordered cascade of ``rules`` (each with optional
    ``subcategories``), the ``category_order`` for plotting / tallying, and
    the ``colors`` palette.  This lets alternative GW taxonomies be swapped
    in during the writing process without touching code.
    """

    name: str
    description: str
    metrics: tuple[str, ...]
    required: tuple[str, ...]
    default_category: str
    rules: tuple[dict, ...]
    category_order: tuple[str, ...]
    colors: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict) -> GwScheme:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            metrics=tuple(data.get("metrics", ())),
            required=tuple(data.get("required", ())),
            default_category=str(data.get("default_category", "unclassified")),
            rules=tuple(data.get("rules", ())),
            category_order=tuple(data.get("category_order", ())),
            colors=dict(data.get("colors", {})),
        )

    def classify(self, metrics: dict[str, Any]) -> tuple[str, str]:
        """Classify one pathway's warming metrics into ``(category, subcategory)``.

        ``metrics`` maps feature name → scalar (e.g. ``peak_warming_50``).
        Returns ``(default_category, default_category)`` when a required
        metric is missing / NaN or no rule matches.
        """
        for feat in self.required:
            val = metrics.get(feat)
            if val is None or (isinstance(val, float) and np.isnan(val)) or (
                np.ndim(val) == 0 and pd.isna(val)
            ):
                return (self.default_category, self.default_category)

        for rule in self.rules:
            if all(_condition_ok(c, metrics) for c in rule.get("conditions", [])):
                category = rule["category"]
                subs = rule.get("subcategories")
                if not subs:
                    return (category, category)
                for sub in subs:
                    if all(_condition_ok(c, metrics) for c in sub.get("conditions", [])):
                        return (category, sub["label"])
                return (category, category)

        return (self.default_category, self.default_category)


def _resolve_gw_scheme_path(name_or_path: str | Path) -> Path:
    """Resolve a scheme name (e.g. ``"si3"``) or explicit path to a JSON file."""
    p = Path(name_or_path)
    if p.suffix == ".json":
        return p if p.is_absolute() else repo_root() / p
    # Bare name → schemes/gw/<name>.json
    return repo_root() / GW_SCHEME_DIR / f"{p.name}.json"


def load_gw_scheme(name_or_path: str | Path = DEFAULT_GW_SCHEME) -> GwScheme:
    """Load a warming-classification scheme by name or path.

    ``name_or_path`` may be a bare scheme name resolved under
    ``schemes/gw/`` (e.g. ``"si3"``) or an explicit ``.json`` path.
    """
    path = _resolve_gw_scheme_path(name_or_path)
    if not path.is_file():
        raise FileNotFoundError(f"GW scheme not found: {path}")
    return GwScheme.from_dict(json.loads(path.read_text()))


# Default scheme, loaded once. ``GW_ORDER`` / ``GW_COLORS`` derive from it so
# existing imports keep working while remaining single-sourced in the JSON.
_DEFAULT_GW_SCHEME = load_gw_scheme(DEFAULT_GW_SCHEME)

# Temperature variable names in the SCI xlsx (Climate Assessment namespace).
_GSAT = "Climate Assessment|Surface Temperature (GSAT)"
TEMP_MEDIAN = f"{_GSAT}|Median [MAGICCv7.5.3]"
TEMP_P33 = f"{_GSAT}|33rd Percentile [MAGICCv7.5.3]"
TEMP_P67 = f"{_GSAT}|67th Percentile [MAGICCv7.5.3]"

YEAR_COLS = [str(y) for y in range(2010, 2105, 5)]


def _extract_temp_timeseries(sdf: pd.DataFrame, var: str) -> pd.Series:
    """Extract a temperature timeseries for a single scenario."""
    rows = sdf.loc[sdf["Variable"] == var]
    if rows.empty:
        return pd.Series(dtype=float)
    available = [c for c in YEAR_COLS if c in rows.columns]
    return pd.to_numeric(rows.iloc[0][available], errors="coerce")


def _peak_warming(ts: pd.Series) -> float:
    """Peak warming = maximum value in the timeseries."""
    if ts.empty or ts.isna().all():
        return np.nan
    return ts.max()


def _eoc_warming(ts: pd.Series) -> float:
    """End-of-century warming = value at 2100."""
    if "2100" in ts.index:
        return ts["2100"]
    return np.nan


def _is_declining(ts: pd.Series) -> bool | None:
    """Whether temperature is declining between 2090 and 2100."""
    if "2090" in ts.index and "2100" in ts.index:
        t90 = ts["2090"]
        t100 = ts["2100"]
        if pd.notna(t90) and pd.notna(t100):
            return t100 < t90
    return None


def classify_single(
    pw50: float,
    eocw50: float,
    pw67: float,
    eocw67: float,
    declining: bool | None,
    scheme: GwScheme | None = None,
) -> tuple[str, str]:
    """Classify a single scenario into GW main category and subcategory.

    Parameters
    ----------
    pw50, eocw50
        Peak warming and end-of-century warming at the 50th percentile (median).
    pw67, eocw67
        Same at the 67th percentile.
    declining
        Whether temperature is declining at end of century.
    scheme
        Warming scheme to apply (default: the canonical SI.3 scheme).

    Returns
    -------
    ``(main_category, subcategory)`` tuple, e.g. ``("GW2", "GW2a")``.
    """
    scheme = scheme or _DEFAULT_GW_SCHEME
    return scheme.classify(
        {
            "peak_warming_50": pw50,
            "eoc_warming_50": eocw50,
            "peak_warming_67": pw67,
            "eoc_warming_67": eocw67,
            "declining": declining,
        }
    )


def classify_from_metrics(
    metrics: pd.DataFrame, scheme: GwScheme | None = None
) -> pd.DataFrame:
    """Apply :func:`classify_single` to a pre-computed warming-metrics frame.

    The frame is the output of
    :func:`ar7_ch5.metrics.compute_warming_metrics` (or
    :func:`ar7_ch5.metrics.warming_metrics_from_outputs`): one row per scenario
    group with columns ``peak_warming_50``, ``peak_warming_67``,
    ``eoc_warming_50``, ``eoc_warming_67``, and ``declining``. This is the
    emissions-based path of the classification (driven by our 3-SCM ensemble),
    in contrast to :func:`classify_warming` which reads the MAGICC v7.5.3
    percentiles baked into the SCI xlsx.

    Returns the input frame plus ``category`` and ``subcategory`` columns.
    """
    required = {
        "peak_warming_50", "peak_warming_67",
        "eoc_warming_50", "eoc_warming_67",
        "declining",
    }
    missing = required - set(metrics.columns)
    if missing:
        raise KeyError(
            f"metrics frame missing required columns: {sorted(missing)}; "
            f"got {list(metrics.columns)}."
        )
    out = metrics.copy()
    scheme = scheme or _DEFAULT_GW_SCHEME
    cats: list[str] = []
    subcats: list[str] = []
    for _, row in out.iterrows():
        cat, sub = classify_single(
            row["peak_warming_50"],
            row["eoc_warming_50"],
            row["peak_warming_67"],
            row["eoc_warming_67"],
            row["declining"],
            scheme=scheme,
        )
        cats.append(cat)
        subcats.append(sub)
    out["category"] = cats
    out["subcategory"] = subcats
    return out


def classify_warming(
    df: pd.DataFrame, scheme: GwScheme | None = None
) -> pd.DataFrame:
    """Classify all scenarios in a global ensemble into GW warming categories.

    Reads the MAGICC v7.5.3 percentile timeseries baked into the SCI xlsx and
    applies :func:`classify_single` row-by-row.

    Parameters
    ----------
    df
        Wide IAMC frame from :func:`ar7_ch5.load.load_sci_iamc_global`.

    Returns
    -------
    DataFrame with columns: ``Model, Scenario, peak_warming_50, peak_warming_67,
    eoc_warming_50, eoc_warming_67, declining, category, subcategory``.
    """
    scenarios = df[["Model", "Scenario"]].drop_duplicates()
    scheme = scheme or _DEFAULT_GW_SCHEME
    results = []

    for _, row in scenarios.iterrows():
        model, scenario = row["Model"], row["Scenario"]
        sdf = df.loc[(df["Model"] == model) & (df["Scenario"] == scenario)]

        ts50 = _extract_temp_timeseries(sdf, TEMP_MEDIAN)
        ts67 = _extract_temp_timeseries(sdf, TEMP_P67)

        pw50 = _peak_warming(ts50)
        pw67 = _peak_warming(ts67)
        eocw50 = _eoc_warming(ts50)
        eocw67 = _eoc_warming(ts67)
        dec = _is_declining(ts50)

        cat, subcat = classify_single(pw50, eocw50, pw67, eocw67, dec, scheme=scheme)

        results.append({
            "Model": model,
            "Scenario": scenario,
            "peak_warming_50": pw50,
            "peak_warming_67": pw67,
            "eoc_warming_50": eocw50,
            "eoc_warming_67": eocw67,
            "declining": dec,
            "category": cat,
            "subcategory": subcat,
        })

    return pd.DataFrame(results)


# Colour palette and category order for GW categories, single-sourced from the
# default GW scheme (``schemes/gw/si3.json``) so a new taxonomy is self-contained.
GW_COLORS = dict(_DEFAULT_GW_SCHEME.colors)

GW_ORDER = list(_DEFAULT_GW_SCHEME.category_order)

# Per-scenario colours for ScenarioMIP CMIP7 (temperature-ordered, cool to warm).
# ssp2c sits between l (~1.9 K) and ml (~2.5 K) in end-of-century warming.
SMIP_COLORS = {
    "vl":    "#1d3d8a",  # deep blue     (~1.6 K, GW4)
    "ln":    "#3b7cc9",  # medium blue   (~1.7 K, GW4)
    "l":     "#6bb5e8",  # light blue    (~1.9 K, GW4)
    "ssp2c": "#8ecda0",  # sage green    (~2.2 K, GW5 between l and ml)
    "ml":    "#f5c242",  # golden amber  (~2.5 K, GW5)
    "hl":    "#e8852a",  # warm orange   (~3.0 K, GW6)
    "m":     "#d43820",  # tomato red    (~3.2 K, GW6)
    "h":     "#7a0c10",  # deep crimson  (~3.8 K, GW8)
}
