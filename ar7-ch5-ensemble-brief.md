# Brief: AR7 WG1 Chapter 5 climate runs repository

Workplan for code development of an AR7
WG1 Chapter 5 climate-runs application repository. This brief sets project
context, names the dependencies and source material, proposes a layout, and
lists the open decisions to settle in the first session.

## 1. What this repo is

A user-facing application repository for the climate-model runs and
emissions-based scenario assessment underpinning IPCC AR7 WG1 Chapter 5
(Ben Sanderson, lead author). It runs three simple climate models (FaIR 2.x,
CICERO-SCM v2.1.1, MAGICC) across:

1. The Scenario Compass Initiative 2025 v1.0 ensemble (~1600 IAMC pathways,
   5-yearly to 2100, Huppmann et al. 2026, Zenodo 18598251).
2. The ScenarioMIP CMIP7 baseline scenarios (Van Vuuren et al. 2024). Eight
   scenarios: VL, L, LN, M, ML, H, HL, plus SSP2-COM. Canonical emissions
   source is `scenariomip-paper-plots` (github.com/benmsanderson/scenariomip-paper-plots,
   archived at Zenodo 20329427), which also defines the run colour and
   line-style conventions used in the GMD paper; reuse those for Ch5
   figures.
3. SSP2-COM (community SSP2). Ben's lab archives the world-aggregated
   emissions; regional and sectoral inputs exist upstream but are not needed
   for the SCM workflow.
