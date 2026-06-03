"""Basic vetting of the SCI 2025 ensemble (Table SI.1).

Ported from scenariocompass ``src/vetting.py`` (Riahi et al. 2026 SI). Checks
each scenario against global reference values for CO2 emissions from energy
and industrial processes, final energy, and primary energy by fuel for
2010-2025.

A scenario PASSES if all checked values fall within the tolerance range.
FAILS if any value falls outside the range.
INSUFFICIENT_REPORTING if any required variable is missing.

Inputs are the wide IAMC frame returned by
:func:`ar7_ch5.load.load_sci_iamc_global` (Title-case meta columns and
string year headers).
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Reference values and tolerances (Table SI.1)
# Format: (variable, year, reference_value, tolerance_fraction). The 2020 entry
# for CO2 Energy & Industrial is an asymmetric COVID-era range.
# ---------------------------------------------------------------------------

VETTING_CRITERIA: list[dict] = [
    # CO2 emissions from energy and industrial processes (Mt CO2/yr)
    {"variable": "Emissions|CO2|Energy and Industrial Processes",
     "year": "2010", "ref": 33460.1, "tol": 0.25},
    {"variable": "Emissions|CO2|Energy and Industrial Processes",
     "year": "2015", "ref": 35627.3, "tol": 0.25},
    # 2020: special treatment for COVID - asymmetric range
    # lower bound from actual value with 25% tolerance = 26540.25
    # upper bound from interpolated (2018-2022 avg) with 25% tolerance = 46092.5
    {"variable": "Emissions|CO2|Energy and Industrial Processes",
     "year": "2020", "ref_lo": 26540.25, "ref_hi": 46092.5},
    {"variable": "Emissions|CO2|Energy and Industrial Processes",
     "year": "2025", "ref": 39383.5, "tol": 0.25},

    # Final energy (EJ/yr)
    {"variable": "Final Energy",
     "year": "2010", "ref": 365.074, "tol": 0.25},
    {"variable": "Final Energy",
     "year": "2015", "ref": 389.56, "tol": 0.25},
    {"variable": "Final Energy",
     "year": "2020", "ref": 395.78, "tol": 0.40},
    {"variable": "Final Energy",
     "year": "2025", "ref": 443.09, "tol": 0.25},

    # Primary energy from coal (EJ/yr)
    {"variable": "Primary Energy|Coal",
     "year": "2010", "ref": 153.51, "tol": 0.25},
    {"variable": "Primary Energy|Coal",
     "year": "2015", "ref": 161.99, "tol": 0.25},
    {"variable": "Primary Energy|Coal",
     "year": "2020", "ref": 160.00, "tol": 0.40},
    {"variable": "Primary Energy|Coal",
     "year": "2025", "ref": 200.43, "tol": 0.25},

    # Primary energy from gas (EJ/yr)
    {"variable": "Primary Energy|Gas",
     "year": "2010", "ref": 126.22, "tol": 0.25},
    {"variable": "Primary Energy|Gas",
     "year": "2015", "ref": 138.32, "tol": 0.25},
    {"variable": "Primary Energy|Gas",
     "year": "2020", "ref": 155.11, "tol": 0.40},
    {"variable": "Primary Energy|Gas",
     "year": "2025", "ref": 164.66, "tol": 0.25},

    # Primary energy from oil (EJ/yr)
    {"variable": "Primary Energy|Oil",
     "year": "2010", "ref": 167.72, "tol": 0.25},
    {"variable": "Primary Energy|Oil",
     "year": "2015", "ref": 180.60, "tol": 0.25},
    {"variable": "Primary Energy|Oil",
     "year": "2020", "ref": 173.40, "tol": 0.40},
    {"variable": "Primary Energy|Oil",
     "year": "2025", "ref": 197.75, "tol": 0.25},

    # Primary energy from nuclear (EJ/yr)
    {"variable": "Primary Energy|Nuclear",
     "year": "2010", "ref": 9.92, "tol": 0.25},
    {"variable": "Primary Energy|Nuclear",
     "year": "2015", "ref": 9.25, "tol": 0.25},
    {"variable": "Primary Energy|Nuclear",
     "year": "2020", "ref": 9.63, "tol": 0.40},
    {"variable": "Primary Energy|Nuclear",
     "year": "2025", "ref": 8.97, "tol": 0.25},
]

# Variables that must all be reported for a scenario to be assessable.
REQUIRED_VARIABLES = sorted({c["variable"] for c in VETTING_CRITERIA})


def _check_criterion(value: float, criterion: dict) -> bool | None:
    """Return True if value passes, False if it fails, None if NaN."""
    if pd.isna(value):
        return None
    if "ref_lo" in criterion:
        return criterion["ref_lo"] <= value <= criterion["ref_hi"]
    ref = criterion["ref"]
    tol = criterion["tol"]
    return ref * (1 - tol) <= value <= ref * (1 + tol)


def apply_vetting(df: pd.DataFrame) -> pd.DataFrame:
    """Apply SCI 2025 basic vetting to a global ensemble DataFrame.

    Parameters
    ----------
    df
        Wide IAMC frame (``Model, Scenario, Region, Variable, Unit, year-cols``)
        from :func:`ar7_ch5.load.load_sci_iamc_global`.

    Returns
    -------
    DataFrame with columns ``Model, Scenario, vetting_status, failed_criteria,
    n_criteria_checked``. ``vetting_status`` is one of ``"passed"``,
    ``"failed"``, ``"insufficient_reporting"``.
    """
    scenarios = df[["Model", "Scenario"]].drop_duplicates()
    results = []
    for _, row in scenarios.iterrows():
        model, scenario = row["Model"], row["Scenario"]
        mask = (df["Model"] == model) & (df["Scenario"] == scenario)
        sdf = df.loc[mask]

        reported_vars = set(sdf["Variable"].unique())
        missing_vars = [v for v in REQUIRED_VARIABLES if v not in reported_vars]

        if missing_vars:
            results.append({
                "Model": model,
                "Scenario": scenario,
                "vetting_status": "insufficient_reporting",
                "failed_criteria": f"missing: {', '.join(missing_vars)}",
                "n_criteria_checked": 0,
            })
            continue

        failed = []
        n_checked = 0
        for crit in VETTING_CRITERIA:
            var_rows = sdf.loc[sdf["Variable"] == crit["variable"]]
            if var_rows.empty:
                continue
            year = crit["year"]
            if year not in var_rows.columns:
                continue
            val = pd.to_numeric(var_rows.iloc[0][year], errors="coerce")
            result = _check_criterion(val, crit)
            if result is None:
                continue
            n_checked += 1
            if not result:
                if "ref_lo" in crit:
                    ref_str = f"{crit['ref_lo']:.1f} - {crit['ref_hi']:.1f}"
                else:
                    lo = crit["ref"] * (1 - crit["tol"])
                    hi = crit["ref"] * (1 + crit["tol"])
                    ref_str = f"{lo:.1f} - {hi:.1f}"
                failed.append(
                    f"{crit['variable']}|{year} (val={val:.1f}, range={ref_str})"
                )

        status = "failed" if failed else "passed"
        results.append({
            "Model": model,
            "Scenario": scenario,
            "vetting_status": status,
            "failed_criteria": "; ".join(failed) if failed else "",
            "n_criteria_checked": n_checked,
        })

    return pd.DataFrame(results)
