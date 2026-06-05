# Data setup

All input data lives under `data/`, which is gitignored. Nothing here is
committed to the repository; this document explains how to obtain each input.
Paths below are relative to the repo root unless stated otherwise.

## Layout

```
data/
  SCI/                 Scenario Compass 2025 ensemble (manual download)
  scenariomip_cmip7/   ScenarioMIP CMIP7 baseline emissions (from scenariomip-paper-plots)
  ssp2com/             SSP2-COM world-total xlsx (from scenariocompass)
  rcmip3_protocol/     RCMIP3 idealised experiment definitions
  sci_csv/             preprocessed SCI CSVs (generated)
```

## 1. SCI 2025 ensemble (manual; access-restricted)

The Scenario Compass database is access-restricted, so the SCI ensemble cannot
be fetched programmatically. Download the most recent global emissions file by
hand from:

    https://download.scenariocompass.org/

and place it at:

    data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx

This file already contains harmonised and infilled, SCM-ready driving emissions
under the `Climate Assessment|Infilled|Emissions|*` namespace (54 species),
produced with the AR6 climate-assessment workflow and run through MAGICC
v7.5.3. We use those directly rather than re-harmonising (see
`docs/methods.md`).

## 2. SSP2-COM world-total (from scenariocompass)

The world-total SSP2-COM file is small (~17 KB, 23 species, World, 2023-2100)
and lives in Ben's scenariocompass repository under `data/ssp2com/`. Drop a
copy or a symlink to:

    data/ssp2com/ssp2-com_world_total.xlsx

The loader reads only the world-total sheet; regional, sectoral, and China
granularities exist in the same scenariocompass directory but are not needed
for the SCM workflow. Pre-2023 history is left to each SCM's bundle /
historical splice; harmonisation to the 2023 history endpoint is done by the
light global harmoniser (see `src/ar7_ch5/harmonise.py` and section 4 below for the history anchor file).

## 3. ScenarioMIP CMIP7 baseline emissions (from scenariomip-paper-plots)

The seven CMIP7 baseline scenarios (VL, L, LN, M, ML, H, HL) ship as a
single CSV in Ben Sanderson's `scenariomip-paper-plots` repository
(github.com/benmsanderson/scenariomip-paper-plots, Zenodo 20329427).
Drop a copy or a symlink to:

    data/scenariomip_cmip7/emissions_1750-2500.csv

The CSV is already harmonised and infilled by the CMIP7 pipeline, so no
harmonisation stage runs here. Year columns are FaIR's half-year offset
convention ("1750.5", ..., "2500.5"); the loader truncates to integer
years and clips to `end_year` (default 2100). The same repository also
defines the run colour / line-style / scenario-naming conventions used in
the GMD paper -- adopt those for any Ch5 figure that shows these
scenarios.

SSP2-COM, the eighth scenario the chapter reports alongside these seven,
is sourced separately from scenariocompass (see section 2).

## 4. RCMIP3 protocol bundle (Zenodo 20430630)

The RCMIP Phase 3 protocol bundle ships three wide-table CSVs (concentrations,
emissions, forcing) covering the 25 RCMIP3 scenarios -- the ECS / TCR / TCRE
idealised set (abrupt-2xCO2, abrupt-4xCO2, 1pctCO2 family, piControl), the
concentration-driven SSP set, and historical attribution variants. v1 of this
repository uses the concentrations CSV only (for the chapter's concentration-
driven RCMIP3 diagnostics). Fetch the bundle from
https://zenodo.org/records/20430630 (single ~37 MB zip), unzip it, and place
or symlink the `RCMIP3_input_datafiles/` subdirectory under:

    data/rcmip3_protocol/RCMIP3_input_datafiles/

The loader accepts either the bundle root, the subdir, or the direct CSV.
On NAC the bundle is already staged at
`/storage/no-backup-nac/users/bensan/rcmip3_protocol/`.

## 5. MAGICC v7.5.3 binary (licensed)

MAGICC is a licensed binary and is not redistributed in this repo. Obtain it
from https://www.magicc.org/ (the v7.5.3 binary plus the AR6 probabilistic
drawnset). Then point the runner at it via an environment variable:

    export MAGICC_EXECUTABLE_7=/path/to/magicc7/bin/magicc

On NAC it is staged at
`/storage/no-backup-nac/users/bensan/magicc-dist/magicc7/bin/magicc`, with the
AR6 drawnset alongside in `magicc-dist/ar6_prob/`. Put the export in your shell
profile or a gitignored `.env.local`.

## 6. Everything else (Zenodo)

The remaining inputs are fetched from their Zenodo archives:

- FaIR 2.x calibration: Zenodo 18828694.
- Global harmonisation history anchor (52 species, World, 1750-2023), used by
  the light SSP2-COM harmoniser: Zenodo 17845154. On NAC this is already
  present under
  `emissions_harmonization_historical/data/processed/history-for-harmonisation/`.

A `scripts/` fetch helper for these will be added with the relevant milestone.
