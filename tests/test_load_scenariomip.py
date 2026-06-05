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


def test_seven_scenarios(run):
    assert sorted(run.get_unique_meta("scenario")) == sorted(SCENARIOS)


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
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    sub = load_scenariomip_emissions(CSV, scenarios=("M", "H"))
    assert sorted(sub.get_unique_meta("scenario")) == ["H", "M"]


def test_unknown_scenario_raises():
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    with pytest.raises(ValueError, match="not present"):
        load_scenariomip_emissions(CSV, scenarios=("XX_NOT_REAL",))
