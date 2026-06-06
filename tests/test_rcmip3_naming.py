"""Unit tests for the chapter-pathway -> RCMIP3-protocol-name mapping.

Verifies the audit trail an IPCC reviewer would want: every chapter
pathway resolves to a documented RCMIP3 protocol name through explicit
lookups against the protocol scenario catalogue.
"""

from __future__ import annotations

import pytest

from ar7_ch5._rcmip3_naming import (
    FALLBACK_CANONICAL,
    RCMIP3_CANONICAL_SCENARIOS,
    SCENARIOMIP_TO_CANONICAL,
    SCI_FAMILY_DEFAULT_CANONICAL,
    SSP2COM_CANONICAL_SURROGATE,
    SSP2COM_CHAPTER_NAME,
    canonical_for,
)


@pytest.mark.parametrize(
    "name",
    [
        # SSP-RCP family.
        "ssp119", "ssp126", "ssp245", "ssp370", "ssp434", "ssp460",
        "ssp534-over", "ssp585",
        # Idealised.
        "abrupt-2xCO2", "abrupt-4xCO2", "1pctCO2", "piControl",
        "esm-flat10", "esm-flat7.5", "esm-flat20",
        # Historical / attribution.
        "historical", "historical-cmip6", "hist-CO2",
        # CMIP7 ScenarioMIP categories (protocol names).
        "scen7-VL", "scen7-L", "scen7-LN", "scen7-M", "scen7-ML",
        "scen7-H", "scen7-HL",
    ],
)
def test_protocol_names_pass_through(name):
    assert name in RCMIP3_CANONICAL_SCENARIOS
    assert canonical_for(name) == name


def test_scenariomip_short_labels_map_to_scen7_protocol_names():
    """The GMD-paper short labels (VL, L, LN, M, ML, H, HL) resolve to
    their RCMIP3 protocol equivalents (``scen7-{cat}``)."""
    assert canonical_for("VL") == "scen7-VL"
    assert canonical_for("L") == "scen7-L"
    assert canonical_for("LN") == "scen7-LN"
    assert canonical_for("M") == "scen7-M"
    assert canonical_for("ML") == "scen7-ML"
    assert canonical_for("H") == "scen7-H"
    assert canonical_for("HL") == "scen7-HL"


def test_ssp2com_surrogate_documented():
    """SSP2-COM is the one chapter scenario with no RCMIP3 protocol name;
    surrogate-mapped to ssp245 and documented in methods.md."""
    assert SSP2COM_CHAPTER_NAME == "SSP2-com"
    assert SSP2COM_CANONICAL_SURROGATE == "ssp245"
    assert canonical_for(SSP2COM_CHAPTER_NAME) == SSP2COM_CANONICAL_SURROGATE


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
    canonical RCMIP3 SSP-RCP scenario resolve directly."""
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
    counterpart fall back to the SSP family's default."""
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
    """Every value emitted by the lookup tables is either a protocol
    RCMIP3 name (member of :data:`RCMIP3_CANONICAL_SCENARIOS`) or the
    explicitly documented ``SSP2-com`` surrogate (which IS a protocol
    name, ``ssp245`` -- the surrogate distinction is about the source
    scenario, not the target name)."""
    for value in SCENARIOMIP_TO_CANONICAL.values():
        assert value in RCMIP3_CANONICAL_SCENARIOS, value
    for value in SCI_FAMILY_DEFAULT_CANONICAL.values():
        assert value in RCMIP3_CANONICAL_SCENARIOS, value
    assert SSP2COM_CANONICAL_SURROGATE in RCMIP3_CANONICAL_SCENARIOS
    assert FALLBACK_CANONICAL in RCMIP3_CANONICAL_SCENARIOS


def test_protocol_catalogue_includes_full_scen7_set():
    """All seven ScenarioMIP CMIP7 baselines must be in the protocol
    catalogue so they pass through unchanged when a loader already uses
    the canonical name."""
    for cat in ("VL", "L", "LN", "M", "ML", "H", "HL"):
        assert f"scen7-{cat}" in RCMIP3_CANONICAL_SCENARIOS
