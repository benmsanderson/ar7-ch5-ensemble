# Harmonisation + infilling: chapter choices and open questions

This is the durable record of the chapter-owned harmonisation and infilling
pipeline (PR replacing the SCI "lift shipped infilled" path, the
ScenarioMIP CMIP7 FaIR-named pre-harmonised path, and the SSP2-COM
light-convergence path with a single
`gcages.cmip7_scenariomip`-backed pipeline). Each entry pairs **the
chapter's current choice** with **why** and any **open question** for
Zeb / Chris / Marit. Entries are added as new choices surface; resolved
ones move to the bottom.

## Status legend

- **DECIDED** -- choice made, in code, no further action needed.
- **CONFIGURED-DEFAULT** -- choice made but should be revisited; configuration
  exists so a different default can be wired without code change.
- **OPEN** -- choice not made; PR ships with a stop-gap that is wrong-enough
  to need follow-up.

## Pipeline architecture

The chapter takes ownership of harmonisation + infilling rather than
inheriting them from SCI's `Climate Assessment|Infilled|Emissions|*`
namespace. One pipeline serves SCI, ScenarioMIP CMIP7, and SSP2-COM.

Stages:

1. drop scenarios starting after the chapter anchor year;
2. linear interpolate sparse year columns onto annual;
3. rename `CMIP7_SCENARIOMIP` -> `GCAGES`, drop aggregate parents,
   strip pint-incompatible chars from units;
4. round near-zero HFCs to zero; drop scenarios with negative non-CO2;
5. global Aneris harmonisation
   (`gcages.cmip7_scenariomip.create_cmip7_scenariomip_global_harmoniser`);
6. infilling (`gcages.cmip7_scenariomip.CMIP7ScenarioMIPInfiller`).

Naming convention is GCAGES through the body of the repo; the openscm-runner
adapter rename is applied at the runner boundary.

## Per-ensemble choices

### SCI 2025 (Huppmann et al. 2026, Zenodo 18598251)

- **Input:** raw `Emissions|*` rows from the published xlsx, not the
  `Climate Assessment|Infilled|*` namespace.
- **DECIDED.**

### ScenarioMIP CMIP7 (Van Vuuren et al. 2024, Zenodo 20329427)

- **Input:** `emissions_1750-2500.csv` from `scenariomip-paper-plots`,
  with a flat-FaIR-name -> `CMIP7_SCENARIOMIP` IAMC rename applied at the
  raw loader (see `ar7_ch5.load_scenariomip.flat_to_cmip7_iamc`). Half-year
  time stamps truncated to integer years.
- **Halons.** `Emissions|Halon1202` and `Emissions|Halon2402` are stripped
  from the raw input before harmonisation and re-supplied by the infiller
  from the inversion history. IAM submissions ship non-zero values at 2023
  but the chapter history has these as zero; aneris cannot reconcile the
  two while landing exactly on history. Stripping + infill is the cleanest
  resolution and treats Halons consistently with other infillable species.
  **DECIDED** (was Q1).

### SSP2-COM (Charlie Koven world-total xlsx)

- **Input:** `data/ssp2com/ssp2-com_world_total.xlsx`, already in
  `CMIP7_SCENARIOMIP` IAMC convention.
- **Aneris overrides.** A `MESSAGE-BASED` block in
  `data/cmip7/aneris-overrides-global.csv` is a verbatim copy of the
  `AIM 3.0` block (23 species, mostly `reduce_ratio_2080` with the usual
  `constant_ratio` HFC125/HFC23/HFC32, `reduce_offset_2150_cov` for the
  CO2|AFOLU sector and HFC43-10, and `constant_ratio` for the persistent
  PFCs). Picked because AIM is one of the three fully-covered IAMs and
  has a conservative method mix; the chapter should review these with
  Charlie before SOD. **CONFIGURED-DEFAULT** (was Q2).
- **History anchor.** Reuses the same `history_cmip7_scenariomip.csv` as
  SCI and ScenarioMIP CMIP7. **DECIDED** (Charlie's separate history is *not*
  used as the v1 anchor).

## Scientific choices common to all three ensembles

### Infilling database

- **Choice:** `infilling_db_cmip7_scenariomip_20566343.csv` (the CMIP7
  ScenarioMIP submissions DB, Zenodo 20566343).
