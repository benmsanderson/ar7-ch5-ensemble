# Engine switch: fork -> upstream openscm-runner

A scope memo for the refactor that moves our pin from
`benmsanderson/openscm-runner` (fork, branch
`feat/fair2-ciceroscmpy2-adapters-and-runmode`) to
`openscm/openscm-runner` (upstream, branch
`feat/fair2-ciceroscmpy2-adapters-and-runmode-nonfork`).

This document captures what the upstream contract is, the design choice
we have to make on our side, the mapping table for each input set, and
the validation plan. The code changes land on top of this memo on the
same branch (`engine-upstream-switch`).

## The upstream contract (the thing that's changed)

Upstream is 52 commits ahead of the fork, with zero commits behind. Most
of those 52 are CI / coverage churn; the substantive ones (review/pr97
series, merged via PRs #97 / #102 on the runner repo) tighten the
adapter into a **strict canonical RCMIP3 mode**:

- The `FAIR2` and `CICEROSCMPY2` adapters require an `rcmip3_bundle_path`
  argument at construction time -- the Zenodo 20430630 protocol bundle
  supplies historical splice, natural forcings (solar + volcanic), and
  land-use forcing for every scenario.
- Scenarios passed to the adapter **must use canonical RCMIP3 names**
  (`ssp119`, `ssp245`, `ssp370`, `ssp585`, `abrupt-2xCO2`, `1pctCO2`,
  `historical`, etc.). Anything else short-circuits through an empty
  `bundle_df` filter and raises `KeyError 'scenario'` -- by design, not by
  accident.
- "Drop legacy bundle scenario/forcing paths" (commit `3a07afb`) and
  "tighten error handling -- raise instead of warn-and-zero on canonical-
  bundle misses" (`58f6af9`) make this explicit.

The runner is no longer in the business of accepting arbitrary IAM
scenario names. The chapter is. We need to bridge.

## Our design choice

The bridge has to handle three input families that DON'T arrive with
canonical RCMIP3 names:

1. **SCI** (M4): ~1599 IAM pathways like `AIM/CGE 2.0 / SSP1-19`,
   `MESSAGE-iX / SSP2-Baseline`.
2. **SSP2-COM** (M5): `MESSAGE-BASED / SSP2-com`.
3. **ScenarioMIP CMIP7** (M6): `VL, L, LN, M, ML, H, HL`.

And one that does (M7 RCMIP3): `abrupt-2xCO2`, `1pctCO2`, etc. -- pass
through unchanged.

### Where the canonicalisation happens

Three options considered:

| Option | Where | Pro | Con |
|---|---|---|---|
| A | each loader emits canonical names | one place per input | bleeds upstream's naming into our identifiers; downstream (`metrics.py`, `cache.py`, classification CSV, figures) all see `ssp245` instead of `SSP1-19`; chapter authors lose IAM/SSP identity at every step |
| B | `runners/orchestrate.run_models` wraps the call: rename in, call adapter, restore on output | downstream sees our names throughout; only the adapter internals see canonical | small per-call overhead, restore logic must be robust to multi-scenario calls |
| C | side channel via a new `rcmip3_scenario` meta column | preserves both names | upstream doesn't read a side column; would need upstream cooperation |

**Going with (B)**. Loaders keep emitting our natural scenario names;
`run_models` does the rename-call-restore around the adapter. Our
output ScmRun preserves the original scenario column, so `metrics.py`,
`cache.py`, the classification CSV, and the figures don't change.

### What the canonical name actually selects in the bundle

The bundle row for a canonical name supplies:

- Pre-2023 historical emissions for the splice.
- Natural forcing trajectory (solar + volcanic).
- Land-use forcing trajectory.

The user's emissions then overlay the post-2023 region. Our chapter
runs all drive emissions (post-2023), so the canonical choice mainly
controls **which SSP family the historical and natural / LU forcings
come from**.

For the chapter, the SSP-family alignment is the right knob. Most of
our scenarios *are* SSP-family-aligned in their original naming.

## Proposed mapping

| Our scenario | Canonical | Notes |
|---|---|---|
| SCI: `SSP1-19` | `ssp119` | |
| SCI: `SSP1-26`, `SSP1-34` | `ssp126` | |
| SCI: `SSP2-*`, `SSP2-Baseline` | `ssp245` | |
| SCI: `SSP3-*` | `ssp370` | |
| SCI: `SSP4-*` | `ssp460` | |
| SCI: `SSP5-*` | `ssp585` | |
| SSP2-COM: `SSP2-com` | `ssp245` | same as Charlie's anchor SSP |
| ScenarioMIP: `VL` | `ssp119` | closest very-low |
| ScenarioMIP: `L`, `LN` | `ssp126` | low overshoot family |
| ScenarioMIP: `M` | `ssp245` | medium |
| ScenarioMIP: `ML`, `HL` | `ssp370` | medium-high / high-LU |
| ScenarioMIP: `H` | `ssp585` | high |
| RCMIP3 (M7) | pass-through | already canonical |

The mapping lives in a small module (`src/ar7_ch5/_rcmip3_naming.py`)
keyed by regex on the scenario name. Unknown scenarios fall back to
`ssp245` with a NOTE printed.

## What needs to change (rough estimate, ~15 files)

```
pixi.toml                                EDIT  (engine pin -> upstream nonfork)
pixi.lock                                EDIT  (regenerated)
data/rcmip3_protocol/                    PRESENT  (already staged for M7)

src/ar7_ch5/_rcmip3_naming.py            NEW   (mapping + helpers)
src/ar7_ch5/runners/__init__.py          EDIT  (resolve_rcmip3_bundle helper)
src/ar7_ch5/runners/fair.py              EDIT  (pass bundle path through)
src/ar7_ch5/runners/ciceroscm.py         EDIT  (same)
src/ar7_ch5/runners/orchestrate.py       EDIT  (wrap-rename-restore in run_models)

docs/data_setup.md                       EDIT  (note RCMIP3 bundle now mandatory)
docs/methods.md                          EDIT  (Vintage note + LU/natural-forcing concession)
ar7-ch5-ensemble-brief.md                EDIT  (stack table; decisions log)
README.md                                EDIT  (engine reference)

tests/test_rcmip3_naming.py              NEW   (mapping unit tests)
tests/test_runners_smoke.py              EDIT  (verify SSP1-19 -> ssp119 round-trips)
tests/test_*_experiment.py               re-run, no edits expected
```

## Open decisions to settle before code

1. **Mapping granularity for SSP*-Baseline pathways.** `SSP2-Baseline`
   -> `ssp245` is uncontroversial. `SSP1-Baseline` (which is more of a
   reference run than a 1.5C target)?  Default `ssp126` (SSP1-family) or
   `ssp245` (generic baseline)? My lean: `ssp126`.

2. **Land-use / natural forcings concession.** Each SCI pathway in,
   e.g., the SSP2 family ends up with **the same LU + natural forcings
   from the bundle's `ssp245` row**, regardless of which IAM produced
   the pathway. Original MAGICC SCI runs used the SCI-vintage AR6
   forcings instead. This is a real divergence and should land in
   `docs/methods.md` as a note alongside the SCI-vintage caveat. Is
   that acceptable as v1, or do we want to override LU forcings from
   our own input? My lean: acceptable as v1, document the choice.

3. **Output preservation strategy.** Wrap-and-restore in `run_models`
   means downstream sees our names. Confirm this is the right axis to
   pin: chapter authors and figures think in `SSP1-19`, not `ssp119`.

4. **MAGICC**. Still emissions-driven only; the conc-driven model
   filter from M7 already handles this. No change here.

## Validation plan

- Fast suite stays green: 48 passed / 1 skipped.
- `tests/test_rcmip3_naming.py` covers each of the families above and
  the SSP*-Baseline edge cases (TBD per decision 1).
- `tests/test_runners_smoke.py` runs `SSP1-19` through FaIR and CICERO;
  asserts the output's scenario column reads `SSP1-19` (not
  `ssp119`).
- M5, M6, M7 experiment smoke tests pass unchanged.
- Side-by-side: pick one SCI pathway (`AIM/CGE 2.0 / SSP1-19`), run on
  fork and on upstream + canonicalisation, compare GSAT_2100. Expect
  a small delta from LU / natural forcings differing. Document the
  delta in `docs/methods.md`.

## What this PR does NOT do

- It does not change scenario naming in any output or report.
- It does not touch the figure layer.
- It does not re-run the full SCI ensemble. The post-switch full re-run
  is a follow-up (and a multi-day batch).

## Open question for review

Sign-off on the mapping table (especially Baseline rows), the LU /
natural-forcings concession, and the wrap-and-restore strategy. After
that the implementation is ~mechanical.
