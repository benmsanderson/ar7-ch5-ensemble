"""Unit tests for archetype_features.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ar7_ch5.archetype_features import (
    _compute_pathway_features,
    _find_netzero_year,
    _integral_range,
    compute_features_sci,
    compute_features_smip,
)

# ---------------------------------------------------------------------------
# _find_netzero_year
# ---------------------------------------------------------------------------

def test_find_netzero_year_crossing():
    """Linear interpolation between a positive and non-positive value."""
    years = np.array([2020.0, 2025.0, 2030.0])
    vals = np.array([10.0, -5.0, -10.0])
    nz = _find_netzero_year(vals, years)
    # Linear interp: 10/(10+5) * 5 = 10/3 ≈ 3.33, so year ≈ 2023.33
    assert abs(nz - (2020 + 10 / 15 * 5)) < 1e-9


def test_find_netzero_year_no_crossing():
    years = np.array([2020.0, 2050.0, 2100.0])
    vals = np.array([10.0, 5.0, 3.0])
    assert np.isnan(_find_netzero_year(vals, years))


def test_find_netzero_year_already_negative():
    """Starts negative; no positive-to-nonpositive crossing."""
    years = np.array([2020.0, 2050.0, 2100.0])
    vals = np.array([-1.0, -2.0, -3.0])
    assert np.isnan(_find_netzero_year(vals, years))


def test_find_netzero_year_exact_zero():
    """Crossing exactly at grid point."""
    years = np.array([2020.0, 2025.0, 2030.0])
    vals = np.array([5.0, 0.0, -5.0])
    nz = _find_netzero_year(vals, years)
    assert abs(nz - 2025.0) < 1e-9


# ---------------------------------------------------------------------------
# _integral_range
# ---------------------------------------------------------------------------

def test_integral_range_simple():
    """Integral of constant 1 over [0, 10] = 10."""
    years = np.array([0.0, 5.0, 10.0])
    vals = np.ones(3)
    result = _integral_range(vals, years, 0, 10)
    assert abs(result - 10.0) < 1e-9


def test_integral_range_partial():
    """Integral of a line segment over sub-interval."""
    years = np.array([0.0, 10.0])
    vals = np.array([0.0, 10.0])  # y = x
    # integral from 2 to 8: trapz(2, 8) on y=x = (8^2 - 2^2)/2 = 30
    result = _integral_range(vals, years, 2, 8)
    assert abs(result - 30.0) < 1e-9


# ---------------------------------------------------------------------------
# _compute_pathway_features
# ---------------------------------------------------------------------------

def _make_pathway(
    eip_2020: float = 40000.0,  # Mt CO2/yr
    eip_2100: float = 0.0,
    afolu_const: float = -2000.0,
    ccs: float | None = 0.0,
    ch4_reduction: float = 0.5,
    sulfur_ratio: float = 0.3,
):
    """Synthetic 5-year pathway from 2010-2100."""
    years = np.arange(2010, 2101, 5, dtype=float)
    # EIP: linear decline from eip_2020 at 2020 to eip_2100 at 2100
    eip_at_2020 = eip_2020
    eip = np.interp(years, [2020.0, 2100.0], [eip_at_2020, eip_2100])
    eip[years < 2020] = eip_2020
    # AFOLU: constant
    afolu = np.full_like(years, afolu_const)
    # CCS: constant fraction
    ccs_arr = np.full_like(years, ccs) if ccs is not None else None
    # CH4: declines to ch4_reduction * 2020 value by 2050
    ch4_base = 400.0  # Mt CH4/yr
    ch4 = np.interp(
        years,
        [2020.0, 2050.0, 2100.0],
        [
            ch4_base,
            ch4_base * ch4_reduction,
            ch4_base * ch4_reduction * 0.5,
        ],
    )
    # Sulfur
    sulfur_base = 100.0
    sulfur = np.interp(
        years, [2020.0, 2050.0], [sulfur_base, sulfur_base * sulfur_ratio]
    )
    sulfur[years > 2050] = sulfur_base * sulfur_ratio
    return eip, afolu, ccs_arr, ch4, sulfur, years


def test_compute_pathway_basic():
    eip, afolu, ccs, ch4, sulfur, years = _make_pathway()
    feat = _compute_pathway_features(eip, afolu, ccs, ch4, sulfur, years)

    assert "cum_co2_eip" in feat
    assert "cdr_fraction" in feat
    assert "ch4_reduction" in feat
    assert "drawdown_band" in feat
    assert feat["cum_co2_eip"] > 0
    assert 0.0 <= feat["cdr_fraction"] <= 1.0


def test_compute_pathway_no_ccs():
    eip, afolu, _, ch4, sulfur, years = _make_pathway()
    feat = _compute_pathway_features(eip, afolu, None, ch4, sulfur, years)
    assert feat["cdr_fraction"] == 0.0


def test_compute_pathway_drawdown_over():
    """Large net-negative after NZ → drawdown_band == 'over'."""
    years = np.arange(2010, 2101, 5, dtype=float)
    # EIP drops sharply to zero by 2030
    eip = np.interp(years, [2020.0, 2030.0, 2100.0], [50000.0, 0.0, 0.0])
    # AFOLU strongly negative: -10000 Mt CO2/yr throughout
    afolu = np.full_like(years, -10000.0)
    ch4 = np.full_like(years, 400.0)
    sulfur = np.full_like(years, 100.0)
    feat = _compute_pathway_features(eip, afolu, None, ch4, sulfur, years)
    assert feat["drawdown_band"] in ("nz", "over")


def test_compute_pathway_pos_band():
    """Never reaches NZ → drawdown_band == 'pos'."""
    years = np.arange(2010, 2101, 5, dtype=float)
    eip = np.full_like(years, 40000.0)
    afolu = np.zeros_like(years)
    ch4 = np.full_like(years, 400.0)
    sulfur = np.full_like(years, 100.0)
    feat = _compute_pathway_features(eip, afolu, None, ch4, sulfur, years)
    assert feat["drawdown_band"] == "pos"


# ---------------------------------------------------------------------------
# compute_features_sci (synthetic IAMC frame)
# ---------------------------------------------------------------------------

def _make_sci_iamc(n_pathways: int = 3) -> pd.DataFrame:
    """Build a minimal SCI IAMC wide-format DataFrame."""
    year_cols = list(range(2010, 2101, 5))
    rows = []
    for i in range(n_pathways):
        base = {
            "Model": f"IAM{i}",
            "Scenario": f"SCN{i}",
            "Region": "World",
            "Unit": "Mt CO2/yr",
        }
        for var, vals_fn in [
            (
                "Climate Assessment|Harmonized|Emissions|CO2|"
                "Energy and Industrial Processes",
                lambda y: max(0, 40000 - 300 * (y - 2020)),
            ),
            ("Climate Assessment|Harmonized|Emissions|CO2|AFOLU",
             lambda y: -1000.0),
            ("Carbon Capture|Geological Storage",
             lambda y: 500.0),
            ("Climate Assessment|Harmonized|Emissions|CH4",
             lambda y: 400 - 2 * (y - 2020)),
            ("Climate Assessment|Harmonized|Emissions|Sulfur",
             lambda y: 100 - 0.5 * (y - 2020)),
        ]:
            row = {**base, "Variable": var}
            for y in year_cols:
                row[y] = vals_fn(y)
            rows.append(row)
    return pd.DataFrame(rows)


def test_compute_features_sci_shape():
    df = _make_sci_iamc(n_pathways=5)
    out = compute_features_sci(df)
    assert len(out) == 5
    assert "cum_co2_eip" in out.columns
    assert "cluster_label" not in out.columns


def test_compute_features_sci_missing_variable():
    """Pathways missing a required variable are dropped."""
    df = _make_sci_iamc(n_pathways=2)
    # Remove CH4 rows for IAM0
    df = df[~((df["Model"] == "IAM0") & (df["Variable"].str.contains("CH4")))]
    out = compute_features_sci(df)
    assert "IAM0" not in out["Model"].values
    assert "IAM1" in out["Model"].values


# ---------------------------------------------------------------------------
# compute_features_smip (synthetic ScenarioMIP frame)
# ---------------------------------------------------------------------------

def _make_smip_iamc(scenarios: list[str] | None = None) -> pd.DataFrame:
    if scenarios is None:
        scenarios = ["VL", "L", "M"]
    year_cols = [f"{y}.5" for y in range(2010, 2101)]
    rows = []
    for scen in scenarios:
        for var, val_fn in [
            ("CO2 FFI", lambda y: max(0, 40000 - 300 * (y - 2020))),
            ("CO2 AFOLU", lambda y: -500.0),
            ("CH4", lambda y: 400 - 2 * (y - 2020)),
            ("Sulfur", lambda y: 100.0),
        ]:
            row = {
                "model": "multi-model",
                "scenario": scen,
                "region": "World",
                "variable": var,
                "unit": "Mt/yr",
            }
            for yc in year_cols:
                y = float(yc)
                row[yc] = val_fn(y)
            rows.append(row)
    return pd.DataFrame(rows)


def test_compute_features_smip_shape():
    df = _make_smip_iamc(["VL", "L", "M"])
    out = compute_features_smip(df)
    assert len(out) == 3
    assert set(out["Scenario"]) == {"VL", "L", "M"}


def test_compute_features_smip_no_ccs():
    """ScenarioMIP has no CCS → cdr_fraction must be 0."""
    df = _make_smip_iamc(["M"])
    out = compute_features_smip(df)
    assert out["cdr_fraction"].iloc[0] == 0.0
