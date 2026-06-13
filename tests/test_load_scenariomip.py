"""Smoke test for the ScenarioMIP CMIP7 loader.

Skipped when the emissions CSV isn't staged; covers the canonical-name
mapping, the 7 scenarios, year-axis clipping, and a representative subset
filter.
"""

from __future__ import annotations

import pytest

from ar7_ch5.load_scenariomip import (
    SCENARIOS,
    load_scenariomip_emissions,
)
from ar7_ch5.runners import repo_root

CSV = repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def run():
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    return load_scenariomip_emissions(CSV)


def test_seven_pathways(run):
    """Each chapter pathway id (``VL`` ... ``H``) appears once, with the
    parallel ``scenario`` column carrying its canonical RCMIP3 SSP."""
    from ar7_ch5._rcmip3_naming import canonical_for
    assert sorted(run.get_unique_meta("pathway_id")) == sorted(SCENARIOS)
    expected_canonical = sorted({canonical_for(s) for s in SCENARIOS})
    assert sorted(run.get_unique_meta("scenario")) == expected_canonical


def test_canonical_emissions_only(run):
    """52 species after chapter harmonise + infill, in GCAGES naming."""
    variables = set(run.get_unique_meta("variable"))
    # 52 = COMPLETE_EMISSIONS_INPUT_VARIABLES_GCAGES from gcages.
    assert len(variables) == 52
    assert "Emissions|CO2|Fossil" in variables
    assert "Emissions|CO2|Biosphere" in variables


def test_annual_axis_2023_to_2100(run):
    """Chapter cache is the 2023-2100 annual harmonised+infilled window."""
    years = sorted(set(run["year"]))
    assert years[0] == 2023
    assert years[-1] == 2100
    assert years == list(range(2023, 2101))


def test_subset_filter():
    """``scenarios=`` filters on chapter pathway ids (the user's labels)."""
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    sub = load_scenariomip_emissions(CSV, scenarios=("M", "H"))
    assert sorted(sub.get_unique_meta("pathway_id")) == ["H", "M"]
    # canonical_for("M") == "scen7-M", canonical_for("H") == "scen7-H"
    assert sorted(sub.get_unique_meta("scenario")) == ["scen7-H", "scen7-M"]


def test_unknown_scenario_raises():
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    with pytest.raises(ValueError, match="not present"):
        load_scenariomip_emissions(CSV, scenarios=("XX_NOT_REAL",))


def test_iam_extension_spliced_past_2100():
    """end_year > 2100 splices the IAM emissions extension onto the cache.

    For ``Emissions|CO2|Fossil`` (an IAM-reported species), the loaded
    series past 2100 must differ from the 2100 chapter value (the IAM
    trajectory keeps changing); for ``Emissions|Halon1202`` (chapter
    stripped + infilled, IAM doesn't report past 2100), values must hold
    flat at the 2100 chapter value.
    """
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    run = load_scenariomip_emissions(CSV, scenarios=("VL",), end_year=2500)
    assert run.time_points.years().max() == 2500
    ts = run.filter(pathway_id="VL").timeseries().reset_index()
    year_cols = [c for c in ts.columns if hasattr(c, "year")]
    by_year = {c.year: c for c in year_cols}
    co2 = ts[ts["variable"] == "Emissions|CO2|Fossil"].iloc[0]
    halon = ts[ts["variable"] == "Emissions|Halon1202"].iloc[0]
    # IAM-reported species: 2200 differs from 2100.
    assert co2[by_year[2200]] != co2[by_year[2100]]
    # Chapter-stripped species: 2200 holds flat at 2100.
    assert halon[by_year[2200]] == halon[by_year[2100]]