- **CONFIGURED-DEFAULT** (was Q3). Zeb flagged this as a stop-gap in PR
  reference; a better candidate before SOD is open. Candidates to evaluate:
  AR6 climate-assessment infilling DB; a chapter-built DB.

### Infiller method

- **Choice:** `RMSClosest` (the gcages default).
- **CONFIGURED-DEFAULT** (was Q4). gcages exposes `direct_copy`,
  `direct_scaling`, `pre_industrial_aware_direct_scaling`, `silicone_based`.
  Choice should be revisited explicitly before SOD.

### CO2|EIP reaggregation

- IAMs publish `Emissions|CO2|Energy and Industrial Processes`
  inconsistently (some report directly, some need re-aggregation from
  sub-sectors).
- **OPEN** (was Q5). For FOD: pass through whatever each IAM publishes.
  For SOD: per-IAM audit + reaggregation pass.

### Late-starting scenarios

- **Choice:** for each row whose first non-null year `y0 > 2023`, splice
  the chapter history into `[2023, y0 - blend_years]` and linearly blend
  from `history(y0 - blend_years)` to `scenario(y0)` across the blend
  window. Default `blend_years = 5`. Rows whose variable is absent from
  history are dropped and recorded in the drops sidecar.
- **DECIDED** (was Q6). Implemented as
  `ar7_ch5.harmonisation.splice_late_starting_from_history`; the legacy
  `drop_late_starting_scenarios` helper stays for callers wanting strict
  drops but is not on the default pipeline.

### Non-CO2 negative values

- **Choice:** HFCs that round to zero at 3 decimals are forced to exact
  zero; any (model, scenario) with a stray negative value on any non-CO2
  species is dropped entirely.
- **Logging:** dropped (model, scenario) pairs (both late-start and
  non-CO2-negative) are written to a sidecar CSV next to the output
  parquet:
  `{cache_dir}/{ensemble}_harmonised_infilled.dropped.csv`.
- **DECIDED** (was Q7). Per-pathway dropping is intentionally coarse for
  v1; per-variable handling can be revisited if the dropped set is large
  enough to matter for chapter coverage.

## Technical / pipeline defaults

### `check_hash` on the gcages history loader

- **Choice:** `False` by default; expose `--check-hash` on the CLI for
  contexts where the exact Zenodo revision matters.
- **DECIDED** (was Q9). History will churn between FOD and SOD; CI must
  not break on an upstream hash bump.

### Multiprocessing worker count

- **Choice:** harmonisation defaults to 36 workers (cap raised from the
  chapter's general `DEFAULT_MAX_WORKERS = 12`, which is sized for SCM
  forking under NAC's overcommit constraint). SCM runs stay at 12.
- **DECIDED** (was Q10).

### Validation diagnostic vs SCI's shipped infilled namespace

- A regression diagnostic compares our harmonised+infilled SCI output
  against SCI's shipped `Climate Assessment|Infilled|*` rows on common
  pathways and species, reporting mean / max deltas. Not an assertion --
  a chapter signal that we have or have not drifted from the community
  choices unintentionally.
- **DECIDED** (was Q8). Ships with this PR.

### Golden fixtures

- SCI: 2-pathway slice committed at
  `tests/fixtures/sci_harmonised_infilled_tiny.parquet`.
- SSP2-COM: 1-pathway slice at
  `tests/fixtures/ssp2com_harmonised_infilled_tiny.parquet`.
- SMIP CMIP7: 7-pathway slice at
  `tests/fixtures/scenariomip_cmip7_harmonised_infilled_tiny.parquet`
  (added after the Halon strip lands).
- **DECIDED** (was Q11). Refresh the fixtures intentionally when a
  chapter scientific choice changes (and document the change in this
  file); never refresh to mask an unexpected diff.

### HFC near-zero cleanup (per-cell, not per-row)

- **Choice:** for HFC rows, individual cells that round to zero at
  3 decimals are forced to exact zero. Differs from Zeb's reference
  notebook which uses per-row zeroing (any single zero year zeroes the
  whole HFC trajectory) -- that variant silently wipes legitimate HFC
  trajectories that decay toward zero by 2100 (e.g. SMIP CMIP7 HFC23
  in VL pathway).
- **DECIDED**. Caught during SMIP CMIP7 smoke run.

## Resolved

(Empty until first round of follow-ups merges.)
