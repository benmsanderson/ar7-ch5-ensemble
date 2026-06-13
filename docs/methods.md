# Methods

Methodological reference for the Chapter 5 runs (the AR7 successor to
scenariocompass `docs/APPROACHES.md`). The decision worth stating up front
is how emissions reach the climate models.

## Emissions to the climate models: chapter-owned harmonisation + infilling

The chapter owns harmonisation + infilling end-to-end via a single
`gcages.cmip7_scenariomip`-backed pipeline (the
[`ar7_ch5.harmonisation`](reference/harmonise.md) module). One pipeline
serves SCI, ScenarioMIP CMIP7 and SSP2-COM; per-ensemble specialisation
lives in the raw loaders, not in the pipeline body.

The published per-ensemble sources are read as **raw IAM emissions**
(`Emissions|*` IAMC rows), not as already-harmonised products:

- **SCI 2025** — raw IAM rows from the published xlsx. (The shipped
  `Climate Assessment|Infilled|Emissions|*` namespace is retained as a
  *validation reference* used by `scripts/validate_sci_vs_shipped.py`,
  not as production input.)
- **ScenarioMIP CMIP7** — raw IAM rows from `scenariomip-paper-plots`
  (Zenodo 20329427). A flat-FaIR-name → `CMIP7_SCENARIOMIP` IAMC rename
  is applied at the raw-loader boundary
  (`ar7_ch5.load_scenariomip.flat_to_cmip7_iamc`); `Halon1202` /
  `Halon2402` are stripped before harmonisation and re-supplied by the
  infiller (chapter decision; see open questions).
- **SSP2-COM** — the world-total xlsx already ships in
  `CMIP7_SCENARIOMIP` IAMC convention, so the raw loader is a thin
  normaliser.
- **RCMIP3** — concentration-driven, so the harmonisation pipeline does
  not apply.

The pipeline writes a parquet cache per ensemble at
`data/<ensemble>/cache/<ensemble>_harmonised_infilled.parquet`; the SCM
loaders read those caches. Build them with:

```bash
pixi run python scripts/harmonise.py --ensemble {sci,scenariomip-cmip7,ssp2com}
```

### Pipeline stages

The top-level entry point is `ar7_ch5.harmonisation.harmonise_and_infill`.
Each stage is also exposed as a public helper for unit testing and
walkthroughs (`notebooks/harmonisation_demo.py`):

1. **Annual interpolation.** Sparse-to-annual linear interpolation onto
   a 2023-2100 integer-year grid.
2. **Variable rename to GCAGES.** Maps `CMIP7_SCENARIOMIP` IAMC names
   onto the chapter's GCAGES convention via
   `gcages.renaming.rename_variables`; drops the aggregate parents
   (`Emissions|CO2`, `Emissions|F-Gases`, ...) to avoid duplicates.
