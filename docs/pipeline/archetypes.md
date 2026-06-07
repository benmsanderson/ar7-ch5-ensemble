# Emissions archetypes

`scripts/compute_archetypes.py` reduces the full SCI ensemble (plus the
ScenarioMIP CMIP7 and SSP2-COM reference pathways) to a small, legible grid of
representative pathways — one per (emissions strategy, warming class) cell. It
is a deterministic, seed-free port of the scenariocompass clustering notebooks,
restructured so the archetype list is tuned entirely from JSON rather than from
a random-seeded clustering run.

```bash
pixi run python scripts/compute_archetypes.py
pixi run python scripts/compute_archetypes.py \
    --sci-xlsx data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx \
    --smip-csv data/scenariomip_cmip7/emissions_1750-2500.csv \
    --ssp2com-xlsx data/ssp2com/ssp2com_emissions.xlsx \
    --classification-sci outputs/classification_per_model.csv \
    --classification-smip outputs/classification_per_model_scenariomip.csv \
    --classification-ssp2com outputs/classification_per_model_ssp2com.csv \
    --gw-source magicc --output-dir outputs
```

Outputs:

| File | Contents |
| --- | --- |
| `outputs/archetype_features.csv` | one row per pathway with all nine features |
| `outputs/clusters.csv` | as above plus `cluster_label` and `centroid_*` |
| `outputs/archetypes.csv` | the representative (strategy, GW) picks |

## The three stages

```mermaid
flowchart LR
    A[Harmonised emissions<br/>SCI · ScenarioMIP · SSP2-COM] --> B[archetype_features<br/>6 features + 3 axis fields]
    B --> C[clustering.fit_clusters<br/>ce_bin-drawdown-strategy]
    C --> D[archetypes.select_archetypes<br/>reference or nearest centroid]
    D --> E[fig07_archetypes grid]
```

### 1. Feature extraction

[`ar7_ch5.archetype_features`](../reference/archetype_features.md) computes, per
pathway, six clustering features (cumulative EIP CO2 2020-2100, CDR fraction,
CH4 reduction by 2050, SO2 in 2050, EIP CO2 in 2050 and 2100, all relative to
2020) plus three partition-axis fields (cumulative AFOLU CO2, cumulative net
CO2 to the net-zero year, and a post-net-zero `drawdown_band` of
`pos`/`nz`/`over`). CO2 integrals are trapezoidal and converted to Gt CO2 to
match the CC-bin thresholds. ScenarioMIP carries no CCS variable, so its CDR
fraction is zero by construction.

### 2. Strategy labelling

[`ar7_ch5.clustering.fit_clusters`](../reference/clustering.md) assigns each
pathway a composite `cluster_label` of `{ce_bin}-{drawdown}-{strategy}` (e.g.
`CC1000-nz-cdr`). Every part is a pure threshold function of the features,
declared in `schemes/clustered.json`:

- `ce_bins` bucket cumulative net CO2 (CC1000 / CC1500 / CC3000 / CC3000+).
- `drawdown_band` is precomputed (`pos` / `nz` / `over`).
- the dominant `strategy` suffix is the first firing rule in an ordered
  priority cascade (`suffix_rules.mode: dominant`).

Two knobs keep the list short and communicable:

- `suffix_rules.mode: dominant` — one strategy per pathway.
- `min_cluster_size` — an occupancy floor that folds rare archetypes into
  their cell's `base` label.

No k-means / random seed runs at this stage. The exploratory analysis that
originally *chose* these thresholds lives in scenariocompass.

### 3. Representative selection

[`ar7_ch5.archetypes.select_archetypes`](../reference/archetypes.md) fills each
(strategy, GW-class) cell with a single pathway, in preference order:

1. A reference pathway — **SSP2-COM first, then ScenarioMIP CMIP7** — whose
   strategy cluster *and* GW class (from its own classification CSV) both match
   the cell; ties break by scenario name.
2. Otherwise, the SCI pathway nearest the cell centroid in standardised feature
   space.
3. Otherwise the cell is left empty.

The `source` (`sci` / `smip` / `ssp2com`) and `selection_rule`
(`reference_match` / `sci_nearest_centroid`) columns record which branch was
taken.

## Figure

`fig07_archetypes` plots the grid: reference picks are coloured with the GMD
pathway palette and SCI nearest-centroid picks are white. Explanatory key
blocks in the empty grid corners gloss the CC budget bins, drawdown bands and
strategy suffixes.
