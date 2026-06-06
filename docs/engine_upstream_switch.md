# Engine switch: fork -> upstream openscm-runner

A scope memo for the refactor that moves our pin from
`benmsanderson/openscm-runner` (fork, branch
`feat/fair2-ciceroscmpy2-adapters-and-runmode`) to
`openscm/openscm-runner` (upstream, branch
`feat/fair2-ciceroscmpy2-adapters-and-runmode-nonfork`). The upstream
branch is 52 commits ahead of the fork and represents the design Zeb has
settled on: strict canonical RCMIP3 scenario names. The chapter has to
bridge.

Beyond the engine switch itself, the refactor reshapes how chapter
scenarios reach the SCMs. The driving constraint is **traceability for
IPCC review**: every output artefact has to make it obvious, without
consulting a sidecar table, which RCMIP3 bundle row supplied the
historical / natural / land-use forcings AND which chapter pathway the
result belongs to. The chosen design carries both names as first-class
data through the entire pipeline.

## The upstream contract

Upstream's 52-commit lead over the fork is mostly CI / coverage churn,
but the substantive series (review/pr97, merged via PRs #97 / #102 on
the runner repo) tightens the FaIR2 and CICEROSCMPY2 adapters into a
**strict canonical RCMIP3 mode**:

- The `FAIR2` and `CICEROSCMPY2` adapters require an `rcmip3_bundle_path`
  argument at construction time -- the Zenodo 20430630 protocol bundle
  supplies historical splice, natural forcings (solar + volcanic), and
  land-use forcing for every scenario.
- Scenarios passed to the adapter **must use canonical RCMIP3 names**
  (`ssp119`, `ssp245`, `ssp370`, `ssp585`, `abrupt-2xCO2`, `1pctCO2`,
  `historical`, ...). Anything else short-circuits through an empty
  `bundle_df` filter and raises `KeyError 'scenario'` -- by design, not
  by accident. The commits "Drop legacy bundle scenario/forcing paths"
  (`3a07afb`) and "tighten error handling -- raise instead of warn-and-
  zero on canonical-bundle misses" (`58f6af9`) make this explicit.

The runner is no longer in the business of accepting arbitrary IAM
scenario names. The chapter is.

## Design: two-column representation, no hidden translation

The chapter's input sets do not arrive with canonical RCMIP3 names:

1. **SCI** (M4): ~1599 IAM pathways like `AIM/CGE 2.0 / SSP1-19`,
   `MESSAGE-iX / SSP2-Baseline`.
2. **SSP2-COM** (M5): `MESSAGE-BASED / SSP2-com`.
3. **ScenarioMIP CMIP7** (M6): `VL, L, LN, M, ML, H, HL`.
4. **RCMIP3** (M7): `abrupt-2xCO2`, `1pctCO2`, ... (pass through; already
   canonical).

A reviewer reading any output artefact -- a NetCDF, the SCI batch
`manifest.csv`, a classification CSV, a figure caption -- has to be able
to answer two questions from the artefact alone:

1. **Which RCMIP3 bundle row supplied the splice?** (`scenario=ssp245`
   means the bundle's `ssp245` row provided solar / volcanic / land-use
   forcings and pre-2023 historical emissions.)
2. **Which chapter pathway is this?** (`pathway_id=SSP1-19` is the SCI
   input, the figure label, the classification key.)

Both names persist as first-class meta columns from the loader through
to every output. No rename-on-the-fly inside the orchestrator; no
sidecar dictionaries; no surprise translation visible only at debug
time. The mapping is one explicit table in `src/ar7_ch5/_rcmip3_naming.py`
that an IPCC reviewer can audit.

### Loader contract

Each loader (`load.py`, `load_ssp2com.py`, `load_scenariomip.py`,
`load_rcmip3.py`) emits a :class:`scmdata.ScmRun` whose meta carries:

- `scenario`: the canonical RCMIP3 name. This is what the adapter
  splices against.
- `pathway_id`: the chapter-meaningful identifier. This is what figures,
  the SCI batch manifest, `metrics.py`, `cache.py`, and post-processing
  index by.
- `model`: the IAM (SCI, SSP2-COM, ScenarioMIP) or `RCMIP3` (M7). This
  layer is unchanged.

For RCMIP3 the two columns are identical (the chapter pathway IS the
canonical name) -- intentional, harmless, keeps consumers uniform.

### Filename convention

Per-pathway NetCDFs are named on `pathway_id`, not on `scenario`:

    outputs/sci/<scm>/sci_<iam>_<pathway_id>.nc
    outputs/scenariomip_cmip7/<scm>/scenariomip_<pathway_id>.nc
    outputs/rcmip3/<scm>/rcmip3_<pathway_id>.nc

