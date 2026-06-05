"""Unit tests for the chapter-scenario -> RCMIP3-canonical mapping.

Verifies the audit trail an IPCC reviewer would want: every chapter
scenario family resolves to a documented canonical RCMIP3 name through
explicit lookups.
"""

from __future__ import annotations

import pytest

from ar7_ch5._rcmip3_naming import (
    FALLBACK_CANONICAL,
    RCMIP3_CANONICAL_SCENARIOS,
    SCENARIOMIP_TO_CANONICAL,
    SCI_FAMILY_DEFAULT_CANONICAL,
    canonical_for,
)


@pytest.mark.parametrize(
    "name",
    [
        "ssp119", "ssp126", "ssp245", "ssp370", "ssp434", "ssp460",
        "ssp534-over", "ssp585",
        "abrupt-2xCO2", "abrupt-4xCO2", "1pctCO2", "piControl",
        "historical", "hist-CO2",
    ],
)
def test_canonical_names_pass_through(name):
    assert name in RCMIP3_CANONICAL_SCENARIOS
    assert canonical_for(name) == name


def test_scenariomip_short_labels_map_by_ssp_family():
    """ScenarioMIP CMIP7 short labels resolve by the SSP family their long
    scenario identifies with, not by a target-W/m^2 match."""
    assert canonical_for("VL") == "ssp119"
    assert canonical_for("L") == "ssp126"
    assert canonical_for("LN") == "ssp126"
    assert canonical_for("M") == "ssp245"
    assert canonical_for("ML") == "ssp245"
    assert canonical_for("HL") == "ssp585"
    assert canonical_for("H") == "ssp370"


def test_ssp2com_maps_to_ssp245():
    """SSP2-COM anchors to ssp245, matching Charlie Koven's pipeline."""
    assert canonical_for("SSP2-com") == "ssp245"


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("SSP1-19", "ssp119"),
        ("SSP1-26", "ssp126"),
        ("SSP2-45", "ssp245"),
        ("SSP3-70", "ssp370"),
        ("SSP4-34", "ssp434"),
        ("SSP4-60", "ssp460"),
        ("SSP5-34", "ssp534-over"),
        ("SSP5-85", "ssp585"),
    ],
)
def test_sci_family_target_combinations_with_canonical_match(scenario, expected):
    """SCI ``SSPx-NN`` names where the (family, target) pair has a
    canonical RCMIP3 SSP resolve directly."""
    assert canonical_for(scenario) == expected


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("SSP2-19", "ssp245"),    # no ssp219 canonical -> SSP2 family default
        ("SSP3-26", "ssp370"),    # no ssp326 canonical -> SSP3 family default
        ("SSP4-45", "ssp460"),    # no ssp445 canonical -> SSP4 family default
        ("SSP5-19", "ssp585"),    # no ssp519 canonical -> SSP5 family default
        ("SSP1-85", "ssp126"),    # no ssp185 canonical -> SSP1 family default
    ],
)
def test_sci_family_target_combinations_without_canonical_match(scenario, expected):
    """SCI ``SSPx-NN`` names where (family, target) has no canonical RCMIP3
    counterpart fall back to the SSP family's default canonical."""
    assert canonical_for(scenario) == expected


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("SSP1-Baseline", "ssp126"),
        ("SSP2-Baseline", "ssp245"),
        ("SSP3-Baseline", "ssp370"),
        ("SSP4-Baseline", "ssp460"),
        ("SSP5-Baseline", "ssp585"),
    ],
)
def test_sci_baselines_use_family_default(scenario, expected):
    assert canonical_for(scenario) == expected


def test_unknown_scenario_falls_back_with_note(capsys):
    """Unmapped names fall back to ssp245 with a printed NOTE rather than
    crashing -- the chapter author notices the unfamiliar name."""
    result = canonical_for("not_a_real_scenario_xyz")
    assert result == FALLBACK_CANONICAL
    captured = capsys.readouterr()
    assert "NOTE" in captured.out
    assert "not_a_real_scenario_xyz" in captured.out


def test_mapping_tables_are_consistent_with_canonical_set():
    """Every canonical value emitted by the lookup tables is itself a
    canonical RCMIP3 scenario name, so canonical_for never produces an
    unknown name."""
    for value in SCENARIOMIP_TO_CANONICAL.values():
        assert value in RCMIP3_CANONICAL_SCENARIOS, value
    for value in SCI_FAMILY_DEFAULT_CANONICAL.values():
        assert value in RCMIP3_CANONICAL_SCENARIOS, value
    assert FALLBACK_CANONICAL in RCMIP3_CANONICAL_SCENARIOS
