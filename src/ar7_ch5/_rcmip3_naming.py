"""Chapter scenario name -> RCMIP3 protocol name mapping.

This is the single auditable table for "which RCMIP3 protocol scenario
labels a given chapter pathway, and which canonical CSV row supplies
the splice for it?". Loaders call :func:`canonical_for` to translate
chapter pathway IDs into the protocol RCMIP3 name *before* the runner
sees them; the chapter pathway identifier is preserved in a parallel
``pathway_id`` meta column on the same ScmRun.

The canonical names come from the RCMIP Phase 3 protocol scenario
list (``rcmip_phase3_protocol_v2.0.0.xlsx`` sheet ``scenario_info``,
Zenodo 20430630). The intent is that any artefact's ``scenario`` value
is a real RCMIP3 scenario name an IPCC reviewer can look up directly:

- ScenarioMIP CMIP7 baselines ``VL``..``HL`` -> ``scen7-VL``..``scen7-HL``
  (the protocol's own labels for the CMIP7 ScenarioMIP categories).
- SCI ``SSPx-NN`` pathways -> the matching CMIP6 SSP-RCP scenario
  (``SSP1-19`` -> ``ssp119``, ``SSP3-70`` -> ``ssp370``, ...). These
  ARE protocol RCMIP3 names; SCI is a re-elicitation of CMIP6 SSP
  targets.
- Idealised runs (``1pctCO2``, ``abrupt-2xCO2``, ``esm-flat10``, ...)
  pass through unchanged; they are first-class RCMIP3 protocol names.
- ``SSP2-com`` is a chapter scenario that has no RCMIP3 protocol name.
  It is surrogate-mapped to ``ssp245`` with the surrogate flagged
  explicitly (it is the only scenario in the chapter that lacks a
  matching RCMIP3 row).

The ``scen7-{cat}`` rows are present in the *augmented* RCMIP3 bundle
the chapter stages at data-setup time. The chapter's
``scripts/build_rcmip3_bundle_augmented.py`` copies the published
RCMIP3 protocol bundle (Zenodo 20430630) into
``data/rcmip3_protocol_augmented/`` and inserts seven new rows in
``rcmip_phase3_forcing_v2.0.0.csv`` for ``scen7-VL``..``scen7-HL`` with
``Effective Radiative Forcing|Natural|Solar`` and ``|Volcanic`` time
series sourced from scenariomip-paper-plots (Zenodo 20329427,
``data/fair-inputs/volcanic_solar.csv``). The upstream openscm-runner
then resolves ``scen7-*`` natural forcings from the augmented bundle
exactly as it would for any SSP-RCP scenario; no chapter-side
surrogate or scenario swap-and-restore is needed.

See ``docs/data_setup.md`` for the augmented-bundle build step,
``docs/engine_upstream_switch.md`` for the audit trail, and
``docs/methods.md`` for the natural-forcings source.
"""

from __future__ import annotations

# --- Protocol scenario catalogue -------------------------------------------
#
# The full RCMIP Phase 3 protocol scenario list (99 rows of
# ``scenario_info`` sheet in ``rcmip_phase3_protocol_v2.0.0.xlsx``).
# Anything in this set is a real protocol scenario name; ``canonical_for``
# returns members of this set (or, for the ``SSP2-com`` surrogate, a
# documented exception).
RCMIP3_CANONICAL_SCENARIOS: frozenset[str] = frozenset({
    # Pre-industrial controls + historical.
    "piControl", "esm-piControl", "esm-allGHG-piControl",
    "historical", "historical-cmip6", "esm-hist", "esm-hist-cmip6",
    "esm-allGHG-hist", "esm-allGHG-hist-cmip6",
    "hist-CO2", "hist-GHG", "hist-aer",
    # CO2-only idealised.
    "1pctCO2", "1pctCO2-4xext", "1pctCO2-cdr",
    "1pctCO2-bgc", "1pctCO2-rad",
    "esm-1pct-brch-1000PgC", "esm-1pct-brch-2000PgC",
    "esm-1pct-brch-750PgC",
    "abrupt-4xCO2", "abrupt-2xCO2", "abrupt-0p5xCO2",
    # Pulse and bell.
    "esm-pi-cdr-pulse", "esm-pi-CO2pulse",
    "esm-bell-1000PgC", "esm-bell-2000PgC", "esm-bell-750PgC",
    # CMIP6 SSP-RCP family (concentration- and emissions-driven).
    "ssp119", "ssp126", "ssp245", "ssp370", "ssp434", "ssp460",
    "ssp534-over", "ssp585",
    "esm-ssp119", "esm-ssp126", "esm-ssp245", "esm-ssp370",
    "esm-ssp434", "esm-ssp460", "esm-ssp534-over", "esm-ssp585",
    # ESM all-GHG attribution variants on the SSP-RCP family.
    "esm-allGHG-ssp119", "esm-allGHG-ssp126", "esm-allGHG-ssp245",
    "esm-allGHG-ssp370", "esm-allGHG-ssp370-lowNTCF",
    "esm-allGHG-ssp370-lowCH4",
    "esm-allGHG-ssp370-lowNTCF-HighCH4",
    "esm-allGHG-ssp434", "esm-allGHG-ssp460",
    "esm-allGHG-ssp534-over",
    "esm-allGHG-ssp534-over-highCH4",
    "esm-allGHG-ssp585", "esm-allGHG-ssp585-lowCH4",
    # CMIP7 ScenarioMIP categories (concentration- and esm-driven).
    "scen7-H", "scen7-HL", "scen7-M", "scen7-ML",
    "scen7-L", "scen7-VL", "scen7-LN",
    "scen7-HC", "scen7-HLC", "scen7-MC", "scen7-MLC",
    "scen7-LC", "scen7-VLC", "scen7-LNC",
    "esm-scen7-H", "esm-scen7-HL", "esm-scen7-M", "esm-scen7-ML",
    "esm-scen7-L", "esm-scen7-VL", "esm-scen7-LN",
    "esm-allGHG-scen7-H", "esm-allGHG-scen7-HL",
    "esm-allGHG-scen7-H-CH4L",
    "esm-allGHG-scen7-M", "esm-allGHG-scen7-ML",
    "esm-allGHG-scen7-L", "esm-allGHG-scen7-L-CH4H",
    "esm-allGHG-scen7-VL", "esm-allGHG-scen7-LN",
    # ESM constant-emissions idealised (flat10 / flat7.5 / flat20).
    "esm-flat10", "esm-flat10-zec", "esm-flat10-cdr",
    "esm-flat10-nz", "esm-flat10-rev",
    "esm-flat7.5", "esm-flat7.5-cdr", "esm-flat7.5-zec",
    "esm-flat7.5-nz", "esm-flat7.5-rev",
    "esm-flat20", "esm-flat20-cdr", "esm-flat20-zec",
    "esm-flat20-nz", "esm-flat20-rev",
    # MethaneMIP.
    "methanemip-TM-allGHG", "methanemip-TM+BC-allGHG",
})