This avoids the collision SCI would suffer otherwise: `SSP1-26` and
`SSP1-34` both map to `scenario=ssp126`, so a `scenario`-keyed filename
would clobber. `pathway_id`-keyed filenames are unique by construction.

## Mapping table

Every entry on the right is a real RCMIP3 protocol name (member of
`scenario_info` in the bundle's `rcmip_phase3_protocol_v2.0.0.xlsx`)
that an IPCC reviewer can look up directly in the published bundle.

| Chapter pathway | RCMIP3 canonical `scenario` | Notes |
|---|---|---|
| SCI: `SSP1-19` | `ssp119` | direct family-target match |
| SCI: `SSP1-26` | `ssp126` | direct family-target match |
| SCI: `SSPx-NN` (no direct) | `ssp{family}` family default | e.g. `SSP2-19` -> `ssp245`; `SSP3-26` -> `ssp370` |
| SCI: `SSP1-Baseline` | `ssp126` | SSP-family default |
| SCI: `SSP2-Baseline` | `ssp245` | |
| SCI: `SSP3-Baseline` | `ssp370` | |
| SCI: `SSP4-Baseline` | `ssp460` | |
| SCI: `SSP5-Baseline` | `ssp585` | |
| SSP2-COM: `SSP2-com` | `ssp245` | documented surrogate (no protocol name for SSP2-COM) |
| ScenarioMIP CMIP7: `VL` | `scen7-VL` | protocol name for the CMIP7 ScenarioMIP "very low" category |
| ScenarioMIP CMIP7: `L` | `scen7-L` | |
| ScenarioMIP CMIP7: `LN` | `scen7-LN` | |
| ScenarioMIP CMIP7: `M` | `scen7-M` | |
| ScenarioMIP CMIP7: `ML` | `scen7-ML` | |
| ScenarioMIP CMIP7: `H` | `scen7-H` | |
| ScenarioMIP CMIP7: `HL` | `scen7-HL` | |
| RCMIP3 (M7): `1pctCO2`, `abrupt-2xCO2`, `esm-flat10`, ... | same | pass through (already protocol names) |

Unmapped chapter pathways fall to `ssp245` with a NOTE printed -- the
neutral choice. The mapping is one named function in
`src/ar7_ch5/_rcmip3_naming.py`; no regex magic, no implicit rules.

### scen7-{cat} canonical CSV coverage at v2.0.0

The published RCMIP3 wide CSVs at v2.0.0 only carry rows for the
SSP-RCP family + `historical`/`historical-cmip6`; the `scen7-*`
protocol names are listed in the protocol scenario sheet and shipped
as per-category source files in `input_datafiles_generation/data/`
but not aggregated into the canonical wide tables. The upstream
openscm-runner raises `KeyError` on a missing scenario row.

To close that packaging gap without modifying the upstream runner or
the published bundle, the chapter stages an augmented bundle at
data-setup time (`scripts/build_rcmip3_bundle_augmented.py`):

- Seven `scen7-{cat}` Solar + Volcanic rows inserted in
  `rcmip_phase3_forcing_v2.0.0.csv`, sourced from
  scenariomip-paper-plots (Zenodo 20329427,
  `data/fair-inputs/volcanic_solar.csv`).
- Seven `scen7-{cat}` emissions rows inserted in
  `rcmip_phase3_emissions_v2.0.0.csv`, copied from an SSP-RCP donor
  per category (see [methods.md](methods.md) for the donor table).

The augmented bundle lives at `data/rcmip3_protocol_augmented/`,
preferred by `resolve_rcmip3_bundle()` over the vanilla bundle. With
this in place the upstream openscm-runner sees `scen7-*` rows
exactly as it sees SSP-RCP rows -- no scenario surrogate or
swap-and-restore is needed in the chapter or the runner. See
[data_setup.md](data_setup.md) section 4a for the build step.

## What changes (file by file)

```
pixi.toml                                EDIT  pin upstream/feat/...-nonfork
pixi.lock                                EDIT  regenerated
data/rcmip3_protocol/                    PRESENT  vanilla bundle (Zenodo 20430630)
data/rcmip3_protocol_augmented/          BUILT  by scripts/build_rcmip3_bundle_augmented.py

scripts/build_rcmip3_bundle_augmented.py NEW   stages augmented bundle with scen7-* rows

src/ar7_ch5/_rcmip3_naming.py            NEW   the mapping table (protocol names on canonical column)
src/ar7_ch5/runners/__init__.py          EDIT  resolve_rcmip3_bundle prefers augmented bundle
src/ar7_ch5/runners/fair.py              EDIT  pass bundle path
src/ar7_ch5/runners/ciceroscm.py         EDIT  pass bundle path
src/ar7_ch5/runners/orchestrate.py       EDIT  attach_pathway_id helper after engine call

src/ar7_ch5/load.py                      EDIT  emit pathway_id + scenario=canonical
src/ar7_ch5/load_ssp2com.py              EDIT  same
src/ar7_ch5/load_scenariomip.py          EDIT  same (canonical = scen7-{cat})
src/ar7_ch5/load_rcmip3.py               EDIT  emit pathway_id (= scenario)

src/ar7_ch5/experiments/sci_ensemble.py  EDIT  pathway_id filenames + manifest col + per-pathway runs
src/ar7_ch5/experiments/ssp2com.py       EDIT  pathway_id filename
src/ar7_ch5/experiments/scenariomip_cmip7.py EDIT  pathway_id filename
src/ar7_ch5/experiments/rcmip3.py        EDIT  pathway_id filename (= scenario)

src/ar7_ch5/metrics.py                   EDIT  index pathways by pathway_id
src/ar7_ch5/cache.py                     EDIT  expected names from pathway_id

docs/data_setup.md                       EDIT  RCMIP3 bundle mandatory + augmented build step
docs/methods.md                          EDIT  mapping + scen7 natural-forcings source
ar7-ch5-ensemble-brief.md                EDIT  stack table; decisions log
README.md                                EDIT  engine reference

tests/test_rcmip3_naming.py              NEW   mapping unit tests
tests/test_load_*.py                     EDIT  assert both columns present + correct
tests/test_*_experiment.py               EDIT  per-pathway NCs land with chapter id
tests/test_runners_smoke.py              EDIT  SSP1-19 input -> SSP1-19 in output meta
tests/test_metrics_smoke.py              EDIT  identity via pathway_id
tests/test_cache.py                      EDIT  pathway_id-based expected names
```

~20 files. The orchestration / `run_models` layer is unchanged --
loaders do the canonicalisation, downstream consumers read
`pathway_id`. No hidden translation.

## SCI LU / natural-forcings concession

Every SCI pathway in an SSP family ends up with the **bundle's row
for that family** supplying solar / volcanic / land-use forcings. For
SCI specifically, all ~600 SSP2-* pathways share the bundle's `ssp245`
LU + natural forcings, regardless of which IAM produced the pathway.

This is a real divergence from the original MAGICC SCI runs (which used
SCI-vintage AR6 forcings). The dominant emissions signal still comes
from the user's overlay, so the practical impact on warming outcomes is
modest, but the concession is documented in `docs/methods.md` alongside
the existing SCI-vintage caveat. The full SCI re-run on the new pin
provides the empirical magnitude.

The ScenarioMIP CMIP7 set does NOT carry this concession: each
`scen7-{cat}` pathway gets the GMD-paper natural forcings (from the
augmented bundle's `volcanic_solar.csv` source) and the bundle's per-
category land-use rows, both via the protocol-name canonical row.

## Validation plan

- Fast suite stays green (48 passed / 1 skipped baseline).
- `tests/test_rcmip3_naming.py` covers the mapping table family by
  family + the SSP*-Baseline edge cases (the Open question above).
- `tests/test_load_*.py` assert each loader's output ScmRun carries
  `scenario` (canonical) and `pathway_id` (chapter) columns with the
  right values.
- `tests/test_runners_smoke.py` runs `SSP1-19` end-to-end and asserts
  the output's `pathway_id` reads `SSP1-19` and `scenario` reads
  `ssp119`. Filename matches `sci_AIM-CGE-2.0_SSP1-19.nc`.
- M5 / M6 / M7 smoke tests run unchanged; their assertions on filenames
  and shapes get updated to `pathway_id` naming.
- Side-by-side: pick one SCI pathway, run on fork and on new pin,
  compare GSAT_2100. Document the delta in `docs/methods.md`.

## Out of scope

- Full SCI ensemble re-run (multi-day batch; follow-up).
- Renaming scenarios in any chapter narrative (the chapter pathway
  names remain SSP1-19 etc.).
- Touching the figure layer or M3 classification (both already key on
  chapter identity from the SCI xlsx, not from SCM outputs).

## Locked decisions

| # | Decision | Resolution |
|---|---|---|
| 1 | SSP1-Baseline mapping | `ssp126` (SSP-family default) |
| 2 | SCI LU / natural-forcings concession | document in `methods.md`; accept as v1 |
| 3 | Naming approach | **two-column representation** (`scenario` canonical + `pathway_id` chapter); no hidden translation in orchestration |
| 4 | ScenarioMIP CMIP7 canonical name | `scen7-{cat}` per the RCMIP3 protocol; **not** an SSP-RCP surrogate |
| 5 | ScenarioMIP CMIP7 natural forcings | scenariomip-paper-plots `volcanic_solar.csv` (Zenodo 20329427), staged into the augmented bundle by `scripts/build_rcmip3_bundle_augmented.py` |
| 6 | ScenarioMIP CMIP7 emissions baseline | SSP-RCP donor copy per category, overlaid by chapter user emissions |
