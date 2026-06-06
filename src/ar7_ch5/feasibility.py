"""Feasibility, plausibility, and sustainability checks (Table SI.2).

Ported from scenariocompass ``src/feasibility.py`` (Riahi et al. 2026 SI).
Each criterion returns a concern level: ``"none"``, ``"medium"``, ``"major"``,
or ``"not_reported"``.

Inputs are the wide IAMC frame returned by
:func:`ar7_ch5.load.load_sci_iamc_global` (Title-case meta columns and
string year headers).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Feasibility criteria (Table SI.2)
# Format: variable, year, upper_major, upper_medium, lower_medium, lower_major
# None means no threshold on that side.
# ---------------------------------------------------------------------------

FEASIBILITY_CRITERIA: list[dict] = [
    # Hydropower capacity in 2030 (GW)
    {"variable": "Capacity|Electricity|Hydro",
     "year": "2030",
     "upper_major": 2118, "upper_medium": 1607,
     "lower_medium": 1175, "lower_major": 979},

    # Nuclear capacity in 2030 (GW)
    {"variable": "Capacity|Electricity|Nuclear",
     "year": "2030",
     "upper_major": 507, "upper_medium": 442,
     "lower_medium": 320, "lower_major": None},

    # Total wind capacity in 2030 (GW)
    {"variable": "Capacity|Electricity|Wind",
     "year": "2030",
     "upper_major": None, "upper_medium": None,
     "lower_medium": 1719, "lower_major": 1220},

    # Onshore wind capacity in 2030 (GW)
    {"variable": "Capacity|Electricity|Wind|Onshore",
     "year": "2030",
     "upper_major": 3655, "upper_medium": 2853,
     "lower_medium": 1719, "lower_major": 1220},

    # Solar capacity in 2030 (GW)
    {"variable": "Capacity|Electricity|Solar",
     "year": "2030",
     "upper_major": 10896, "upper_medium": 8164,
     "lower_medium": 4350, "lower_major": 2683},

    # Geological storage of CO2 in 2030 (Mt CO2/yr)
    {"variable": "Carbon Capture|Geological Storage",
     "year": "2030",
     "upper_major": 458, "upper_medium": 152,
     "lower_medium": 44, "lower_major": None},

    # Geological storage of CO2 in 2035 (Mt CO2/yr) - medium only
    {"variable": "Carbon Capture|Geological Storage",
     "year": "2035",
     "upper_major": None, "upper_medium": 1300,
     "lower_medium": None, "lower_major": None},

    # Geological storage of CO2 in 2040 (Mt CO2/yr) - medium only
    {"variable": "Carbon Capture|Geological Storage",
     "year": "2040",
     "upper_major": None, "upper_medium": 4300,
     "lower_medium": None, "lower_major": None},
]

# Alternative names for carbon capture (legacy reporting).
_CC_ALIASES = [
    "Carbon Capture|Geological Storage",
    "Carbon Capture|CCS",
    "Carbon Capture",
]


SUSTAINABILITY_CRITERIA: list[dict] = [
    # Prudent limit for geological carbon storage (cumulative Gt CO2 to 2100)
    {"variable": "cumulative_ccs",  # computed
     "upper_major": 1460, "upper_medium": 1290,
     "lower_medium": None, "lower_major": None,
     "unit": "Gt CO2"},

    # Bioenergy use (EJ/yr, max over pathway)
    {"variable": "Primary Energy|Biomass",
     "upper_major": 245, "upper_medium": 100,
     "lower_medium": None, "lower_major": None,
     "unit": "EJ/yr"},

    # Food availability (kcal/cap/day, any year)
    {"variable": "Food Availability [per capita]",
     "upper_major": None, "upper_medium": 5000,
     "lower_medium": 2100, "lower_major": None,
     "unit": "kcal/cap/day"},
]


def _get_concern_level(value: float, crit: dict) -> str:
    """Determine the concern level for a value given thresholds."""
    if pd.isna(value):
        return "not_reported"
    if crit.get("upper_major") is not None and value > crit["upper_major"]:
        return "major"
    if crit.get("upper_medium") is not None and value > crit["upper_medium"]:
        return "medium"
    if crit.get("lower_major") is not None and value < crit["lower_major"]:
        return "major"
    if crit.get("lower_medium") is not None and value < crit["lower_medium"]:
        return "medium"
    return "none"


def _get_scenario_value(sdf: pd.DataFrame, variable: str, year: str) -> float:
    """One numeric value for (scenario, variable, year), trying CC aliases."""
    candidates = [variable] + (_CC_ALIASES if "Carbon Capture" in variable else [])
    for var in candidates:
        rows = sdf.loc[sdf["Variable"] == var]
        if not rows.empty and year in rows.columns:
            val = pd.to_numeric(rows.iloc[0][year], errors="coerce")
            if not pd.isna(val):
                return val
    return np.nan


def apply_feasibility(df: pd.DataFrame) -> pd.DataFrame:
    """Assess feasibility concerns per scenario.

    Returns a DataFrame with ``Model, Scenario``, a column per criterion
    (named ``<variable>|<year>``), and a summary ``worst_feasibility`` column
    (``"none"``, ``"medium"``, or ``"major"``).
    """
    scenarios = df[["Model", "Scenario"]].drop_duplicates()
    results = []
    for _, row in scenarios.iterrows():
        model, scenario = row["Model"], row["Scenario"]
        sdf = df.loc[(df["Model"] == model) & (df["Scenario"] == scenario)]
        rec = {"Model": model, "Scenario": scenario}

        worst = "none"
        for crit in FEASIBILITY_CRITERIA:
            val = _get_scenario_value(sdf, crit["variable"], crit["year"])
            level = _get_concern_level(val, crit)
            rec[f"{crit['variable']}|{crit['year']}"] = level
            if level == "major":
                worst = "major"
            elif level == "medium" and worst != "major":
                worst = "medium"

        rec["worst_feasibility"] = worst
        results.append(rec)

    return pd.DataFrame(results)


def _cumulative_ccs(sdf: pd.DataFrame) -> float:
    """Cumulative geological CO2 storage 2020-2100 (Gt CO2; trapezoidal, 5y)."""
    year_cols = [str(y) for y in range(2020, 2105, 5)]
    for var in _CC_ALIASES:
        rows = sdf.loc[sdf["Variable"] == var]
        if not rows.empty:
            vals = pd.to_numeric(rows.iloc[0][year_cols], errors="coerce")
            if vals.notna().sum() >= 2:
                vals_gt = vals / 1000.0  # Mt -> Gt
                return np.trapezoid(vals_gt.values, dx=5)
    return np.nan


def apply_sustainability(df: pd.DataFrame) -> pd.DataFrame:
    """Assess sustainability concerns per scenario.

    Returns a DataFrame with ``Model, Scenario``, derived values
    (``cumulative_ccs_GtCO2``, ``max_bioenergy_EJ``), per-criterion concern
    levels, and a summary ``worst_sustainability`` column.
    """
    scenarios = df[["Model", "Scenario"]].drop_duplicates()
    year_cols = [str(y) for y in range(2020, 2105, 5)]
    results = []
    for _, row in scenarios.iterrows():
        model, scenario = row["Model"], row["Scenario"]
        sdf = df.loc[(df["Model"] == model) & (df["Scenario"] == scenario)]
        rec = {"Model": model, "Scenario": scenario}
        worst = "none"

        for crit in SUSTAINABILITY_CRITERIA:
            if crit["variable"] == "cumulative_ccs":
                val = _cumulative_ccs(sdf)
                level = _get_concern_level(val, crit)
                rec["cumulative_ccs_GtCO2"] = val
                rec["sustainability_ccs"] = level
            elif crit["variable"] == "Primary Energy|Biomass":
                rows = sdf.loc[sdf["Variable"] == crit["variable"]]
                if rows.empty:
                    level = "not_reported"
                    val = np.nan
                else:
                    vals = pd.to_numeric(rows.iloc[0][year_cols], errors="coerce")
                    val = vals.max()
                    level = _get_concern_level(val, crit)
                rec["max_bioenergy_EJ"] = val
                rec["sustainability_bioenergy"] = level
            elif crit["variable"] == "Food Availability [per capita]":
                rows = sdf.loc[sdf["Variable"] == crit["variable"]]
                if rows.empty:
                    level = "not_reported"
                else:
                    vals = pd.to_numeric(rows.iloc[0][year_cols], errors="coerce")
                    level = "none"
                    if crit.get("upper_medium") and (vals > crit["upper_medium"]).any():
                        level = "medium"
                    if crit.get("lower_medium") and (vals < crit["lower_medium"]).any():
                        level = "medium"
                rec["sustainability_food"] = level
            else:
                continue

            if level == "major":
                worst = "major"
            elif level == "medium" and worst != "major":
                worst = "medium"

        rec["worst_sustainability"] = worst
        results.append(rec)

    return pd.DataFrame(results)
