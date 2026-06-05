"""Smoke test for the RCMIP3 concentrations loader.

Skipped when the bundle isn't staged; covers the default-diagnostics
selection, the wide variable set (Atmospheric Concentrations|*),
year-axis clipping, subset filter, and resolve-path flexibility.
"""

from __future__ import annotations

import pytest

from ar7_ch5.load_rcmip3 import (
    DEFAULT_DIAGNOSTICS,
    load_rcmip3_concentrations,
    resolve_concentrations_csv,
)
from ar7_ch5.runners import repo_root

BUNDLE = repo_root() / "data" / "rcmip3_protocol"


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def run():
    if not BUNDLE.is_dir():
        pytest.skip(f"RCMIP3 bundle not staged at {BUNDLE}")
    return load_rcmip3_concentrations(BUNDLE)


def test_default_diagnostics(run):
    assert sorted(run.get_unique_meta("scenario")) == sorted(DEFAULT_DIAGNOSTICS)
    # RCMIP3 scenarios are already canonical: pathway_id == scenario, emitted
    # for cross-experiment uniformity with M4 / M5 / M6.
    assert sorted(run.get_unique_meta("pathway_id")) == sorted(DEFAULT_DIAGNOSTICS)


def test_atmospheric_concentrations_only(run):
    """Every variable is an Atmospheric Concentrations|* row."""
    variables = run.get_unique_meta("variable")
    assert variables
    assert all(v.startswith("Atmospheric Concentrations|") for v in variables)


def test_annual_axis_clipped_to_2100(run):
    years = sorted(set(run["year"]))
    assert years[0] == 1750
    assert years[-1] == 2100
    assert years == list(range(1750, 2101))


def test_subset_filter_and_unknown_raises():
    if not BUNDLE.is_dir():
        pytest.skip(f"RCMIP3 bundle not staged at {BUNDLE}")
    sub = load_rcmip3_concentrations(BUNDLE, scenarios=("abrupt-4xCO2", "ssp245"))
    assert sorted(sub.get_unique_meta("scenario")) == ["abrupt-4xCO2", "ssp245"]
    with pytest.raises(ValueError, match="not present"):
        load_rcmip3_concentrations(BUNDLE, scenarios=("XX_NOT_REAL",))


def test_resolve_path_flexibility():
    """resolve_concentrations_csv accepts root, subdir, or direct CSV."""
    if not BUNDLE.is_dir():
        pytest.skip(f"RCMIP3 bundle not staged at {BUNDLE}")
    csv_root = resolve_concentrations_csv(BUNDLE)
    csv_subdir = resolve_concentrations_csv(BUNDLE / "RCMIP3_input_datafiles")
    csv_direct = resolve_concentrations_csv(csv_root)
    assert csv_root == csv_subdir == csv_direct
    assert csv_root.is_file()
