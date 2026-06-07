# Building figures

`scripts/make_figures.py` dispatches the jupytext-paired figure scripts under
`notebooks/`, reading only the cached outputs and writing PNG / PDF under
`outputs/figures/`.

```bash
# Build everything registered in schemes/figures.yaml.
pixi run python scripts/make_figures.py --all

# Build one figure.
pixi run python scripts/make_figures.py --figure fig07_archetypes
```

## How a figure is wired

Each figure is a jupytext-paired `notebooks/figXX_*.py` (percent format):

- The `.py` is the tracked source of truth; the `.ipynb` is generated on
  demand and gitignored. Open the `.py` in JupyterLab to use it as a notebook.
- Per-figure spec lives in `schemes/figures.yaml`, keyed by the same id as the
  script (the "which data goes into this figure" decisions chapter authors
  would edit by hand). Shared palettes and DPI / font defaults live in
  `schemes/style.yaml`.
- Figure scripts load their slice via
  [`ar7_ch5.figures.load_config`](../reference/cache.md).

`make_figures.py` checks required inputs through the same enumerator as
[`cache_status.py`](running-scms.md) and fails early with a clear
`FileNotFoundError` if a cached output is missing, so the figure layer never
silently runs an SCM.

## Adding a figure

Two steps:

1. A new `notebooks/figXX_*.py` (percent format, jupytext-paired).
2. A new entry in `schemes/figures.yaml` keyed by the same id.

## Current figures

| Id | Content |
| --- | --- |
| `fig01_classification` | GW0-GW8 classification distribution (SCI) |
| `fig03_classification_per_scm` | GW0-GW8 per SCM across the chapter input sets |
| `fig04_ssp2com_validation` | SSP2-COM driving emissions vs Charlie Koven |
| `fig05_scenariomip_extensions` | ScenarioMIP CMIP7 three-SCM extensions |
| `fig06_per_scm_grid` | Per-SCM CO2 / CH4 / ERF / GSAT grid |
| `fig07_archetypes` | Strategy × warming-class archetype grid |