3. **History splice.** For each row whose first non-null year `y0 >
   2023`, fills `[2023, y0 - blend_years]` with the chapter history
   year-by-year and linearly blends `(y0 - blend_years, y0)` from the
   history value to the scenario's first value (default `blend_years
   = 5`). Rows whose variable is absent from history are dropped to a
   sidecar CSV.
4. **HFC zero-rounding + non-CO2 negative drop.** Per-cell HFC
   zero-rounding kills numerical noise without destroying decaying
   trajectories; any `(model, scenario)` with a stray negative on a
   non-CO2 species is dropped (recorded in the sidecar).
5. **Aneris harmonisation.** Anchored at 2023 against
   `data/cmip7/history_cmip7_scenariomip.csv` with per-IAM method
   overrides from `data/cmip7/aneris-overrides-global.csv`. Methods
   come from gcages's `create_cmip7_scenariomip_global_harmoniser`.
6. **Infilling.** `RMSClosest` against
   `data/cmip7/infilling_db_cmip7_scenariomip_20566343.csv`, padding
   minor GHGs from `data/cmip7/cmip7_ghg_inversions.csv`. Output is
   the full 52-species `COMPLETE_EMISSIONS_INPUT_VARIABLES_GCAGES`
   driving set.

Variable naming is GCAGES through the body of the chapter; the
openscm-runner adapter rename (GCAGES → OPENSCM_RUNNER) is applied at
the runner boundary by
`ar7_ch5.runners.orchestrate.rename_to_openscm_runner` so the SCMs see
their canonical input names.

### Scientific choices and open questions

The pipeline encodes a number of chapter-owned scientific choices (which
history vintage, which aneris overrides, which infilling DB, infiller
method, Halon treatment, ...). Each is tracked with a status flag
(`DECIDED` / `CONFIGURED-DEFAULT` / `OPEN`) and the reasoning behind it
in
[`docs/harmonisation_open_questions.md`](harmonisation_open_questions.md).
Update that file whenever a choice changes; refresh the golden fixture
parquets in the same commit (so the regression diagnostic catches
unintended drift in the same review).

### Validation diagnostic

`scripts/validate_sci_vs_shipped.py` is a per-species delta report
between the chapter pipeline's SCI output and SCI's shipped
`Climate Assessment|Infilled|Emissions|*` namespace, on the
`(model, scenario, variable)` intersection. It is a *diagnostic*, not
an assertion: the two outputs embed different scientific choices
(chapter history vs SCI's AR6 climate-assessment workflow), so the
question is "how big are the deltas, and is the pattern intelligible?".
The script writes a per-species summary CSV and prints the top-10
species by mean absolute delta at 2100.

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

### Vintage note (no longer applies)

Previously, SCI inputs were lifted from SCI's shipped `Climate
Assessment|Infilled|*` namespace, which is harmonised to the AR6 vintage
(~2015 base, RCMIP), while ScenarioMIP CMIP7 was harmonised to 2023
CMIP7 history. Under the chapter-owned pipeline above, all three
ensembles are now harmonised against the same 2023 anchor
(`data/cmip7/history_cmip7_scenariomip.csv`), so cross-ensemble
comparison is on a single historical baseline by construction.

## AFOLU CO2 convention

For SCM driving, use the physical `Emissions|CO2|AFOLU`, not the
`Emissions|CO2|AFOLU [NGHGI]` (national-inventory) variant, because the SCMs
model the physical carbon cycle.

## Emissions archetypes

`scripts/compute_archetypes.py` reduces the SCI ensemble to a small, legible
grid of representative pathways, one per (emissions strategy, warming class)
cell. It is a deterministic port of the scenariocompass clustering notebooks,
restructured so the archetype list is tuned entirely from JSON rather than from
a random-seeded clustering run.

**Features.** `ar7_ch5.archetype_features` computes, per pathway, six clustering
features (cumulative EIP CO2 2020-2100, CDR fraction, CH4 reduction by 2050,
SO2 in 2050, EIP CO2 in 2050 and 2100, all relative to 2020) plus three
partition-axis fields (cumulative AFOLU CO2, cumulative net CO2 to the net-zero
year, and a post-net-zero `drawdown_band` of `pos`/`nz`/`over`). CO2 integrals
are trapezoidal and converted to Gt CO2 to match the CC-bin thresholds.
ScenarioMIP carries no CCS variable, so its CDR fraction is zero by
construction.

**Strategy labelling.** `ar7_ch5.clustering.fit_clusters` assigns each pathway a
composite `cluster_label` of `{ce_bin}-{drawdown}-{strategy}` (e.g.
`CC1000-nz-cdr`). Every part is a pure threshold function of the features,
declared in `schemes/clustered.json`: `ce_bins` bucket cumulative net CO2,
`drawdown_band` is precomputed, and the dominant `strategy` suffix is the
first firing rule in an ordered priority cascade (`suffix_rules.mode:
dominant`). An occupancy floor (`min_cluster_size`) folds rare archetypes into
their cell's `base` label so the final list stays around a dozen-and-a-half
communicable archetypes. The k-means analysis that originally *chose* these
thresholds is not rerun here; it lives in scenariocompass.

**Representative selection.** `ar7_ch5.archetypes.select_archetypes` fills each
(strategy, GW-class) cell with a single pathway. It prefers a reference
pathway \u2014 SSP2-COM first, then ScenarioMIP CMIP7 \u2014 whose strategy cluster
*and* GW class (from its own classification CSV) both match the cell; ties
break by scenario name. If no reference qualifies, it takes the SCI pathway
nearest the cell centroid in standardised feature space. The `source` and
`selection_rule` columns record which branch was taken. `fig07_archetypes`
colours reference picks with the GMD pathway palette and leaves SCI
nearest-centroid picks white.

## The Chapter 5 contribution

SCI ships MAGICC-only climate outcomes. The value added here is running the same
harmonised emissions through FaIR 2.x and CICERO-SCM as well, giving a genuine
three-SCM ensemble spread on identical inputs.
