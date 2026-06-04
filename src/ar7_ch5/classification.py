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

import numpy as np
import pandas as pd

# Temperature variable names in the SCI xlsx (Climate Assessment namespace).
TEMP_MEDIAN = "Climate Assessment|Surface Temperature (GSAT)|Median [MAGICCv7.5.3]"
TEMP_P33 = "Climate Assessment|Surface Temperature (GSAT)|33rd Percentile [MAGICCv7.5.3]"
TEMP_P67 = "Climate Assessment|Surface Temperature (GSAT)|67th Percentile [MAGICCv7.5.3]"

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

    Returns
    -------
    ``(main_category, subcategory)`` tuple, e.g. ``("GW2", "GW2a")``.
    """
    if pd.isna(pw50):
        return ("unclassified", "unclassified")

    # GW0: PW50 < 1.5
    if pw50 < 1.5:
        return ("GW0", "GW0")

    # GW1: PW50 < 1.6 (still GW1 even if EoCW not quite < 1.5)
    if pw50 < 1.6:
        return ("GW1", "GW1")

    # GW2: PW50 < 1.7
    if pw50 < 1.7:
        if pd.notna(eocw50) and eocw50 < 1.5:
            return ("GW2", "GW2a")
        return ("GW2", "GW2b")

    # GW3: PW67 < 2.0 ("likely below 2C")
    if pd.notna(pw67) and pw67 < 2.0:
        if pd.notna(eocw50) and eocw50 < 1.5:
            return ("GW3", "GW3a")
        return ("GW3", "GW3b")

    # GW4: PW50 < 2.0
    if pw50 < 2.0:
        if pd.notna(eocw50) and eocw50 < 1.7:
            return ("GW4", "GW4-I")
        return ("GW4", "GW4-II")

    # GW5: PW50 < 2.5
    if pw50 < 2.5:
        dec_label = "DEC" if declining else "Non-DEC"
        return ("GW5", f"GW5-{dec_label}")

    # GW6: PW50 < 3.0
    if pw50 < 3.0:
        return ("GW6", "GW6")

    # GW7: PW50 < 3.5
    if pw50 < 3.5:
        return ("GW7", "GW7")

    # GW8: PW50 >= 3.5
    return ("GW8", "GW8")


def classify_from_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
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
    cats: list[str] = []
    subcats: list[str] = []
    for _, row in out.iterrows():
        cat, sub = classify_single(
            row["peak_warming_50"],
            row["eoc_warming_50"],
            row["peak_warming_67"],
            row["eoc_warming_67"],
            row["declining"],
        )
        cats.append(cat)
        subcats.append(sub)
    out["category"] = cats
    out["subcategory"] = subcats
    return out


def classify_warming(df: pd.DataFrame) -> pd.DataFrame:
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

        cat, subcat = classify_single(pw50, eocw50, pw67, eocw67, dec)

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


# Colour palette for GW categories (consistent plotting).
GW_COLORS = {
    "GW0": "#1a237e",
    "GW1": "#1565c0",
    "GW2": "#2196f3",
    "GW2a": "#64b5f6",
    "GW2b": "#90caf9",
    "GW3": "#26a69a",
    "GW3a": "#4db6ac",
    "GW3b": "#80cbc4",
    "GW4": "#fdd835",
    "GW5": "#ff9800",
    "GW6": "#f4511e",
    "GW7": "#c62828",
    "GW8": "#4a148c",
    "unclassified": "#9e9e9e",
}

GW_ORDER = ["GW0", "GW1", "GW2", "GW3", "GW4", "GW5", "GW6", "GW7", "GW8", "unclassified"]

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
