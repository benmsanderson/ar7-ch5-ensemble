"""Chapter scenario name -> RCMIP3 canonical name mapping.

This is the single auditable table for "which RCMIP3 bundle row supplied
the historical splice, the natural forcings, and the land-use forcing
for a given chapter pathway?". Loaders call :func:`canonical_for` to
translate names *before* the runner sees them; the chapter pathway
identifier is preserved in a parallel ``pathway_id`` meta column on the
same ScmRun. See ``docs/engine_upstream_switch.md`` for the full audit
trail and the locked design decisions.

The mapping intentionally has no regex magic: every chapter scenario
name resolves through a small number of explicit lookups, in a fixed
priority order. An IPCC reviewer can read this module and the test
suite together to verify the canonical-name choice for any pathway.
"""

from __future__ import annotations

# Canonical RCMIP3 scenarios as published in the protocol bundle's
# concentrations CSV (Zenodo 20430630). Anything in this set passes
# through ``canonical_for`` unchanged.
RCMIP3_CANONICAL_SCENARIOS: frozenset[str] = frozenset({
    # The eight concentration-driven SSPs.
    "ssp119", "ssp126", "ssp245", "ssp370", "ssp434", "ssp460",
    "ssp534-over", "ssp585",
    # Historical + attribution.
    "historical", "historical-cmip6",
    "hist-CO2", "hist-GHG", "hist-aer",
    # CO2-only idealised.
    "1pctCO2", "1pctCO2-4xext", "1pctCO2-cdr",
    "abrupt-2xCO2", "abrupt-4xCO2", "abrupt-0p5xCO2",
    "piControl",
    # ESM all-GHG attribution variants.
    "esm-allGHG-ssp370-lowCH4",
    "esm-allGHG-ssp370-lowNTCF",
    "esm-allGHG-ssp370-lowNTCF-HighCH4",
    "esm-allGHG-ssp534-over-highCH4",
    "esm-allGHG-ssp585-lowCH4",
})

# ScenarioMIP CMIP7 short labels -> canonical RCMIP3 name.
# The choice is by the SSP family the long_scenario identifies with --
# the bundle row supplies natural / LU forcings, so SSP-family alignment
# is the operative axis.
#
#   VL : SSP1 - Very Low Emissions
#   L  : SSP2 - Low Emissions
#   LN : SSP2 - Low Overshoot_a
#   M  : SSP2 - Medium Emissions
#   ML : SSP2 - Medium-Low Emissions
#   HL : SSP5 - Medium-Low Emissions_a
#   H  : SSP3 - High Emissions
SCENARIOMIP_TO_CANONICAL: dict[str, str] = {
    "VL": "ssp119",
    "L":  "ssp126",
    "LN": "ssp126",
    "M":  "ssp245",
    "ML": "ssp245",
    "HL": "ssp585",
    "H":  "ssp370",
}

# SSP-family default canonical (used for SCI ``SSPx-Baseline`` and for any
# ``SSPx-NN`` combination that doesn't have a direct RCMIP3 counterpart).
SCI_FAMILY_DEFAULT_CANONICAL: dict[str, str] = {
    "SSP1": "ssp126",
    "SSP2": "ssp245",
    "SSP3": "ssp370",
    "SSP4": "ssp460",
    "SSP5": "ssp585",
}

# Direct (SSP family, target suffix) -> canonical for SCI ``SSPx-NN`` names
# where the (family, target) pair has a canonical RCMIP3 SSP.
_SCI_FAMILY_TARGET_CANONICAL: dict[tuple[str, str], str] = {
    ("SSP1", "19"): "ssp119",
    ("SSP1", "26"): "ssp126",
    ("SSP2", "45"): "ssp245",
    ("SSP3", "70"): "ssp370",
    ("SSP4", "34"): "ssp434",
    ("SSP4", "60"): "ssp460",
    ("SSP5", "34"): "ssp534-over",
    ("SSP5", "85"): "ssp585",
}

# Neutral fallback used when no rule matches. Logged via NOTE so the user
# notices, but does not crash (each input set's loader is the right place
# to add a mapping if a new chapter scenario appears).
FALLBACK_CANONICAL = "ssp245"


def canonical_for(scenario: str) -> str:
    """Map a chapter scenario name to its RCMIP3 canonical name.

    Resolution order:

    1. Already canonical (member of :data:`RCMIP3_CANONICAL_SCENARIOS`)
       -> pass through.
    2. ScenarioMIP CMIP7 short label (``VL``, ``L``, ``LN``, ``M``,
       ``ML``, ``HL``, ``H``) -> :data:`SCENARIOMIP_TO_CANONICAL`.
    3. ``SSP2-com`` (M5 SSP2-COM) -> ``ssp245``.
    4. SCI ``SSPx-NN`` pattern -> the direct family-target match if one
       exists, otherwise the family default from
       :data:`SCI_FAMILY_DEFAULT_CANONICAL`.
    5. SCI ``SSPx-Baseline`` pattern -> family default.
    6. Otherwise -> :data:`FALLBACK_CANONICAL` with a NOTE printed.
    """
    if scenario in RCMIP3_CANONICAL_SCENARIOS:
        return scenario
    if scenario in SCENARIOMIP_TO_CANONICAL:
        return SCENARIOMIP_TO_CANONICAL[scenario]
    if scenario == "SSP2-com":
        return "ssp245"
    if "-" in scenario:
        family, suffix = scenario.split("-", 1)
        if family in SCI_FAMILY_DEFAULT_CANONICAL:
            return _SCI_FAMILY_TARGET_CANONICAL.get(
                (family, suffix),
                SCI_FAMILY_DEFAULT_CANONICAL[family],
            )
    print(
        f"NOTE: scenario {scenario!r} has no explicit RCMIP3 canonical "
        f"mapping; defaulting to {FALLBACK_CANONICAL}."
    )
    return FALLBACK_CANONICAL


__all__ = [
    "RCMIP3_CANONICAL_SCENARIOS",
    "SCENARIOMIP_TO_CANONICAL",
    "SCI_FAMILY_DEFAULT_CANONICAL",
    "FALLBACK_CANONICAL",
    "canonical_for",
]
