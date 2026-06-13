# %% [markdown]
# # Chapter harmonisation + infilling: walkthrough
#
# Reproduces the chapter harmonise+infill pipeline (PR replacing the lift-
# shipped-infilled path) on two SCI pathways, showing the raw IAM input,
# the harmonised intermediate at 2023, and the infilled SCM-driving output.
# The full pipeline runs in this notebook; the production entry point is
# ``scripts/harmonise.py --ensemble {sci,scenariomip-cmip7,ssp2com}``.
#
# Naming convention is GCAGES through the body of the chapter; the
# openscm-runner adapter rename is applied at the runner boundary (see
# ``ar7_ch5.runners.orchestrate.rename_to_openscm_runner``). The four
# input files (history, aneris overrides, infilling DB, GHG inversions)
# encode chapter-owned scientific choices documented in
# ``docs/harmonisation_open_questions.md``.

# %%
from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import pandas as pd
from pandas_openscm.indexing import multi_index_match

from ar7_ch5.cmip7_inputs import load_history_emissions
from ar7_ch5.harmonisation import (
    HarmonisationConfig,
    drop_late_starting_scenarios,
    harmonise_and_infill,
    harmonise_aneris_global,
    infill_cmip7,
    interpolate_to_annual,
    rename_iamc_to_gcages,
)
from ar7_ch5.load import load_sci_raw_iamc
from ar7_ch5.runners import repo_root

warnings.filterwarnings("ignore")

SCI_XLSX = repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"

# %% [markdown]
# ## Stage 0: raw IAM emissions
#
# The SCI ensemble xlsx ships IAM submissions under
# ``Emissions|*`` (CMIP7_SCENARIOMIP IAMC convention). We pick two SCI
# pathways for the walkthrough.

# %%
raw = load_sci_raw_iamc(SCI_XLSX)
pairs = list(raw.index.droplevel(["region", "variable", "unit"]).unique())[:2]
sub = raw.loc[
    multi_index_match(
        raw.index,
        pd.MultiIndex.from_tuples(pairs, names=["model", "scenario"]),
    )
]
print(f"{len(sub):,} rows for {len(pairs)} pathways "
      f"({sub.index.get_level_values('variable').nunique()} variables).")

# %% [markdown]
# ## Stages 1-4: drop late starts, interpolate annual, rename, clean
#
# These are the pre-harmonisation chapter transforms. The history-splice
# variant of stage 1 is invoked from the top-level ``harmonise_and_infill``;
# for the visualisation here we use the simpler drop variant so the plot
# below is unambiguous.

# %%
cfg = HarmonisationConfig(progress=False, n_processes=1)
pruned = drop_late_starting_scenarios(sub, anchor_year=cfg.harmonisation_year)
annual = interpolate_to_annual(
    pruned,
    start_year=cfg.annual_start_year,
    end_year=cfg.annual_end_year,
    clip_to_year=cfg.harmonisation_year,
)
renamed = rename_iamc_to_gcages(annual)
print("GCAGES species after rename:")
for v in sorted(renamed.index.get_level_values("variable").unique())[:10]:
    print(" ", v)

# %% [markdown]
# ## Stage 5: aneris harmonisation
#
# Anchors at 2023 using the chapter history file
# (``data/cmip7/history_cmip7_scenariomip.csv``) and the per-IAM overrides
# (``data/cmip7/aneris-overrides-global.csv``). Methods come from
# ``gcages.cmip7_scenariomip``; the chapter does not reimplement aneris.

# %%
history = load_history_emissions(check_hash=cfg.check_hash)
harmonised = harmonise_aneris_global(renamed, config=cfg)
print(f"Harmonised: {len(harmonised):,} rows.")

# %% [markdown]
# ## Stage 6: infilling
#
# Pads the harmonised set onto the 52-species GCAGES driving set using
# RMSClosest against the ScenarioMIP submissions DB (Zenodo 20566343).

# %%
infilled = infill_cmip7(harmonised, config=cfg)
print(f"Infilled: {len(infilled):,} rows, "
      f"{infilled.index.get_level_values('variable').nunique()} species.")

# %% [markdown]
# ## Before / after at the anchor year
#
# The IAM submission and the harmonised series cross at 2023 (the chapter
# anchor); divergence increases as we move forward (each species follows
# its assigned aneris method).

# %%
species = "Emissions|CO2|Fossil"
pid = sorted(infilled.index.get_level_values("scenario").unique())[0]
hist_row = history.xs(species, level="variable").iloc[0]
ren_row = renamed.xs(species, level="variable").iloc[0]
har_row = harmonised.xs(species, level="variable").xs(pid, level="scenario").iloc[0]

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(hist_row.index, hist_row.values, label="history (1750-2023)", lw=2, color="0.4")
ax.plot(
    ren_row.index, ren_row.values,
    label="IAM submission", lw=1.5, color="C0", ls="--",
)
ax.plot(har_row.index, har_row.values, label="harmonised", lw=1.5, color="C3")
ax.axvline(cfg.harmonisation_year, color="0.6", ls=":")
ax.set_xlim(2000, 2100)
ax.set_xlabel("year")
ax.set_ylabel(species + " (Mt CO2/yr)")
ax.set_title(f"Anchor-year handoff: {pid}, {species}")
ax.legend(loc="best", frameon=False)
fig.tight_layout()

# %% [markdown]
# ## Equivalent one-shot call
#
# The whole walkthrough collapses to one ``harmonise_and_infill`` call
# with the same config. The output matches the cached fixture parquet
# committed under ``tests/fixtures/sci_harmonised_infilled_tiny.parquet``.

# %%
out = harmonise_and_infill(sub, config=cfg)
print(f"one-shot output: {len(out):,} rows; "
      f"{out.index.get_level_values('variable').nunique()} species; "
      f"years {out.columns.min()}-{out.columns.max()}.")
