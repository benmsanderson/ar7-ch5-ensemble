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

### Validation against Charlie Koven's `ar7_wg1_ch5` reference

The SSP2-COM harmoniser is compared against Charlie Koven's FaIR-only
SSP2-COM pipeline using `scripts/validate_ssp2com_vs_charlie.py`. The
script loads both pipelines' SSP2-COM emissions and writes a per-
(species, year) comparison CSV to `outputs/ssp2com/validation_vs_charlie.csv`.

Two systematic differences come out, and both are method choices rather
than bugs:

1. **Input gap.** Charlie's SSP2-COM CSV (`data/fair-inputs/emissions_1750-
   2500_with_ssp2com.csv`) carries the main GHGs and ozone precursors but
   not all of the halocarbons; his pipeline fills the missing species with
   the L scenario as a default. The scenariocompass world-total xlsx we
   use does carry the full 23-species SSP2-COM set, so for 8 HFCs
   (HFC-125, HFC-134a, HFC-143a, HFC-227ea, HFC-23, HFC-245fa, HFC-32,
   HFC-4310mee) the two pipelines are not even running on the same
   underlying scenario data. The validation script flags these
   explicitly under `charlie_used_l_fallback=True` and excludes them
   from the harmonisation-comparison summary.

2. **Anchor choice.** For the 15 species both pipelines source from
   SSP2-COM (BC, CH4, CO, CO2 AFOLU, CO2 FFI, N2O, NH3, NOx, OC, SF6,
   Sulfur, VOC, C2F6, C6F14, CF4), the main GHGs agree at 5-15% across
   2025-2100. The PFCs (C2F6, CF4, C6F14) show large 2025 anomalies (up
   to ~220% for C2F6) because the published 2023 global history endpoint
   has very different values than the IAM's 2023 estimate (factor of ~4
   for C2F6); the linear taper on a large correction creates a transient
   bump that resolves by 2050. This is intrinsic to the ratio-with-
   convergence method when scenario and history disagree on baseline
   magnitude. For chapter-relevant aggregates (warming, exceedance
   probabilities) the transient is small; for species-level PFC plots
   the choice should be flagged.

The takeaway: the brief's "light global harmoniser anchored to 2023
history" produces a defensible SSP2-COM input that agrees with Charlie's
on the macroscale and differs in well-understood ways at the species
level. The two differences above are not in scope to harmonise away;
they are intentional consequences of (a) richer SSP2-COM source data
and (b) a different anchoring choice.

### RCMIP3 canonical-scenario splice and the chapter mapping

The upstream openscm-runner adapters require every scenario to splice
against a canonical RCMIP3 bundle row (Zenodo 20430630) for the historical
emissions, natural forcings (solar + volcanic) and land-use / irrigation
forcings. Chapter pathway IDs flow through the mapping in
`ar7_ch5._rcmip3_naming.canonical_for` so the output ScmRun's `scenario`
column carries the RCMIP3 protocol name:

- ScenarioMIP CMIP7 baselines `VL`..`HL` -> `scen7-VL`..`scen7-HL` (the
  protocol's own labels for the CMIP7 ScenarioMIP categories; the GMD
  paper's short codes are equivalent labels for the same scenarios).
- SCI `SSPx-NN` -> matching CMIP6 SSP-RCP scenario (e.g. `SSP1-19` ->
  `ssp119`, `SSP3-70` -> `ssp370`) -- these are protocol RCMIP3 names
  for what is effectively a re-elicitation of CMIP6 SSP targets.
- `SSP2-com` -> `ssp245` as a documented surrogate (SSP2-COM is the one
  chapter scenario with no RCMIP3 protocol name; the surrogate is
  flagged explicitly and the chapter pathway ID `SSP2-com` is
  preserved on `pathway_id`).
- Idealised runs (`1pctCO2`, `abrupt-2xCO2`, `esm-flat10`, etc.) pass
  through unchanged; they are first-class RCMIP3 protocol names.

The full table and design rationale live in
[engine_upstream_switch.md](engine_upstream_switch.md).

#### ScenarioMIP CMIP7 natural forcings: scenariomip-paper-plots (Zenodo 20329427) is the source of truth

The published RCMIP3 wide CSVs at v2.0.0 do not yet carry rows for
`scen7-*`, so the chapter stages an augmented bundle at data-setup
time (`scripts/build_rcmip3_bundle_augmented.py`; see
[data_setup.md](data_setup.md) section 4a). The augmented bundle
copies the published bundle and inserts:

- Seven `scen7-{cat}` rows in `rcmip_phase3_forcing_v2.0.0.csv` for
  `Effective Radiative Forcing|Natural|Solar` and `|Volcanic`, sourced
  from scenariomip-paper-plots `data/fair-inputs/volcanic_solar.csv`
  (Zenodo 20329427). The GMD-paper natural-forcing time series are
  identical across the seven CMIP7 baselines (as expected -- solar
  and volcanic are externally prescribed in CMIP7).
- Seven `scen7-{cat}` rows in `rcmip_phase3_emissions_v2.0.0.csv`,
  copied from an SSP-RCP donor (`scen7-VL` <- `ssp119`,
  `scen7-L` <- `ssp126`, `scen7-LN` <- `ssp534-over`,
  `scen7-M` <- `ssp245`, `scen7-ML` <- `ssp245`,
  `scen7-H` <- `ssp370`, `scen7-HL` <- `ssp585`). The donor row
  provides pre-overlay historical years on every species and a
  defensible 2025-2500 default for species the chapter does not
  actively vary. The chapter's user emissions (loaded from
  scenariomip-paper-plots, the same Zenodo) overlay this baseline
  for the 23 driven species before the runner passes them to the
  SCMs. Donor choice matches the upstream's
  `_RCMIP3_CMIP7_CATEGORY_TO_SSP` category-to-SSP defaults.

Land-use forcings for `scen7-*` come from the published bundle's
per-category files in `input_datafiles_generation/data/`
(`{vl,l,ln,m,ml,h,hl}_output_concentrations.csv` and the associated
LU albedo CSVs) and resolve automatically through the upstream
runner's `resolve_scenario_category` for any `scen7-{cat}` name.

No chapter-side scenario surrogate or runner monkey-patching is
needed: the augmented bundle puts `scen7-*` rows where the upstream
runner expects them, and an IPCC reviewer can verify the donor
choice + GMD-paper natural forcings by reading the augmented CSV
directly.

#### SCI ensemble pathways and the SSP-family LU concession

Every SCI pathway in an SSP family ends up driven with the **bundle's
row for that family** supplying solar / volcanic / land-use forcings
-- so all ~600 SSP2-* SCI pathways share the bundle's `ssp245` LU +
natural forcings regardless of which IAM produced the pathway. The
original MAGICC SCI runs used SCI-vintage AR6 forcings instead. The
dominant emissions signal still comes from the user's overlay, so
the practical impact on warming outcomes is modest, but the choice
is documented here so any species-level / forcing-level figure flags
it. A full SCI re-run on the upstream pin gives the empirical
magnitude.

#### Audit trail

The output ScmRuns and NetCDFs carry both `scenario` (the canonical
RCMIP3 name -- the bundle row that supplied the splice) and
`pathway_id` (the chapter pathway identifier, e.g. `SSP1-19`, `VL`,
`SSP2-com`) as first-class meta columns, so the audit trail "which
bundle row supplied the splice for this output?" is answerable from
any artefact alone.

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
