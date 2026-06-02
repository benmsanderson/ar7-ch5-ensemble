# Data setup

All input data lives under `data/`, which is gitignored. Nothing here is
committed to the repository; this document explains how to obtain each input.
Paths below are relative to the repo root unless stated otherwise.

## Layout

```
data/
  SCI/                 Scenario Compass 2025 ensemble (manual download)
  scenariomip_cmip7/   ScenarioMIP CMIP7 baseline emissions (Zenodo)
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

## 2. MAGICC v7.5.3 binary (licensed)

MAGICC is a licensed binary and is not redistributed in this repo. Obtain it
from https://www.magicc.org/ (the v7.5.3 binary plus the AR6 probabilistic
drawnset). Then point the runner at it via an environment variable:

    export MAGICC_EXECUTABLE_7=/path/to/magicc7/bin/magicc

On NAC it is staged at
`/storage/no-backup-nac/users/bensan/magicc-dist/magicc7/bin/magicc`, with the
AR6 drawnset alongside in `magicc-dist/ar6_prob/`. Put the export in your shell
profile or a gitignored `.env.local`.

## 3. Everything else (Zenodo)

The remaining inputs are fetched from their Zenodo archives:

- ScenarioMIP CMIP7 emissions and figure styling: scenariomip-paper-plots,
  Zenodo 20329427.
- FaIR 2.x calibration: Zenodo 18828694.
- Global harmonisation history anchor (52 species, World, 1750-2023), used by
  the light SSP2-COM harmoniser: Zenodo 17845154. On NAC this is already
  present under
  `emissions_harmonization_historical/data/processed/history-for-harmonisation/`.

A `scripts/` fetch helper for these will be added with the relevant milestone.
