"""Smoke test for the ScenarioMIP CMIP7 loader.

Skipped when the emissions CSV isn't staged; covers the canonical-name
mapping, the 7 scenarios, year-axis clipping, and a representative subset
filter.
"""

from __future__ import annotations

import pytest

from ar7_ch5.load import CANONICAL_EMISSIONS
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
    """All variables fall in the adapter-canonical set."""
    variables = set(run.get_unique_meta("variable"))
    assert variables.issubset(CANONICAL_EMISSIONS)
    # ScenarioMIP carries 23 species after canonicalisation, the full set
    # we drive.
    assert len(variables) == 23


def test_annual_axis_clipped_to_2100(run):
    """Half-year FaIR convention truncates to integer years and clips to 2100."""
    years = sorted(set(run["year"]))
    assert years[0] == 1750
    assert years[-1] == 2100
    assert years == list(range(1750, 2101))


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
