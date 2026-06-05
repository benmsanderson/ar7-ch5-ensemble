# ---
# jupyter:
#   jupytext:
#     formats: notebooks///py:percent,notebooks///ipynb
# ---

# %% [markdown]
# # Figure 01 - SCI 2025 warming classification distribution
#
# Counts of pathways across the GW0-GW8 warming categories (Riahi et al.
# 2026, SI Table 3) from the SCI 2025 ensemble. Two stacks:
# **all 1599 pathways** and the **vetted subset** (passing Table SI.1
# basic vetting).
#
# Inputs: ``outputs/classification_xlsx.csv`` -- written by
# ``scripts/classify.py --source xlsx``. The cache reporter
# (``scripts/cache_status.py``) lists this CSV under
# ``[classification]`` if missing.

# %%
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ar7_ch5 import figures
from ar7_ch5.cache import status_for
from ar7_ch5.classification import GW_ORDER
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig01_classification"

# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)

source = cfg["source"]
csv_path = repo_root() / "outputs" / f"classification_{source}.csv"

# Cache check: fail with the exact rerun command if the CSV isn't there.
entry = status_for("classification", source)
if not entry.complete:
    raise FileNotFoundError(
        f"Required input is missing: {csv_path.relative_to(repo_root())}. "
        f"Generate it with: {entry.rerun_cmd}"
    )

df = pd.read_csv(csv_path)
print(f"loaded {len(df)} scenarios from {csv_path.name}")

# %% [markdown]
# ## Tally per category

# %%
def _counts(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["category"]
        .value_counts()
        .reindex(GW_ORDER)
        .fillna(0)
        .astype(int)
    )


all_counts = _counts(df)
print("all-scenario counts:", all_counts.to_dict())

show_vetted = bool(cfg.get("show_vetted_only", False))
if show_vetted:
    vetted_counts = _counts(df.loc[df["vetting_status"] == "passed"])
    print("vetted counts:    ", vetted_counts.to_dict())

# %% [markdown]
# ## Plot

# %%
categories = list(GW_ORDER)
n = len(categories)
positions = np.arange(n)
width = 0.4 if show_vetted else 0.7
colors = [style.gw_colors.get(c, "#888888") for c in categories]

fig, ax = plt.subplots(figsize=tuple(style.fig_size_inches))
if show_vetted:
    ax.bar(positions - width / 2, all_counts.values, width=width,
           color=colors, edgecolor="black", linewidth=0.5,
           label="all pathways")
    ax.bar(positions + width / 2, vetted_counts.values, width=width,
           color=colors, edgecolor="black", linewidth=0.5,
           hatch="///", label="vetted (passed)")
    ax.legend(loc="upper right", frameon=False)
else:
    ax.bar(positions, all_counts.values, width=width,
           color=colors, edgecolor="black", linewidth=0.5)

ax.set_xticks(positions)
ax.set_xticklabels(categories, rotation=0)
ax.set_ylabel("Number of pathways")
ax.set_xlabel("GW category")
ax.set_title(cfg.get("title", FIGURE_ID))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
fig.tight_layout()

# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")
sys.exit(0)
