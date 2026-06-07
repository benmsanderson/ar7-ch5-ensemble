# %% [markdown]
# # Figure 07 - Emissions archetypes grid (strategy × GW class)
#
# Canonical strategy × warming grid: each cell shows the (Model, Scenario)
# selected as representative for that (emissions-strategy cluster, GW class)
# combination.  ESM picks (ScenarioMIP CMIP7) are highlighted; SCI picks
# are the nearest-centroid scenario.
#
# Inputs:
#   ``outputs/archetypes.csv``      produced by ``scripts/compute_archetypes.py``
#   ``outputs/clusters.csv``        produced by the same script
#
# Run the pipeline first if those files are missing:
#
#     pixi run python scripts/compute_archetypes.py
#     pixi run python scripts/make_figures.py --figure fig07_archetypes

# %%
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from ar7_ch5 import figures
from ar7_ch5.classification import GW_ORDER
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig07_archetypes"

# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
figures.apply_style()

# %% [markdown]
# ## Load archetype data

# %%
root = repo_root()
archetypes_path = root / "outputs" / "archetypes.csv"
clusters_path = root / "outputs" / "clusters.csv"

if not archetypes_path.exists():
    raise FileNotFoundError(
        f"Archetypes CSV not found: {archetypes_path}\n"
        "  produce with: pixi run python scripts/compute_archetypes.py"
    )

archetypes = pd.read_csv(archetypes_path)
clusters = pd.read_csv(clusters_path)

print(f"Archetype cells populated: {len(archetypes)}")
print(f"Strategies: {archetypes['strategy_label'].nunique()}")
print(f"GW classes covered: {sorted(archetypes['gw_class'].unique())}")

# %% [markdown]
# ## Figure layout helpers

# %%
# GW class column order (subset of GW_ORDER that actually appear)
gw_present = [g for g in GW_ORDER if g in archetypes["gw_class"].values]

# Strategy row order: sort by CE bin, then drawdown band, then suffix
def _sort_key(label: str) -> tuple:
    # label format: CC{bin}-{drawdown}-{suffix}
    parts = label.split("-", 2)
    bin_order = {"CC1000": 0, "CC1500": 1, "CC3000": 2, "CC3000+": 3}
    db_order = {"over": 0, "nz": 1, "pos": 2}
    ce = bin_order.get(parts[0] if parts else "", 99)
    db = db_order.get(parts[1] if len(parts) > 1 else "", 99)
    suffix = parts[2] if len(parts) > 2 else ""
    return (ce, db, suffix)

strategies = sorted(archetypes["strategy_label"].unique(), key=_sort_key)

n_rows = len(strategies)
n_cols = len(gw_present)

# %% [markdown]
# ## Build grid lookup

# %%
# cell_map[(strategy, gw)] = (short_label, source)
cell_map: dict[tuple[str, str], tuple[str, str]] = {}
for _, row in archetypes.iterrows():
    strat = row["strategy_label"]
    gw = row["gw_class"]
    # Short label: for ESM use scenario id; for SCI use IAM abbreviation + scenario
    if row["source"] == "smip":
        short = str(row["Scenario"])
    else:
        # Abbreviate IAM model name
        model_abbrev = str(row["Model"]).split("/")[0][:8]
        scen_abbrev = str(row["Scenario"])[:12]
        short = f"{model_abbrev}\n{scen_abbrev}"
    cell_map[(strat, gw)] = (short, str(row["source"]))

# %% [markdown]
# ## Draw figure

# %%
fig_width = max(10, n_cols * 1.8)
fig_height = max(6, n_rows * 0.65)
fig, ax = plt.subplots(figsize=(fig_width, fig_height))

ax.set_xlim(-0.5, n_cols - 0.5)
ax.set_ylim(-0.5, n_rows - 0.5)
ax.invert_yaxis()

# Background grid
for i in range(n_rows):
    for j in range(n_cols):
        ax.add_patch(
            FancyBboxPatch(
                (j - 0.45, i - 0.45),
                0.9, 0.9,
                boxstyle="round,pad=0.02",
                linewidth=0.3,
                edgecolor="#cccccc",
                facecolor="#f8f8f8",
            )
        )

# Cell contents
for i, strat in enumerate(strategies):
    for j, gw in enumerate(gw_present):
        key = (strat, gw)
        if key not in cell_map:
            continue
        short_label, source = cell_map[key]
        fc = "#d4e8ff" if source == "smip" else "#ffffff"
        ec = "#3a7ebf" if source == "smip" else "#aaaaaa"
        lw = 1.2 if source == "smip" else 0.5
        ax.add_patch(
            FancyBboxPatch(
                (j - 0.45, i - 0.45),
                0.9, 0.9,
                boxstyle="round,pad=0.02",
                linewidth=lw,
                edgecolor=ec,
                facecolor=fc,
            )
        )
        fontsize = 4.5 if source == "sci" else 6
        ax.text(
            j, i, short_label,
            ha="center", va="center",
            fontsize=fontsize,
            color="#222222" if source == "sci" else "#003366",
            fontweight="bold" if source == "smip" else "normal",
            wrap=True,
        )

# Axis labels
ax.set_xticks(range(n_cols))
ax.set_xticklabels(gw_present, fontsize=8, rotation=45, ha="right")
ax.set_yticks(range(n_rows))
ax.set_yticklabels(strategies, fontsize=6.5)

ax.set_xlabel("Warming category (GW class)", fontsize=10, labelpad=6)
ax.set_ylabel("Emissions strategy cluster", fontsize=10, labelpad=6)
ax.set_title(
    "Emissions archetypes: representative pathways per (strategy, GW) cell\n"
    r"$\bf{Blue}$" + " = ScenarioMIP CMIP7 ESM;  White = SCI nearest-centroid",
    fontsize=9,
    pad=10,
)

ax.tick_params(axis="both", which="both", length=0)
ax.spines[["top", "right", "bottom", "left"]].set_visible(False)

plt.tight_layout()

# %% [markdown]
# ## Save figure

# %%
for fmt in cfg.get("output_formats", ["png", "pdf"]):
    out_path = root / "outputs" / "figures" / f"{FIGURE_ID}.{fmt}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300 if fmt == "png" else None, bbox_inches="tight")
    print(f"Saved: {out_path}")

plt.show()
