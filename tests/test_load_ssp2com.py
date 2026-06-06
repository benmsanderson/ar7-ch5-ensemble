"""Smoke test for the SSP2-COM loader.

Skipped when the world-total xlsx isn't staged at the canonical location, so a
bare checkout still collects and passes. The fixture itself is just a sanity
check that shape, variable set, units, and the canonical 2023-2100 annual axis
are what downstream SCM runs will see.
"""

from __future__ import annotations

import pytest

from ar7_ch5.load import CANONICAL_EMISSIONS
from ar7_ch5.load_ssp2com import (
    SSP2COM_CANONICAL_SCENARIO,
    SSP2COM_MODEL,
    SSP2COM_PATHWAY_ID,
    load_ssp2com_world_total,
)
from ar7_ch5.runners import repo_root

SSP2COM_XLSX = (
    repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"
)


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def ssp2com_run():
    if not SSP2COM_XLSX.is_file():
        pytest.skip(f"SSP2-COM xlsx not staged at {SSP2COM_XLSX}")
    return load_ssp2com_world_total(SSP2COM_XLSX)


def test_single_pathway_meta(ssp2com_run):
    """The world-total file ships one model x one pathway x World only.

    The ScmRun carries both columns: ``pathway_id`` is the chapter
    identifier (``SSP2-com``); ``scenario`` is the canonical RCMIP3 name
    the runner splices against (``ssp245``).
    """
    assert ssp2com_run.get_unique_meta("model") == [SSP2COM_MODEL]
    assert ssp2com_run.get_unique_meta("pathway_id") == [SSP2COM_PATHWAY_ID]
    assert ssp2com_run.get_unique_meta("scenario") == [SSP2COM_CANONICAL_SCENARIO]
    assert ssp2com_run.get_unique_meta("region") == ["World"]


def test_annual_axis(ssp2com_run):
    """Native xlsx is mixed 1-/5-yearly 2023-2100; loader interpolates annual."""
    years = sorted(set(ssp2com_run["year"]))
    assert years[0] == 2023
    assert years[-1] == 2100
    assert len(years) == 78
    # No gaps in the annual grid.
    assert years == list(range(2023, 2101))


def test_canonical_emissions(ssp2com_run):
    """All 23 SSP2-COM species canonicalise into the adapter-known set."""
    variables = set(ssp2com_run.get_unique_meta("variable"))
    assert variables.issubset(CANONICAL_EMISSIONS)
    # The xlsx ships 23 species, all in our canonical set.
    assert len(variables) == 23
    # CO2 sectors are the MAGICC-naming ones.
    assert "Emissions|CO2|MAGICC Fossil and Industrial" in variables
    assert "Emissions|CO2|MAGICC AFOLU" in variables