# --- ScenarioMIP CMIP7 short label -> canonical protocol name ---------------
#
# The chapter uses the GMD-paper short labels (``VL``/``L``/.../``H``/``HL``)
# for the seven CMIP7 ScenarioMIP baselines. RCMIP3's protocol names for
# the same set are ``scen7-{category}``.
SCENARIOMIP_TO_CANONICAL: dict[str, str] = {
    "VL": "scen7-VL",
    "L":  "scen7-L",
    "LN": "scen7-LN",
    "M":  "scen7-M",
    "ML": "scen7-ML",
    "H":  "scen7-H",
    "HL": "scen7-HL",
}


# --- SCI SSPx-NN family/target tables --------------------------------------
#
# SCI pathways are reported as ``IAM | SSPx-NN`` (e.g. ``IMAGE | SSP1-19``).
# These are CMIP6 SSP-RCP variants; the canonical RCMIP3 name is the
# matching ``ssp{x}{NN}`` row in the protocol.
SCI_FAMILY_DEFAULT_CANONICAL: dict[str, str] = {
    "SSP1": "ssp126",
    "SSP2": "ssp245",
    "SSP3": "ssp370",
    "SSP4": "ssp460",
    "SSP5": "ssp585",
}

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


# --- SSP2-COM: the one chapter scenario with no RCMIP3 protocol name -------
#
# SSP2-COM (community SSP2) is sourced from scenariocompass. It is not in
# the RCMIP3 protocol scenario list and so cannot pass through unchanged.
# The chapter records ``SSP2-com`` on ``pathway_id`` and surrogate-maps to
# ``ssp245`` on the canonical ``scenario`` column, with the surrogate
# documented in ``docs/methods.md``.
SSP2COM_CHAPTER_NAME = "SSP2-com"
SSP2COM_CANONICAL_SURROGATE = "ssp245"


# Neutral fallback used when no rule matches. Logged via NOTE so the user
# notices, but does not crash (each input set's loader is the right place
# to add a mapping if a new chapter scenario appears).
FALLBACK_CANONICAL = "ssp245"


def canonical_for(scenario: str) -> str:
    """Map a chapter pathway identifier to its RCMIP3 protocol name.

    Resolution order:

    1. Already a protocol RCMIP3 name (member of
       :data:`RCMIP3_CANONICAL_SCENARIOS`) -> pass through. Idealised
       runs (``1pctCO2``, ``esm-flat10``, ``abrupt-2xCO2``, ...) and
       SSP-RCP names (``ssp119``..``ssp585``) take this branch.
    2. ScenarioMIP CMIP7 short label (``VL``, ``L``, ``LN``, ``M``,
       ``ML``, ``HL``, ``H``) -> :data:`SCENARIOMIP_TO_CANONICAL`
       (returns the ``scen7-{cat}`` protocol name).
    3. ``SSP2-com`` (chapter-only) -> :data:`SSP2COM_CANONICAL_SURROGATE`
       (no RCMIP3 protocol name exists; surrogate documented).
    4. SCI ``SSPx-NN`` pattern -> the direct family-target match if one
       exists (``SSP1-19`` -> ``ssp119``), otherwise the family default
       from :data:`SCI_FAMILY_DEFAULT_CANONICAL`.
    5. SCI ``SSPx-Baseline`` pattern -> family default.
    6. Otherwise -> :data:`FALLBACK_CANONICAL` with a NOTE printed.
    """
    if scenario in RCMIP3_CANONICAL_SCENARIOS:
        return scenario
    if scenario in SCENARIOMIP_TO_CANONICAL:
        return SCENARIOMIP_TO_CANONICAL[scenario]
    if scenario == SSP2COM_CHAPTER_NAME:
        return SSP2COM_CANONICAL_SURROGATE
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
    "SSP2COM_CHAPTER_NAME",
    "SSP2COM_CANONICAL_SURROGATE",
    "FALLBACK_CANONICAL",
    "canonical_for",
]
