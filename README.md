# AR7 WG1 Chapter 5 climate runs

Runs three simple climate models (FaIR 2.x, CICERO-SCM 2.1.2, MAGICC v7.5.3)
across the Chapter 5 scenario sets and produces the emissions-based scenario
classification, synthesis tables, and figures for IPCC AR7 WG1 Chapter 5.

This repository is meant to be navigable without reading the source. There is
one canonical command-line entry point per task; notebooks are reserved for
figures. The full plan, porting map, and conventions are in
[ar7-ch5-ensemble-brief.md](ar7-ch5-ensemble-brief.md).

> Status: M1-M8 complete. Smoke runs, SCI ensemble batch on NAC, vetting /
> feasibility / classification port, SSP2-COM ingestion + harmoniser,
> ScenarioMIP CMIP7, RCMIP3 concentration-driven diagnostics, and the
> emissions-archetypes port (feature extraction, JSON-tunable strategy
> labelling, representative selection, fig07). Figures are jupytext-paired
> scripts driven by YAML configuration with a read-only cache reporter. See
> the milestone list in
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

# 7. Compute the emissions archetypes (features -> clusters -> representatives).
pixi run python scripts/compute_archetypes.py

# 8. Build the figures registered in schemes/figures.yaml.
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

## Emissions archetypes

`scripts/compute_archetypes.py` reduces the full SCI ensemble (plus the
ScenarioMIP CMIP7 and SSP2-COM reference pathways) to a small grid of
representative pathways, one per (emissions strategy, warming class) cell. It
is a deterministic, seed-free port of the scenariocompass clustering notebooks
in three stages:

1. **Feature extraction** ([archetype_features.py](src/ar7_ch5/archetype_features.py))
   — six clustering features (cumulative EIP CO2, CDR fraction, CH4 reduction,
   SO2 2050, EIP 2050/2100) plus three partition-axis fields (AFOLU CO2,
   cumulative net CO2 to net-zero, post-net-zero drawdown band) per pathway.
2. **Strategy labelling** ([clustering.py](src/ar7_ch5/clustering.py)) — each
   pathway gets a composite `cluster_label` (`{ce_bin}-{drawdown}-{strategy}`,
   e.g. `CC1000-nz-cdr`). The label is a pure function of the features and the
   thresholds in [schemes/clustered.json](schemes/clustered.json); two knobs
   keep the list short and communicable — `suffix_rules.mode: dominant` (one
   strategy per pathway) and `min_cluster_size` (an occupancy floor that folds
   rare labels into their cell's `base` archetype). No k-means / random seed is
   involved at run time.
3. **Representative selection** ([archetypes.py](src/ar7_ch5/archetypes.py)) —
   for each (strategy, GW-class) cell, prefer a reference pathway (SSP2-COM,
   then ScenarioMIP) whose strategy cluster and GW class both match; otherwise
   take the SCI pathway nearest the cell centroid in standardised feature
   space.

The picks are written to `outputs/archetypes.csv` (with `outputs/clusters.csv`
and `outputs/archetype_features.csv`) and plotted by `fig07_archetypes`.

## Building figures

Three CLIs in a chain; each is read-only on the layer below it:

```
scripts/cache_status.py    reports which ensemble outputs / CSVs are present
scripts/run_scenarios.py   produces SCM ensemble NetCDFs (per experiment)
scripts/classify.py        produces classification CSVs (per source)
scripts/compute_archetypes.py  produces archetype features / clusters / picks
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

## Documentation

A MkDocs (Material) site under `docs/` collects the narrative guides
(installation, NAC setup, data setup, the pipeline walkthroughs, methods) and
an auto-generated API reference built from the package docstrings.

### Read it online (no setup)

The docs are published to GitHub Pages and rebuilt automatically on every push
to `main`, so the hosted copy always tracks the code:

**<https://benmsanderson.github.io/ar7-ch5-ensemble/>**

This is the easiest option, especially when working on a cluster where
forwarding a local port is awkward.

### Read the docs locally (foolproof)

If you prefer a local copy, you do **not** need MAGICC, the input data, or any
of the climate models — `pixi` resolves everything the docs build needs.

1. **Start the live docs server** from the repo root. On first run this builds
   the pixi environment (a few minutes, only once), then serves the site:

   ```bash
   pixi run docs-serve
   ```

   If the environment is stale or you hit a missing-package error, force a
   fresh install first with `pixi install`, then re-run the command above.

2. **Open the docs**: visit <http://127.0.0.1:8000> in your browser. The page
   rebuilds automatically when you edit anything under `docs/`. Press
   `Ctrl+C` in the terminal to stop the server.

That's it — no other setup is required to read the documentation.

### Build a static copy

```bash
# One-off strict build into site/ (what ReadTheDocs runs).
pixi run docs
```

This writes a self-contained HTML site to `site/`; open `site/index.html` in a
browser. `mkdocs.yml` holds the nav and theme. The hosted copy is built and
deployed by [.github/workflows/docs.yml](.github/workflows/docs.yml) on each
push to `main`; `.readthedocs.yaml` is kept as an alternative hosting path
(`pip install .[docs]`). The built `site/` directory is gitignored.

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
  archetype_features.py  per-pathway emissions features for archetypes
  clustering.py       declarative strategy labelling (schemes/clustered.json)
  archetypes.py       representative (strategy, GW) pathway selection
  metrics.py          warming metrics over the 3-SCM ensemble NetCDFs
  cache.py            read-only enumerator (expected vs present per experiment)
  figures.py          config / style / save helpers for figure scripts
  runners/, experiments/
scripts/              canonical command-line entry points
  run_scenarios.py    select experiment + models, run the SCMs
  classify.py         vetting + feasibility + sustainability + classification
  compute_archetypes.py  features -> clusters -> representative archetypes
  cache_status.py     report present / missing ensemble outputs
  make_figures.py     dispatch jupytext-paired figure scripts
docs/                 data_setup.md, running_on_nac.md, methods.md
schemes/              YAML configs
  figures.yaml        per-figure spec (experiment, source, output formats)
  clustered.json      archetype partition + strategy-labelling thresholds
  gw/<name>.json      GW0-GW8 warming taxonomy (default si3)
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
