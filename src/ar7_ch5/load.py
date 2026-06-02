"""Scenario loaders for the SCI and ScenarioMIP CMIP7 input sets.

To be ported from scenariocompass `src/load.py` (milestone 3). Reads the SCI
2025 ensemble xlsx (the `data` sheet, IAMC wide format) and the ScenarioMIP
CMIP7 emissions, returning tidy emissions frames keyed by (model, scenario,
region, variable, unit).

For SCI, the relevant driving emissions already ship pre-harmonised and
infilled under the `Climate Assessment|Infilled|Emissions|*` namespace (54
species); this loader lifts those rather than re-harmonising. See
harmonise.py and the brief for the rationale.
"""
