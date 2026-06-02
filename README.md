# AR7 WG1 Chapter 5 climate runs

Runs three simple climate models (FaIR 2.x, CICERO-SCM 2.1.0, MAGICC v7.5.3)
across the Chapter 5 scenario sets and produces the emissions-based scenario
classification, synthesis tables, and figures for IPCC AR7 WG1 Chapter 5.

This repository is meant to be navigable without reading the source. There is
one canonical command-line entry point per task; notebooks are reserved for
figures. The full plan, porting map, and conventions are in
[ar7-ch5-ensemble-brief.md](ar7-ch5-ensemble-brief.md).

> Status: scaffold (milestone 1). The layout and environment are in place; the
> run, classification and figure logic land in later milestones. Module
> docstrings say what each file will hold and which milestone fills it.

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
```

## Engine

The SCM engine is the modernised openscm-runner fork
(github.com/benmsanderson/openscm-runner, branch `modernisation/integration`),
pinned in `pixi.toml` until the upstream PRs land. This repository is the
*application*; the fork is the *engine*.

## How emissions reach the models

Three of the four input sets arrive already harmonised and infilled, so this
repository does not carry a harmonisation/infilling stack. SCI ships SCM-ready
driving emissions (`Climate Assessment|Infilled|Emissions|*`); ScenarioMIP
CMIP7 is harmonised by the CMIP7 pipeline; only SSP2-COM is harmonised here, by
a light global harmoniser anchored to a published 2023 history. See
[docs/methods.md](docs/methods.md) for details and the SCI-vintage caveat.

## Layout

```
pixi.toml             single source of truth for the environment
pyproject.toml        installable package metadata
src/ar7_ch5/          the package (loaders, harmonise, vetting, classification,
                      runners/, experiments/, metrics, figures)
scripts/              canonical command-line entry points
  run_scenarios.py    select experiment + models, run the SCMs
  preprocess_sci.py   SCI xlsx -> CSV
  preprocess_ssp2com.py
  classify.py         vetting + feasibility + classification
  make_figures.py
docs/                 data_setup.md, running_on_nac.md, methods.md
schemes/              clustering / partition config (JSON)
notebooks/            figure-only, thin wrappers over the package
tests/                fixtures + tests (real adapters, no SCM mocking)
data/                 gitignored; obtain per docs/data_setup.md
```

## Conventions

See the brief, section 9. In short: additive changes (do not rewrite working
modules unless asked), feature branches with author-readable commits, tests hit
the real SCM adapters on small inputs (no mocking), drive with physical
`Emissions|CO2|AFOLU`, and flag any scientific divergence from a reference
before treating it as acceptable.
