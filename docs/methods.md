# Methods

Methodological reference for the Chapter 5 runs. This will be filled out as the
ports land (it is the AR7 successor to scenariocompass `docs/APPROACHES.md`).
The one decision worth stating up front is how emissions reach the climate
models.

## Emissions to the climate models: no harmonisation stack in v1

Three of the four input sets arrive already harmonised and infilled, so v1 does
not take on a harmonisation/infilling pipeline (no aneris/silicone machinery):

- **SCI 2025** ships harmonised + infilled driving emissions under
  `Climate Assessment|Infilled|Emissions|*` (54 species), produced with the AR6
  climate-assessment workflow (Kikstra et al.) and run through MAGICC v7.5.3.
  We lift these directly.
- **ScenarioMIP CMIP7** emissions are already harmonised + infilled by the
  CMIP7 pipeline.
- **SSP2-COM** is the one set that needs harmonising. It is handled by a
  light-touch global (World-total) harmoniser: ratio convergence for
  positive-definite species, offset convergence for zero-crossing species (net
  CO2, CO2|AFOLU), with a single convergence-year knob, anchored to the CMIP7
  world-total harmonised history (52 species, 1750-2023, Zenodo 17845154).
  Missing halocarbons are borrowed from a baseline scenario rather than
  silicone-infilled.
- **RCMIP3** is concentration-driven, so no emissions harmonisation applies.

### Vintage note (flag before cross-ensemble comparison)

SCI is harmonised to the AR6 historical vintage (~2015 base, RCMIP), while the
ScenarioMIP CMIP7 set is harmonised to 2023 CMIP7 history. The two ensembles
therefore sit on different historical baselines. Treating each on its own terms
is fine; making them directly comparable on one baseline would mean
re-harmonising SCI to the 2023 anchor with the same global harmoniser. That is
a deliberate, deferred scientific choice, not a v1 default.

## AFOLU CO2 convention

For SCM driving, use the physical `Emissions|CO2|AFOLU`, not the
`Emissions|CO2|AFOLU [NGHGI]` (national-inventory) variant, because the SCMs
model the physical carbon cycle.

## The Chapter 5 contribution

SCI ships MAGICC-only climate outcomes. The value added here is running the same
harmonised emissions through FaIR 2.x and CICERO-SCM as well, giving a genuine
three-SCM ensemble spread on identical inputs.
