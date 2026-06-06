# AR7 WG1 Chapter 5 climate runs

Runs three simple climate models (FaIR 2.x, CICERO-SCM 2.1.2, MAGICC v7.5.3)
across the Chapter 5 scenario sets and produces the emissions-based scenario
classification, synthesis tables, and figures for IPCC AR7 WG1 Chapter 5.

This repository is meant to be navigable without reading the source. There is
one canonical command-line entry point per task; notebooks are reserved for
figures. The full plan, porting map, and conventions are in
[ar7-ch5-ensemble-brief.md](ar7-ch5-ensemble-brief.md).

> Status: M1-M7 complete (smoke runs, SCI ensemble batch on NAC, vetting /
> feasibility / classification port, SSP2-COM ingestion + harmoniser,
> ScenarioMIP CMIP7, RCMIP3 concentration-driven diagnostics). M8 figures
> is in scaffold + first-figure form -- jupytext-paired figure scripts,
> YAML-driven configuration, a read-only cache reporter, and `fig01`
> wired end-to-end. See the milestone list in
> [ar7-ch5-ensemble-brief.md](ar7-ch5-ensemble-brief.md) section 8.

## Scenario sets

1. Scenario Compass Initiative 2025 ensemble (~1600 IAMC pathways).
2. ScenarioMIP CMIP7 baselines (VL, L, LN, M, ML, H, HL, plus SSP2-COM).
3. SSP2-COM (community SSP2), world-total.
4. Selected RCMIP3 idealised experiments.

## Quickstart

The environment is managed entirely by [Pixi](https://pixi.sh).

```bash
# 1. Build the environment (pins the openscm-runner fork; first run is slow).
pixi install

# 2. Get input data. See docs/data_setup.md. At minimum, place the SCI xlsx:
#    data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx
#    and, for MAGICC, export the binary path:
#    export MAGICC_EXECUTABLE_7=/path/to/magicc7/bin/magicc

# 3. See the run interface.
pixi run python scripts/run_scenarios.py --help

# 4. Run the tests.
pixi run test

# 5. Run one experiment end-to-end (FaIR-only smoke, ~10 s).
pixi run python scripts/run_scenarios.py \
    --experiment ssp2com --models fair --n-members 5

# 6. Run vetting + feasibility + classification on the SCI ensemble (~5 min).
pixi run python scripts/classify.py --source xlsx

# 7. Build the figures registered in schemes/figures.yaml.
pixi run python scripts/make_figures.py --all
```

## Engine

The SCM engine is the upstream openscm-runner feature branch hosting the
modernised FaIR2 / CICEROSCMPY2 adapters and the strict canonical RCMIP3
splice path (github.com/openscm/openscm-runner, branch
`feat/fair2-ciceroscmpy2-adapters-and-runmode-nonfork`), pinned in
`pixi.toml` until those PRs land on main. This repository is the
*application*; the runner is the *engine*. Chapter pathway IDs flow
through a chapter-side mapping to the matching RCMIP3 protocol name on
the `scenario` meta column (ScenarioMIP CMIP7 -> `scen7-{cat}`, SCI ->
`ssp{x}{NN}`, idealised pass-through, SSP2-COM as a documented
surrogate), while the chapter pathway identifier is preserved on a
parallel `pathway_id` meta column; see
[docs/engine_upstream_switch.md](docs/engine_upstream_switch.md). The
`scen7-*` natural-forcing rows are added at data-setup time by
`scripts/build_rcmip3_bundle_augmented.py` from
scenariomip-paper-plots (Zenodo 20329427); see
[docs/data_setup.md](docs/data_setup.md) section 4a.

## How emissions reach the models

Three of the four input sets arrive already harmonised and infilled, so this
repository does not carry a harmonisation/infilling stack. SCI ships SCM-ready
driving emissions (`Climate Assessment|Infilled|Emissions|*`); ScenarioMIP
CMIP7 is harmonised by the CMIP7 pipeline; only SSP2-COM is harmonised here, by
a light global harmoniser anchored to a published 2023 history. See
[docs/methods.md](docs/methods.md) for details and the SCI-vintage caveat.

## Building figures

Three CLIs in a chain; each is read-only on the layer below it:

```
scripts/cache_status.py    reports which ensemble outputs / CSVs are present
scripts/run_scenarios.py   produces SCM ensemble NetCDFs (per experiment)
scripts/classify.py        produces classification CSVs (per source)
scripts/make_figures.py    reads the cached outputs, writes PNG / PDF
```

`cache_status.py` is the entry point for "what do I need to run before this
figure works?". For every (experiment, SCM) it lists present / expected
counts and prints the exact `run_scenarios.py` command beside each missing
piece. `make_figures.py` calls into the same enumerator and fails early with
a clear `FileNotFoundError` if a required input is missing, so iteration
stays fast and the figure layer never silently runs an SCM.

Each figure is a jupytext-paired `notebooks/figXX_*.py` (percent format).
The `.py` is the tracked source of truth; the `.ipynb` is generated on demand
and gitignored. Open the `.py` in JupyterLab to use it as a notebook; run
`python notebooks/figXX_*.py` or `make_figures.py --figure figXX_*` to
produce the output files. Per-figure spec lives in
[schemes/figures.yaml](schemes/figures.yaml), shared palettes and DPI / font
defaults in [schemes/style.yaml](schemes/style.yaml).

Figures land under `outputs/figures/`. Adding a figure is two steps: a new
`notebooks/figXX_*.py` and a new entry in `schemes/figures.yaml` keyed by
the same id.

## Layout

```
pixi.toml             single source of truth for the environment
jupytext.toml         pairing config for notebooks/ figure scripts
pyproject.toml        installable package metadata
src/ar7_ch5/          the package
  load*.py            per-input loaders (SCI, SSP2-COM, ScenarioMIP, RCMIP3)
  harmonise.py        light global SSP2-COM harmoniser (anchor to 2023 history)
  vetting.py          Riahi 2026 Table SI.1
  feasibility.py      Table SI.2 (feasibility + sustainability)
  classification.py   Table SI.3 (GW0-GW8) + emissions-based extension
  metrics.py          warming metrics over the 3-SCM ensemble NetCDFs
  cache.py            read-only enumerator (expected vs present per experiment)
  figures.py          config / style / save helpers for figure scripts
  runners/, experiments/
scripts/              canonical command-line entry points
  run_scenarios.py    select experiment + models, run the SCMs
  classify.py         vetting + feasibility + sustainability + classification
  cache_status.py     report present / missing ensemble outputs
  make_figures.py     dispatch jupytext-paired figure scripts
docs/                 data_setup.md, running_on_nac.md, methods.md
schemes/              YAML configs
  figures.yaml        per-figure spec (experiment, source, output formats)
  style.yaml          shared palettes and DPI / font defaults
notebooks/            jupytext-paired figure scripts (figXX_*.py tracked,
                      figXX_*.ipynb gitignored)
tests/                fixtures + tests (real adapters, no SCM mocking)
data/                 gitignored; obtain per docs/data_setup.md
outputs/              gitignored; per-experiment NetCDFs, classification CSVs,
                      and figures/figXX_*.{png,pdf}
```

## Conventions

See the brief, section 9. In short: additive changes (do not rewrite working
modules unless asked), feature branches with author-readable commits, tests hit
the real SCM adapters on small inputs (no mocking), drive with physical
`Emissions|CO2|AFOLU`, and flag any scientific divergence from a reference
before treating it as acceptable.
