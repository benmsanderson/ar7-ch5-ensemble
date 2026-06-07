# schemes

Configuration for the clustering / partition scheme.

`clustered.json` is the declarative emissions-archetype scheme consumed by
`ar7_ch5.clustering.fit_clusters`. It holds the partition thresholds
(`ce_bins`, `drawdown_bands`), the ordered `suffix_rules` that assign each
pathway its dominant strategy, and the two knobs that keep the archetype list
short: `suffix_rules.mode` (`"dominant"` = one strategy per pathway) and
`min_cluster_size` (occupancy floor folding rare labels into the cell `base`).
The label is a pure, deterministic function of the per-pathway features — no
k-means / random seed runs at this stage. The exploratory k-means analysis that
originally *chose* these thresholds lives in the scenariocompass repository.
Kept as plain JSON config rather than buried in code.

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

