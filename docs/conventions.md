# Conventions

See `ar7-ch5-ensemble-brief.md` section 9 for the full statement. In short:

- **Additive changes.** Do not rewrite working modules unless asked. Extend.
- **Feature branches** with author-readable commits; open a PR to merge.
- **Real adapters in tests.** Tests hit the real SCM adapters on small inputs;
  there is no SCM mocking.
- **Physical AFOLU.** Drive the SCMs with the physical
  `Emissions|CO2|AFOLU`, not the `[NGHGI]` national-inventory variant.
- **Flag divergence.** Surface any scientific divergence from a reference
  before treating it as acceptable.

## Code style

- `pixi run lint` runs `ruff check .`; `pixi run format` runs `ruff format .`.
- Line length is 88 (ruff `E501`).
- Public functions carry numpydoc-style docstrings; these are what the
  [API reference](reference/load.md) renders via mkdocstrings.

## Figures

- Each figure is a jupytext-paired `notebooks/figXX_*.py` (percent format).
  The `.py` is the tracked source of truth; the `.ipynb` is generated on
  demand and gitignored.
- Per-figure spec lives in `schemes/figures.yaml`, keyed by the figure id;
  shared palettes and DPI / font defaults in `schemes/style.yaml`.
- Adding a figure is two steps: a new `notebooks/figXX_*.py` and a new entry
  in `schemes/figures.yaml` keyed by the same id.

## Declarative schemes

Behaviour that chapter authors might want to tune lives in JSON/YAML under
`schemes/`, not in code:

- `schemes/gw/<name>.json` — the GW0-GW8 warming taxonomy (default `si3`).
- `schemes/clustered.json` — the emissions-archetype partition and
  strategy-labelling thresholds.
- `schemes/figures.yaml` / `schemes/style.yaml` — per-figure spec and style.
