# Classification

`scripts/classify.py` runs the Riahi et al. (2026) supplementary tables over a
scenario set: vetting (Table SI.1), feasibility and sustainability (Table
SI.2), and the GW0-GW8 warming classification (Table SI.3) plus its
emissions-based extension. It writes `outputs/classification_*.csv`.

```bash
# Regression path: MAGICC percentiles baked into the SCI xlsx.
pixi run python scripts/classify.py --source xlsx

# Three-SCM ensemble metrics path.
pixi run python scripts/classify.py --source per_model
```

## Warming taxonomy schemes

The GW0-GW8 taxonomy is declarative. `schemes/gw/<name>.json` holds an ordered
first-match cascade of threshold tests on the warming metrics
(`peak_warming_50/67`, `eoc_warming_50/67`, `declining`), plus `category_order`
and a `colors` palette, so each scheme is fully self-contained.

- `gw/si3.json` is the canonical Table SI.3 taxonomy (Riahi et al. 2026); it is
  the default and what the classification regression test pins against.

Select a scheme with `--gw-scheme <name>` (default `si3`), or load it in code
via [`ar7_ch5.classification.load_gw_scheme`](../reference/classification.md).
Figures declare which scheme they were classified under with a `gw_scheme:` key
in `schemes/figures.yaml`. Adding a new taxonomy is a new JSON file — no code
change.

## Modules

- [`ar7_ch5.vetting`](../reference/vetting.md) — Table SI.1.
- [`ar7_ch5.feasibility`](../reference/vetting.md) — Table SI.2.
- [`ar7_ch5.classification`](../reference/classification.md) — Table SI.3 +
  emissions-based extension.
- [`ar7_ch5.metrics`](../reference/metrics.md) — warming metrics over the
  three-SCM ensemble NetCDFs.