4. Selected RCMIP3 idealised experiments (concentration-driven,
   fixed-forcing, abrupt-CO2). Requires concentration-driven support in the
   openscm-runner fork (priority #4 on the engine roadmap).

Outputs feed Ch5 figures, the synthesis tables, and the emissions-based
scenario classification scheme.

## 2. Audience and tone

Chapter authors with mixed technical skills will read, run, and possibly
modify this code. The repo must be navigable without reading the source.
Concretely:

- A README that gets a new author from clone to a single scenario run in
  under 10 minutes.
- One canonical entry point per task (`run_scenarios.py`, `classify.py`,
  `make_figures.py`) rather than a maze of notebooks.
- Notebooks reserved for figure generation and exploratory work, never for
  the actual run logic.
- Configuration in plain YAML or TOML files, not buried in code.
- Errors that say what to do, not just what went wrong.
- Do not bullet-proof. If a setup is running with unexpected or wrong
  inputs, raise a clear exception or crash cleanly rather than muddling
  through with try/except bootstrapping.

## 3. Stack

| Layer        | What                                          | Source                                                                |
|--------------|-----------------------------------------------|-----------------------------------------------------------------------|
| SCM engine     | openscm-runner (modernised fork)              | github.com/benmsanderson/openscm-runner, branch `feat/fair2-ciceroscmpy2-adapters-and-runmode` until upstream PRs land |
| FaIR 2.x       | fair >=2.2.4                                  | Calibration zenodo.org/records/18828694                               |
| CICERO-SCM     | ciceroscm 2.1.1                               | github.com/ciceroOslo/ciceroscm; calibration zenodo.org/records/20506399 |
| MAGICC         | pymagicc + licensed MAGICC v7.5.3 binary      | gitlab.com/magicc/magicc; AR6 600-member drawnset                     |
| Post-processing| gcages.ar6.post_processing (no [ar6] extra)   | github.com/openscm/gcages; supplies AR6 anchoring + quantile machinery |
| Scenario IO    | pyam, scmdata                                 | IIASA pyam, ORD scmdata (scmdata stays for v1; see roadmap memory)    |
| Env mgmt       | Pixi                                          | Matches Charlie Koven's ar7_wg1_ch5 convention so authors only learn one tool |

**Separation of concerns with the engine.** openscm-runner is the runner: it
owns the FaIR, CICERO-SCM and MAGICC adapters and the (member, scenario) ->
output mapping. This repository drives: it selects experiments, derives any
inputs that aren't shipped with the source (e.g. irrigation forcing and
land-use albedo, both calculable from `CO2|AFOLU` and the chosen SSP), names
the variables it wants back, and post-processes the result into figures and
the classification. If an SCM does not produce a requested variable, the fix
is upstream (in the SCM or in the runner's adapter); this repo should record
the gap and continue, not crash.

## 4. Source material to port from `scenariocompass`

`~/Documents/Github/scenariocompass` (Ben's exploratory repo) has converged
methodology. Port modules essentially verbatim, with light tidying for the
multi-SCM API.

| scenariocompass path                                 | Action                                                              |
|------------------------------------------------------|---------------------------------------------------------------------|
| `src/load.py`                                        | Port. SCI / ScenarioMIP data loading helpers.                       |
| `src/vetting.py`                                     | Port. Riahi et al. (2026) Table SI.1 basic vetting.                 |
| `src/feasibility.py`                                 | Port. Riahi et al. (2026) Table SI.2 feasibility / sustainability.  |
| `src/classification.py`                              | Port. Riahi et al. (2026) Table SI.3 warming classification, plus Ben's emissions-based extension. |
| `src/climate.py`                                     | Rewrite. Currently calls MAGICC directly; replacement calls openscm-runner across all three SCMs. |
| `schemes/clustered.json`                             | Copy. Three-axis partition + within-cell clustering config.         |
| `scripts/excel_to_csv.py`                            | Port. SCI xlsx-to-csv preprocessing.                                |
| `data/ssp2com/*.xlsx`                                | Bring world-total files. Regional / sectoral / China granularity not needed for this workflow. |
| SSP2-COM ingestion logic embedded in notebooks 02/03/05 | Extract into `src/ar7_ch5/load_ssp2com.py` (world-total xlsx → SCM-driving emissions). |
| `notebooks/01_vetting_and_classification.ipynb`      | Logic ports into `src/`; notebook reduces to a figure-only thin wrapper. |
| `notebooks/02_scenariomip_projection.ipynb`          | PCA projection logic ports into `src/projection.py`.                |
| `notebooks/03_metrics.ipynb`                         | Logic ports into `src/metrics.py`.                                  |
| `notebooks/04_cluster_explore.ipynb`                 | Logic ports into `src/clustering.py`.                               |
| `notebooks/05_archetypes.ipynb`                      | Port archetype selection into `src/archetypes.py`.                  |
| `notebooks/06_views.ipynb`                           | Stays a notebook (figures).                                         |

Expectation: scenariocompass is treated as static source material. No further
changes flow back to it; the AR7 repo becomes the canonical home for these
modules.

## 5. Cross-references (read, do not import wholesale)

- **Charlie Koven's `~/Documents/Github/ar7_wg1_ch5`** (the Ch5 ZOD figures
  repo, FaIR-only, eight scenarios including SSP2-COM). The SSP2-COM
  construction, the 1750-2500 emissions extension methodology, and the FaIR
  setup are worth reading before writing the equivalents here. Specifically:
  `scripts/prepare_ssp2com_for_fair.py` and `scripts/validate_ssp2com.py`
  are the closest existing FaIR-side reference.

- **Shared harmonisation function.** Direction: extract the SSP2-COM
  harmonisation logic into a shared utility that both this repo and Charlie's
  ar7_wg1_ch5 import. First session task is to scope where that utility
  lives (in this repo, in a small standalone package, or upstreamed somewhere
  else), then port Charlie's harmonisation choices into it, with a
  regression test against his current FaIR outputs.

- **Ben's `scenariomip-paper-plots`**
  (github.com/benmsanderson/scenariomip-paper-plots, archived at Zenodo
  20329427). The official reference for ScenarioMIP CMIP7 emissions and the
  canonical figure styling (run colours, line styles, scenario naming) from
  the GMD paper. Use this both as the emissions data source for the
  ScenarioMIP CMIP7 runs and as the styling reference for any Ch5 figure
  that shows those scenarios, so the chapter stays visually consistent with
  the GMD paper.

- **IIASA `climate-assessment`** (github.com/iiasa/climate-assessment). The
  AR6 WGIII pipeline that runs openscm-runner in production. Read to see how
  the runner is actually used downstream.

- **Zebedee Nicholls' `openscm/gcages`**
  (github.com/openscm/gcages). The AR6 successor to climate-assessment:
  harmonisation, infilling, SCM running, post-processing. This repo depends
  on it (no `[ar6]` extra, so aneris / silicone / pymagicc are not pulled
  in); only `gcages.ar6.post_processing` is consumed, which supplies the AR6
  historical anchoring, peak/EOC warming, quantile aggregation and
  exceedance probabilities used by the emissions-based classification path.
  The multi-SCM combination logic we add on top (per-model / pooled / per-
  model-classify-then-aggregate) is a candidate to push upstream eventually.

- **`emissions-harmonisation-historical`**
  (github.com/iiasa/emissions_harmonization_historical, on NAC at
  `/storage/no-backup-nac/users/bensan/emissions_harmonization_historical`).
  Source of the 52-species World 1750-2023 history anchor used by the light
  SSP2-COM harmoniser.

- **Marit Sandstad's `cscm-input-data-generation`**
  (github.com/ciceroOslo/cscm-input-data-generation). CICERO-SCM scenario
  ingestion patterns.

## 6. Proposed layout

```
ar7-ch5-ensemble/
  README.md                     first-author quickstart
  pixi.toml                     single source of truth for env
  data/                         gitignored, see docs/data_setup.md
    excel_original/             SCI xlsx files (from Zenodo)
    sci_csv/                    preprocessed CSVs
    scenariomip_cmip7/          ScenarioMIP baselines
    ssp2com/                    SSP2-COM world-total xlsx (from scenariocompass)
    rcmip3_protocol/            RCMIP3 idealised experiment definitions
  docs/
    data_setup.md               how to get input data onto NAC
    methods.md                  methodological reference (port of scenariocompass docs/APPROACHES.md)
    running_on_nac.md           cluster-specific guidance
  src/ar7_ch5/                  installable package
    __init__.py
    load.py                     SCI / ScenarioMIP loaders (port from scenariocompass)
    load_ssp2com.py             SSP2-COM xlsx -> SCM-ready (extract from scenariocompass nbs)
    harmonise.py                shared harmonisation utilities (with Charlie's repo)
    vetting.py                  port from scenariocompass
    feasibility.py              port from scenariocompass
    classification.py           port from scenariocompass
    runners/
      __init__.py
      fair.py                   FaIR 2.x configuration + run wrapper
      ciceroscm.py              CICERO-SCM 2.1.0 configuration + run wrapper
      magicc.py                 MAGICC configuration + run wrapper
      orchestrate.py            builds (scenario, model, config_chunk) plan, dispatches via openscm-runner
    experiments/
      sci_ensemble.py
      scenariomip_cmip7.py
      ssp2com.py
      rcmip3.py
    metrics.py                  port from scenariocompass notebook 03
    projection.py               port from scenariocompass notebook 02
    clustering.py               port from scenariocompass notebook 04
    archetypes.py               port from scenariocompass notebook 05
    figures.py                  shared figure helpers
  schemes/
    clustered.json              ported from scenariocompass
  scripts/                      canonical command-line entry points
    preprocess_sci.py
    preprocess_ssp2com.py
    run_scenarios.py            single CLI; args select experiment + models
    classify.py
    make_figures.py
  notebooks/                    figure-only, not run logic
    01_vetting_overview.ipynb
    02_emissions_classification.ipynb
    03_three_scm_ensemble.ipynb
    04_rcmip3_diagnostics.ipynb
    05_ssp2com_comparison.ipynb
  tests/
    fixtures/                   small fixture scenarios for fast tests
    test_load.py
    test_vetting.py
    test_classification.py
    test_runners_smoke.py       each SCM produces sane output on one scenario
    test_harmonise.py           regression vs Charlie's SSP2-COM outputs
  .github/
    workflows/                  CI: pytest + ruff on PRs (still to set up)
```

## 7. Workhorse machine

NAC: single-node AMD EPYC 7742, 2 sockets, 64 physical cores per socket
(128 physical, 256 logical with SMT), 2 TB RAM, 2 TB swap. NUMA layout:
node0 = cores 0-63, 128-191; node1 = cores 64-127, 192-255.

Implications:

- Single-node parallelism is sufficient. No cross-node MPI work needed.
- 2 TB RAM means scenario-level memory pressure is unlikely, but a
  streaming / chunked output writer is still wanted because the SCI x
  3-SCM x N-config product is large and accumulating everything in scmdata
  RAM is wasteful.
- NAC is raw shared-login, no SLURM queueing; the worker pool sizes from
  `os.cpu_count()` with a polite cap (12 workers by default). Pin BLAS
  threads to 1 in the environment so the per-process virtual size stays
  small and `fork()` stays within the headroom on the strict-overcommit
  kernel; see `docs/running_on_nac.md` for the trap and the mitigation.
- NUMA-awareness is not worth chasing for v1; revisit if profiling shows
  it matters.

**Machine-agnostic by default, NAC-tuned in docs.** Authors will run this
on laptops, on other shared-login nodes, and possibly on queueable clusters.
The code gauges available cores and memory at launch and adjusts worker
count and chunking accordingly, rather than hardcoding NAC numbers. NAC-
specific guidance (memory-overcommit trap, expected throughput, the
worker-cap default, monitoring patterns) lives in `docs/running_on_nac.md`,
not in the code.

## 8. First milestones

Each milestone is a feature branch with its own PR-style commit, aimed at
being readable by future Ch5 authors.

1. **Scaffold.** Empty layout above, pixi env, CI skeleton, README that
   explains the plan. Pin the openscm-runner fork.
2. **Single-scenario smoke test.** One SCI scenario end-to-end through FaIR
   2.x, CICERO-SCM 2.1.0, MAGICC, on a laptop. Validates the openscm-runner
   fork integration before anything harder.
3. **Port classification.** Vetting, feasibility, classification modules
   from scenariocompass, with tests that regress against scenariocompass
   outputs. No new science.
4. **SCI ensemble batch on NAC.** All ~1600 scenarios through the three
   SCMs, chunked output. First real cluster run.
5. **SSP2-COM ingestion and run.** World-total xlsx -> SCM-driving inputs,
   three-SCM ensemble. Extract shared harmonisation utility, validate
   against Charlie Koven's FaIR-only SSP2-COM output.
6. **ScenarioMIP CMIP7 baseline runs.** Same machinery, different input set.
7. **RCMIP3 idealised experiments.** A capped subset of the RCMIP-III
   protocol (just the experiments Ch5 reports: concentration-driven,
   fixed-forcing, abrupt-CO2); not the full protocol. Requires
   concentration-driven support across the three SCM adapters in the
   openscm-runner fork (FaIR and CICERO-SCM already declare it; MAGICC
   does not yet, see engine roadmap). May land after the SCI work.
8. **Figures.** Notebook-driven figure generation for Ch5 ZOD targets,
   cross-referenced against Charlie Koven's ZOD figures.

**Validation plots and sanity checks land with the milestone that introduces
the data, not gated by milestone 8.** A new pipeline stage should print or
write the simplest diagnostic that lets a reader verify "this looks right"
without re-running the whole batch. M3's per-SCM GW breakdown in
`classify.py --source per_model` is one example.

## 9. Conventions

- **No em-dashes.** Use plain commas, semicolons, parentheses, or sentence
  breaks.
- **No emojis** in code, commits, or docs unless explicitly requested.
- **Additive changes.** Add new modules alongside; do not rewrite working
  ones unless the user asks. Flag scientific choices explicitly before
  committing.
- **Feature branches.** One branch per piece of work, informative commits
  aimed at being readable by future Ch5 authors.
- **Test on real workloads.** Smoke tests against fixtures, but the gating
  check is whether it runs cleanly on NAC with actual SCI input.
- **Flag uncertainty.** If something diverges from a reference
  (scenariocompass, Charlie's FaIR runs), check the ensemble spread or ask
  before claiming the divergence is acceptable.
- **No mocking the SCMs.** Tests hit the real adapters on small inputs.
- **AFOLU choice.** Prefer plain `Emissions|CO2|AFOLU` (physical) over
  `Emissions|CO2|AFOLU [NGHGI]` (political / inventory) for SCM driving.
- **Figure styling for ScenarioMIP scenarios.** Inherit run colours, line
  styles, and scenario naming from `scenariomip-paper-plots` so Ch5 figures
  read consistently with the GMD paper. Lift a shared style module rather
  than re-eyeballing colours.
- **Code maintainability and readability.** Reuse a library's built-in
  functionality before reimplementing it. Follow the linting and docs
  style (`ruff`, brief docstrings). Some problems are better solved
  upstream in the SCM or in openscm-runner; if you suspect that, flag and
  suggest a discussion rather than working around it here. Keep the
  software stack tight; prefer well-maintained standard libraries to
  reduce maintenance and deprecation burden.
- **No in-function imports or in-function sub-functions** unless they
  give a real performance or memory win. Do not use classes unless they
  carry state worth encapsulating: no class-as-paragraph-marker, no test
  classes that don't use `self`.
- **Notebooks tracked as jupytext-paired scripts.** The committed
  artefact is the `.py` percent-format script; the `.ipynb` is generated
  on demand. Keeps diffs reviewable.

## 10. Context the agent should load

Memory files in
`~/.claude/projects/-Users-bensan-Documents-Github-openscm-runner/memory/`:

- `project_openscm_runner_modernisation.md` (engine roadmap)
- `project_ar6_uptake_context.md` (why cluster-friendliness matters)
- `project_ciceroscm_idealised_layers.md` (CICERO-SCM idealised gotchas)
- `project_ciceroscm_historical_bias.md` (bundle vs splice mode)
- `feedback_working_style.md`, `feedback_workflow.md`,
  `feedback_debug_discipline.md` (collaboration norms)
- `feedback_afolu_construct.md` (AFOLU CO2 variable choice)
- `reference_external.md` (upstream model and protocol pointers)

A new project memory should be written at first-session start naming this
repo as the AR7 Ch5 application repo and pointing back to the openscm-runner
fork as the engine.

## 11. Decisions log

### Resolved

1. **Env management:** Pixi. Committed in `pixi.toml`; matches Charlie's
   `ar7_wg1_ch5`.
2. **NAC job scheduling:** raw shared-login, no SLURM. See
   `docs/running_on_nac.md` for the worker-cap and memory-overcommit
   discussion.
3. **MAGICC binary on NAC:** staged at
   `/storage/no-backup-nac/users/bensan/magicc-dist/`, with the AR6
   probabilistic drawnset alongside. The path is set via
   `MAGICC_EXECUTABLE_7` and resolved by the runner; the drawnset path
   has a similar override (`MAGICC_PROBABILISTIC_FILE`). See
   `docs/data_setup.md`. MAGICC setup is an explicit step (license,
   binary, drawnset), not an automatic fetch.
4. **Input data location:** mixed, per `docs/data_setup.md`. The SCI
   xlsx is manually placed under `data/SCI/` (access-restricted, no
   programmatic fetch). The FaIR and CICERO-SCM calibration sets,
   ScenarioMIP CMIP7 emissions, and the global history anchor use an
   override-or-default pattern: a path environment variable points at a
   staged location, defaulting to `data/`; a future `scripts/fetch_*.py`
   helper pulls from Zenodo when missing.

### Open

5. **Shared harmonisation host.** Where the shared SSP2-COM
   harmonisation utility lives: inside this repo (and Charlie imports
   from it), inside Charlie's repo (and this one imports), or a small
   standalone package both depend on. To settle when M5 starts.
6. **Headline source for the emissions-based classification.** Whether
   the chapter's main classification uses per-SCM percentiles with
   MAGICC as headline (B1), pooled across the three SCMs (B2), or
   per-SCM classify-then-aggregate-as-robust (B4). Infrastructure
   exposes all of these as a CLI flag in `scripts/classify.py`
   (`--source xlsx|per_model|pooled`); the choice can wait until the
   full-ensemble comparison is on hand. See memory
   `project_classification_warming_contract`.
7. **CI workflow.** `.github/workflows/` for running at least `pytest`
   and `ruff` on PRs is still to set up.
8. **MAGICC concentration-driven adapter.** Required by milestone 7
   (RCMIP3). FaIR and CICERO-SCM already declare it; MAGICC does not.
   Decision deferred to when M7 starts: wire it in the engine fork
   first, or ship M7 as a FaIR + CICERO ensemble and add MAGICC later.
