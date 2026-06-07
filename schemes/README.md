# schemes

Configuration for the clustering / partition scheme.

`clustered.json` (the three-axis partition plus within-cell clustering config)
is to be copied verbatim from scenariocompass `schemes/clustered.json` when the
clustering port lands (milestone 5+). It is kept as plain JSON config rather
than buried in code.

## `gw/` — warming-classification schemes

`gw/<name>.json` holds the declarative GW0-GW8 warming taxonomy: an ordered
first-match cascade of threshold tests on the warming metrics
(`peak_warming_50/67`, `eoc_warming_50/67`, `declining`), plus `category_order`
and a `colors` palette so each scheme is fully self-contained.

- `gw/si3.json` — the canonical Table SI.3 taxonomy (Riahi et al. 2026); the
  default and what the classification regression test pins against.

Select a scheme with `scripts/classify.py --gw-scheme <name>` (default `si3`),
or load it in code via `ar7_ch5.classification.load_gw_scheme(name)`. Figures
declare which scheme they were classified under with a `gw_scheme:` key in
`figures.yaml`. Adding a new taxonomy is a new JSON file here — no code change.

