# Emissions archetypes: port + figure (next PR brief)

This brief captures everything a future session needs to land the
emissions-archetypes port from `scenariocompass` into this repo. PR A
(per-SCM warming classification) merged as #24; the per-SCM
classification CSVs that the archetype selection step consumes are now
on disk. PR B (this brief) is the substantive port: feature extraction,
pinned-centroid clustering, representative selection, plus a figure.

If you're picking this up cold, read the [original plan
file](../.claude/plans/prancy-weaving-cerf.md) for the two-PR plan
overview, then this brief for everything PR-B-specific.

## 1. Where the chapter stands today

**Landed** (as of merge of PR #24, commit `c17e4c1`):

- Per-SCM warming classification CSVs in `outputs/`:
  - `classification_per_model.csv` -- 2259 rows (SCI: 1599 vetting + 990
    per-SCM where NCs exist).
  - `classification_per_model_scenariomip.csv` -- 21 rows.
  - `classification_per_model_ssp2com.csv` -- 3 rows.
  - `classification_xlsx.csv` -- the MAGICC-baked-percentiles regression
    path (1599 rows, no per-SCM dimension).
- `fig03_classification_per_scm.{png,pdf}` summarising the per-SCM
  spread (SCI stacks left, ScenarioMIP+SSP2-COM 3x8 grid right).
- 990 SCI ScmRun NetCDFs covering the vetted set at 200 members per
  SCM, 21 ScenarioMIP CMIP7 NetCDFs, 3 SSP2-COM NetCDFs. All carry
  GSAT / ERF / CO2 conc / CH4 conc.

**Not yet ported** -- the focus of this PR:

- Emissions-feature extraction (analogue of `scenariocompass/notebooks/
  03_metrics.ipynb`).
- Pinned-centroid k-means clustering (analogue of `04_cluster_explore`).
- Representative-archetype selection (analogue of `05_archetypes`).
- A summary figure (`fig07_archetypes`) reproducing scenariocompass's
  strategy x GW grid.

## 2. Why this PR -- the chapter scientific question

The chapter needs a small set of representative pathways that span both
the emissions-strategy space (how the world decarbonises: CDR-heavy vs
lock-in vs methane-first etc.) and the warming-outcome space
(GW0..GW8). Showing every one of ~1599 SCI scenarios is impossible;
showing just the 8 ScenarioMIP CMIP7 baselines under-represents the IAM
diversity. The scenariocompass approach -- cluster SCI on emissions
features with ScenarioMIP CMIP7 pinned as fixed centroids, then for
each (strategy, GW) cell pick a representative -- gives the chapter a
~45-pathway shortlist that's emissions-justified, warming-distinguished
and traceable.

The figure (`fig07_archetypes`) is the canonical chapter visualisation:
strategy labels on one axis, GW0..GW8 on the other, every populated
cell carries a chosen `(Model, Scenario)` archetype label.

## 3. Two-PR plan recap

| | Status | Scope |
|---|---|---|
| **PR A** -- per-SCM classification | Landed (#24) | Generalise `metrics.py` + `scripts/classify.py` to handle SCI / ScenarioMIP / SSP2-COM. Produces the per-SCM classification CSVs. |
| **PR B** -- archetypes port + figure | This brief | Port scenariocompass's clustering + archetype selection + figure. Consumes PR A's CSVs for the GW labels. |

User decisions already locked in (see [plan
file](../.claude/plans/prancy-weaving-cerf.md)):

- Emissions-feature extraction in a **new** module
  `src/ar7_ch5/archetype_features.py` (not bolted onto the existing
  warming-metrics `metrics.py`).
- **Full reproduction** -- data + figure, not data only.

## 4. Methodology (plain prose)

### 4.1 Feature extraction

For each pathway (SCI scenario or ScenarioMIP/SSP2-COM baseline),
compute six emissions features over 2020-2100 IAMC-style emissions
trajectories:

| Feature | Definition |
|---|---|
| `cum_co2_eip` | Trapezoidal integral of `Emissions\|CO2\|Energy and Industrial Processes`, 2020-2100. Gt CO2. |
| `cdr_fraction` | `cum_removals / cum_gross_fossil`, where `cum_removals` is the trapezoidal integral of `\|Carbon Capture\|Geological Storage\|` and `cum_gross_fossil = cum_co2_eip + cum_removals`. Unitless [0, 1]. |
| `ch4_reduction` | `CH4(2050) / CH4(2020)` ratio. Unitless. |
| `so2_2050_rel` | `Sulfur(2050) / Sulfur(2020)` ratio. Unitless. |
| `eip_2050_rel` | `EIP(2050) / EIP(2020)` ratio. Unitless. |
| `eip_2100_rel` | `EIP(2100) / EIP(2020)` ratio. Unitless. |

Plus three partition-axis fields:

- `cum_co2_afolu` -- trapezoidal integral of `Emissions|CO2|AFOLU`,
  2020-2100. Used by the `land` suffix rule.
- `cum_co2_net_to_nz` -- cumulative net CO2 from 2020 to the
  net-zero year (or 2100 if NZ never reached). Net = EIP + AFOLU.
  **Primary partition axis.**
- `drawdown_band` -- categorical from `post_nz_drawdown` (cumulative
  net-negative CO2 from NZ year to 2100):
  - `pos` -- never reaches NZ
  - `nz` -- reaches NZ, drawdown <= 200 GtCO2
  - `over` -- reaches NZ, drawdown > 200 GtCO2
  **Secondary partition axis.**

Net-zero year identification: scan the (annualised) net CO2
trajectory; first crossing from positive to non-positive; linearly
interpolate between the bracketing grid points. NaN if no crossing.

### 4.2 Partitioning + clustering

Step 1: assign each pathway to a (CC bin, drawdown band) cell. CC bin
edges (config-driven): 1000 / 1500 / 3000 Gt CO2 split
`cum_co2_net_to_nz` into CC1000, CC1500, CC3000, CC3000+. Drawdown
band already computed. Up to 12 cells; only 9 are non-empty in the
landed SCI ensemble.

Step 2: standardise the six clustering features with a single
`StandardScaler` fitted on the full SCI vetted set (NaN filled with
SCI median first). Apply the same scaler to both SCI and ESM.

Step 3: in each (CC, drawdown) cell, run **pinned-centroid k-means**:

- `n_pinned` centroids initialised at ScenarioMIP/SSP2-COM positions
  (whichever ESMs fall in that cell). These centroids never move.
- `n_free` additional centroids initialised via k-means++ on SCI data.
- Iterate distance assignment + centroid update; only free centroids
  update; convergence at `atol=1e-8`.

Step 4: silhouette sweep to pick `k`. For each `k` in
`[n_esm, n_esm + max_extra_clusters]`:

- Run pinned k-means.
- Merge SCI-only clusters with fewer than `min_cluster_size`
  members into their nearest viable neighbour (protect ESM-pinned
  clusters from dissolution).
- Compute `silhouette_score(X_sci, merged_labels)`.

Accept additional clusters greedily: walk `k_range` ascending,
accept the next `k` only if silhouette gain >= `min_silhouette_gain`
(0.05); stop at first failure.

Step 5: dissolve ESM-anchored clusters with zero SCI uptake whose
ESM falls within `esm_merge_threshold` (1.5 standardised SDs) of a
non-ESM cluster centroid.

Step 6: name each surviving cluster with a composite suffix
(`cdr+ch4` etc.) via priority rules; see §5.4. Combined label is
`"{ce_bin}-{drawdown_band}-{suffix}"` e.g. `CC1000-nz-cdr+ch4`.

### 4.3 Representative selection

For each (strategy_label, GW_class) cell:

1. If a ScenarioMIP/SSP2-COM pathway in that strategy cluster has
   matching GW class, use it.
2. Otherwise pick the SCI scenario closest to the cluster centroid
   in standardised feature space.
3. Skip the cell entirely if no SCI candidate and no matching ESM.

Output: ~45 archetype rows (8 ESM + ~37 SCI) over ~16 strategy
labels and 8 GW classes.

## 5. Reference material from scenariocompass

Local checkout: `~/Documents/Github/scenariocompass`.

### 5.1 File map

| scenariocompass path | What it does | Lift directly? |
|---|---|---|
| `notebooks/03_metrics.ipynb` | Feature extraction; writes `data/metrics_sci.parquet`, `data/metrics_smip.parquet` | Port logic into `src/ar7_ch5/archetype_features.py`. Don't keep the parquet format; CSV in `outputs/` matches the chapter convention. |
| `notebooks/04_cluster_explore.ipynb` | Pinned k-means + suffix labelling; writes `data/clustered_sci.parquet`, `data/clustered_smip.parquet` | Port into `src/ar7_ch5/clustering.py`. The pinned-kmeans + merge helpers are pure-numerical and unit-testable. |
| `notebooks/05_archetypes.ipynb` | Strategy x GW selection; writes `data/archetypes.parquet` + figure | Port into `src/ar7_ch5/archetypes.py`. Figure goes to `notebooks/fig07_archetypes.py` (jupytext-paired). |
| `schemes/clustered.json` | Configuration (CC bins, suffix rules, k-means hyperparams) | Copy as-is to `schemes/clustered.json` in this repo. See §5.4 below for the full payload. |

### 5.2 Net-zero detection (reference snippet)

Verbatim from `notebooks/03_metrics.ipynb`:

```python
def find_netzero_year(co2_net_row):
    """First year net CO2 crosses zero (linear interpolation); NaN if never."""
    vals = co2_net_row.values.astype(float)
    for i in range(len(vals) - 1):
        if vals[i] > 0 and vals[i + 1] <= 0:
            frac = vals[i] / (vals[i] - vals[i + 1])
            return years_int[i] + frac * (years_int[i + 1] - years_int[i])
    return np.nan
```

### 5.3 Pinned k-means (reference snippet)

Verbatim from `notebooks/04_cluster_explore.ipynb`:

```python
def pinned_kmeans(X_sci, X_esm, k_total, n_pinned, max_iter=100):
    """K-means with n_pinned centroids held fixed at ESM positions."""
    n_free = k_total - n_pinned
    n_sci = len(X_sci)

    pinned_centroids = X_esm.copy() if n_pinned > 0 else np.empty((0, X_sci.shape[1]))

    if n_free > 0 and n_sci > 0:
        km_init = KMeans(
            n_clusters=min(n_free, n_sci), n_init=10, random_state=42,
        )
        km_init.fit(X_sci)
        free_centroids = km_init.cluster_centers_[:n_free]
    else:
        free_centroids = np.empty((0, X_sci.shape[1]))

    centroids = np.vstack([pinned_centroids, free_centroids])
    X_all = np.vstack([X_sci, X_esm]) if n_pinned > 0 else X_sci

    for _ in range(max_iter):
        dists = np.linalg.norm(X_all[:, None, :] - centroids[None, :, :], axis=2)
        labels = dists.argmin(axis=1)
        new_centroids = centroids.copy()
        for j in range(n_pinned, k_total):
            members = X_all[labels == j]
            if len(members) > 0:
                new_centroids[j] = members.mean(axis=0)
        if np.allclose(new_centroids, centroids, atol=1e-8):
            break
        centroids = new_centroids

    labels_sci = labels[:n_sci]
    labels_esm = labels[n_sci:] if n_pinned > 0 else np.array([], dtype=int)
    return labels_sci, labels_esm, centroids
```

`merge_small_clusters` and `merge_close_esms` are similarly structured;
both walk a `while True` loop merging into nearest viable neighbour by
Euclidean distance in standardised feature space.

### 5.4 schemes/clustered.json (verbatim)

Copy this file unchanged to `schemes/clustered.json` in the chapter
repo. Same payload, same comments:

```json
{
    "name": "Two-axis (CC bin x drawdown band) partition + within-cell strategy clustering",
    "description": "Two-axis emissions-based partition of the SCI ensemble. Both axes are properties of the emissions trajectory only (no SCM lookup): cumulative net CO2 from 2020 to net-zero year on the primary axis, and post-NZ behaviour band on the secondary axis (pos/nz/over). Within each (CC, drawdown) cell, k-means with ESM-pinned centroids identifies strategy clusters; centroids are then named by composite suffix flags (CDR, methane, aerosol cleanup, land-sink reliance, near-term deferral, fossil lock-in). CC bin edges are rounded to where MAGICC v7.5.3 medians cross GW-class PW50 boundaries in the SCI ensemble. AFOLU dependence, formerly a partition axis, was demoted to a suffix flag (`land`) after diagnostic showed mean landdep/other centroid separation of 0.61 SD against a within-cell spread of 1.2 SD -- below typical noise.",
    "ce_bins": {
        "metric": "cum_co2_net_to_nz",
        "thresholds": [1000, 1500, 3000],
        "labels": ["CC1000", "CC1500", "CC3000", "CC3000+"]
    },
    "drawdown_bands": {
        "metric": "drawdown_band",
        "comment": "Pre-computed in 03_metrics (assign_drawdown_band).",
        "thresholds": [200],
        "labels": ["pos", "nz", "over"]
    },
    "cluster_features": [
        "cum_co2_eip", "cdr_fraction", "ch4_reduction",
        "so2_2050_rel", "eip_2050_rel", "eip_2100_rel"
    ],
    "suffix_rules": {
        "display_order": ["cdr", "deepcdr", "ch4", "slcf", "land", "defer", "lockin"],
        "rules": {
            "cdr":     {"conditions": [
                {"feature": "cdr_fraction", "op": ">=", "threshold": 0.25},
                {"feature": "cdr_fraction", "op": "<",  "threshold": 0.55}
            ]},
            "deepcdr": {"conditions": [
                {"feature": "cdr_fraction", "op": ">=", "threshold": 0.55}
            ]},
            "ch4":     {"conditions": [
                {"feature": "ch4_reduction", "op": "<=", "threshold": 0.50}
            ]},
            "slcf":    {"conditions": [
                {"feature": "so2_2050_rel", "op": ">=", "threshold": 0.50}
            ]},
            "land":    {"conditions": [
                {"feature": "cum_co2_afolu", "op": "<=", "threshold": -150}
            ]},
            "defer":   {"conditions": [
                {"feature": "eip_2050_rel", "op": ">=", "threshold": 0.80},
                {"feature": "eip_2100_rel", "op": "<",  "threshold": 0.30}
            ]},
            "lockin":  {"conditions": [
                {"feature": "eip_2050_rel", "op": ">=", "threshold": 0.80},
                {"feature": "eip_2100_rel", "op": ">=", "threshold": 0.50}
            ]}
        }
    },
    "min_cluster_size": 8,
    "esm_pinning": true,
    "esm_merge_threshold": 1.5,
    "max_extra_clusters": 1,
    "min_silhouette_gain": 0.05
}
```

(The original file has longer comment fields; trim to taste.)

### 5.5 Required IAMC variables

Names per source. ScenarioMIP CMIP7 uses bare `Emissions|...`; the SCI
xlsx uses the `Climate Assessment|Harmonized|Emissions|...` infilled
namespace. Both sources need the same time grid (5-year intervals,
2020-2100; interpolation OK).

| Purpose | SCI xlsx variable | ScenarioMIP CSV variable |
|---|---|---|
| EIP CO2 | `Climate Assessment\|Harmonized\|Emissions\|CO2\|Energy and Industrial Processes` | `Emissions\|CO2\|Energy and Industrial Processes` |
| AFOLU CO2 | `Climate Assessment\|Harmonized\|Emissions\|CO2\|AFOLU` | `Emissions\|CO2\|AFOLU` |
| Storage / CCS | `Carbon Capture\|Geological Storage` | `Emissions\|CO2\|Gross Removals` (sign-flipped at load) |
| CH4 | `Climate Assessment\|Harmonized\|Emissions\|CH4` | `Emissions\|CH4` |
| N2O | `Climate Assessment\|Harmonized\|Emissions\|N2O` | `Emissions\|N2O` |
| Sulfur | `Climate Assessment\|Harmonized\|Emissions\|Sulfur` | `Emissions\|Sulfur` |

Note: scenariocompass also pulls a MAGICC GSAT percentile column for
diagnostics (`peak_year`). PR B doesn't need those -- GW labels come
from PR A's per-SCM classification CSVs.

## 6. File-by-file PR plan

### 6.1 New files

| File | Purpose |
|---|---|
| `src/ar7_ch5/archetype_features.py` | Emissions-feature extraction. `compute_features(sci_df, smip_df) -> pd.DataFrame`. Reuses existing IAMC parsers from `ar7_ch5.load` and `ar7_ch5.load_scenariomip`. |
| `src/ar7_ch5/clustering.py` | `pinned_kmeans`, `merge_small_clusters`, `merge_close_esms`, `match_suffix`. Pure-numerical, sklearn for silhouette only. Unit-testable. |
| `src/ar7_ch5/archetypes.py` | `select_archetypes(clustered_sci, clustered_smip, classification_per_model_sci, scheme) -> pd.DataFrame`. Iterates (strategy, GW_class) cells; preference order ESM-pinned-with-matching-GW > SCI-nearest-to-centroid. |
| `schemes/clustered.json` | Lifted verbatim from scenariocompass. |
| `scripts/compute_archetypes.py` | CLI: `--classification-sci ... --classification-smip ... --gw-source magicc`. Writes `outputs/archetypes.csv` and intermediates `outputs/archetype_features.csv`, `outputs/clusters.csv`. |
| `notebooks/fig07_archetypes.py` | Jupytext-paired figure: strategy x GW grid with chosen `(Model, Scenario)` per cell. |
| `tests/test_archetype_features.py` | Feature math on small synthetic IAMC frames. |
| `tests/test_clustering.py` | Pinned-kmeans keeps pinned centroids stationary; `merge_small_clusters` deterministic; `match_suffix` honours priority order. |
| `tests/test_archetypes.py` | Selection: ESM preference; SCI tie-break by centroid distance. |
| `tests/test_archetypes_regression.py` | Compare against scenariocompass `data/archetypes.parquet` if staged locally; require >= 90% (Model, Scenario) match. Skipped in CI. |

### 6.2 Modified files

| File | Change |
|---|---|
| `schemes/figures.yaml` | Register `fig07_archetypes`. |
| `docs/methods.md` | Short section on the archetype methodology + a pointer to the published reference (Riahi 2026 SI / scenariocompass). |
| `ar7-ch5-ensemble-brief.md` | Section 12 "Backlog" item closed; tick the archetype port. |

### 6.3 NOT modified

- `src/ar7_ch5/metrics.py` -- stays focused on warming-metrics-from-NCs. (The plan considered overloading it; the user picked the clean split.)
- `src/ar7_ch5/classification.py` -- unchanged; `classify_from_metrics` is reused via PR A's CSV outputs.

## 7. Key open decisions for the next session

1. **Which SCM's GW labels feed archetype selection?** Default
   recommendation: **MAGICC**, for parity with scenariocompass. CLI
   flag `--gw-source {fair,ciceroscm,magicc}` so it's easy to switch.
   Rationale and tradeoffs go in `docs/methods.md`.

2. **What if the chapter's vetted set doesn't have all the IAMC
   variables scenariocompass assumes?** Specifically the
   `Carbon Capture|Geological Storage` row; if missing, set
   `cdr_fraction = 0` and document. Currently
   `outputs/classification_per_model.csv` is keyed on (Model,
   Scenario); we know all 330 vetted pathways have the basic emissions
   variables, but CCS coverage needs spot-checking.

3. **Drawdown threshold sign convention.** scenariocompass uses
   "drawdown" = net-negative cumulative emissions, threshold 200 Gt.
   The chapter has flipped sign conventions in places (CO2|AFOLU); be
   careful at the load boundary. The reference snippet at §5.2 keeps
   the math explicit.

4. **What does `cum_co2_net` mean for ScenarioMIP/SSP2-COM whose data
   ends at 2100 vs SCI?** All three sources share the 2020-2100 window,
   so this should be a no-op, but check the loader doesn't silently
   bring 2100.5 half-year offsets into the picture.

5. **Regression test policy.** If we have scenariocompass's
   `data/archetypes.parquet` accessible, the test should require
   >=90% (Model, Scenario) match per cell. Allow legitimate drift
   from (a) different MAGICC drawnset, (b) slightly different vetted
   set, (c) different CICERO/FaIR contribution to GW labels.

## 8. Verification plan

End-to-end:

```bash
pixi run python scripts/compute_archetypes.py
# Expect outputs/archetypes.csv with roughly 45 rows.

pixi run python scripts/make_figures.py --figure fig07_archetypes
# Expect outputs/figures/fig07_archetypes.{png,pdf}; visually similar
# to scenariocompass's archetype grid.
```

Unit:

```bash
pixi run pytest -q -m "not smoke" tests/test_archetype_features.py \
    tests/test_clustering.py tests/test_archetypes.py
```

Regression (skipped if scenariocompass parquet unavailable):

```bash
pixi run pytest -q -m smoke tests/test_archetypes_regression.py
```

Visual: open `outputs/figures/fig07_archetypes.png`. Expect a strategy
x GW grid with ~16 strategy rows and 8 GW columns. Most cells
populated; ESM-anchored cells highlighted (e.g. bold ScenarioMIP
short-codes like `M`, `H`, `VL` rather than full IAM/Scenario strings).

## 9. Estimated effort

- Feature extraction: ~half day (small, mostly arithmetic; the IAMC
  variable plumbing is the main work).
- Clustering: ~half to one day (the pinned-kmeans logic is short but
  needs careful unit tests).
- Archetype selection: half day.
- Figure: half day.
- Tests + regression: half day.
- Docs + PR description: half day.

**Total: ~3 days for a focused session.** Could compress to 2 days if
working from scenariocompass code mechanically.

## 10. Out of scope

- Porting `notebooks/02_scenariomip_projection.ipynb` (PCA diagnostic
  -- companion to archetypes, not consumed by them).
- Pooled-across-SCMs classification -- the per-SCM decision is locked
  ([memory](../.claude/projects/-storage-no-backup-nac-users-bensan-ch5-ar7-ensemble/memory/project_classification_warming_contract.md)).
- SSP2-COM long-tail extension via FLEX (separate backlog,
  brief Section 12).
- Re-running the SCI ensemble -- the existing 990 vetted NCs feed
  PR A's CSVs, which PR B reads. No new SCM runs in PR B.

## 11. Quick-start checklist for the next session

1. `git checkout main && git pull` (verify at >= `c17e4c1`).
2. `git checkout -b archetypes-port`.
3. Read [the plan file](../.claude/plans/prancy-weaving-cerf.md) and
   this brief end-to-end (~15 min).
4. Skim `~/Documents/Github/scenariocompass/notebooks/03_metrics.ipynb`,
   `04_cluster_explore.ipynb`, `05_archetypes.ipynb` for the actual
   code (~30 min).
5. Copy `~/Documents/Github/scenariocompass/schemes/clustered.json` to
   `schemes/clustered.json` (verbatim).
6. Implement `archetype_features.py` first, with unit tests on
   synthetic IAMC.
7. Implement `clustering.py` next, with unit tests.
8. Implement `archetypes.py` selection.
9. Wire `scripts/compute_archetypes.py` CLI.
10. Build `notebooks/fig07_archetypes.py` last.
11. PR + CI green + merge.
