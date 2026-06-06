# ---
# jupyter:
#   jupytext:
#     formats: notebooks///py:percent,notebooks///ipynb
# ---

# %% [markdown]
# # Figure 04 - SSP2-COM driving emissions: chapter vs Charlie Koven
#
# Reference comparison of the chapter's SSP2-COM harmoniser output against
# Charlie Koven's FaIR-only SSP2-COM pipeline (the `ar7_wg1_ch5` ZOD
# repository). Reads the per-(species, year) CSV that
# `scripts/validate_ssp2com_vs_charlie.py` produces during M5.
#
# Two systematic differences come out and both are documented choices,
# not bugs (see `docs/methods.md`):
#
# 1. **Charlie's L-fallback.** Eight HFCs (HFC-23, HFC-32, HFC-125,
#    HFC-134a, HFC-143a, HFC-227ea, HFC-245fa, HFC-4310mee) are not in
#    Charlie's SSP2-COM CSV; his pipeline fills them with the L scenario
#    as default. The chapter pulls these from the scenariocompass
#    world-total xlsx instead, so we have a real SSP2-COM trajectory.
#    These species are NOT a harmonisation disagreement; they're
#    plotted separately and flagged.
#
# 2. **PFC 2025 baseline anomaly.** Three PFCs (C2F6, CF4, C6F14) show
#    large 2025 differences (up to ~220% for C2F6) because the
#    published 2023 global history endpoint disagrees with the IAM's
#    2023 estimate by a large factor; the linear taper on a big
#    correction creates a transient bump that resolves by 2050. This
#    is intrinsic to the ratio-with-convergence harmoniser when
#    scenario and history disagree on baseline magnitude.

# %%
from __future__ import annotations

import sys

import matplotlib.pyplot as plt
import pandas as pd

from ar7_ch5 import figures
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig04_ssp2com_validation"

# %% [markdown]
# ## Load config + validation CSV

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)

csv_path = repo_root() / "outputs" / "ssp2com" / "validation_vs_charlie.csv"
if not csv_path.is_file():
    raise FileNotFoundError(
        f"Required input is missing: {csv_path.relative_to(repo_root())}. "
        "Generate it with: pixi run python "
        "scripts/validate_ssp2com_vs_charlie.py"
    )

df = pd.read_csv(csv_path)
print(f"loaded {len(df)} rows from {csv_path.name}")
print(f"  {df['charlie_variable'].nunique()} species "
      f"({df.loc[~df['charlie_used_l_fallback'], 'charlie_variable'].nunique()} "
      f"true-overlap, "
      f"{df.loc[df['charlie_used_l_fallback'], 'charlie_variable'].nunique()} "
      f"L-fallback) at years {sorted(df['year'].unique())}")

# %% [markdown]
# ## Per-species summary: maximum |relative difference| across years
#
# True overlap means both pipelines source from SSP2-COM and the
# difference is purely the harmoniser's contribution. L-fallback means
# Charlie's CSV doesn't carry that species and his pipeline silently
# substitutes the L scenario; the difference there is a scenario mismatch,
# not a harmonisation disagreement.

# %%
def _max_abs_pct(frame: pd.DataFrame) -> pd.Series:
    """Per-species max |relative diff|, robust to near-zero Charlie baselines.

    Charlie's pipeline drops a few species (notably HFC-32) to ~1e-15 by
    2100, which is an end-of-century floor rather than a meaningful
    baseline. Computing the relative diff against that floor blows up
    by ~15 orders of magnitude even when the absolute disagreement is
    small. Filter out year rows where Charlie's value is below 1% of
    that species' own peak before taking the per-species max.
    """
    def _per_species(grp: pd.DataFrame) -> float:
        peak = grp["charlie"].abs().max()
        meaningful = grp.loc[grp["charlie"].abs() >= 0.01 * peak]
        if meaningful.empty:
            return float("nan")
        return meaningful["relative_difference_pct"].abs().max()

    return (
        frame.groupby("charlie_variable")
        .apply(_per_species, include_groups=False)
        .dropna()
        .sort_values()
    )


overlap = df.loc[~df["charlie_used_l_fallback"]]
fallback = df.loc[df["charlie_used_l_fallback"]]

overlap_max = _max_abs_pct(overlap)
fallback_max = _max_abs_pct(fallback)

print("\nTrue-overlap max |relative diff| (sorted, %):")
for sp, m in overlap_max.items():
    print(f"  {sp:15s}  {m:7.1f}%")

print("\nL-fallback max |relative diff| (sorted, %):")
for sp, m in fallback_max.items():
    print(f"  {sp:15s}  {m:7.1f}%")

# %% [markdown]
# ## Plot
#
# Two-panel horizontal bar chart, shared symlog x-axis so the PFC outliers
# in the overlap set don't squash the main-GHG bars but small values stay
# readable. Linear-region near zero is kept up to +/-15% (Riahi 2026
# "agree within 15%" rule of thumb on harmonised aggregates).

# %%
fig, (ax_top, ax_bot) = plt.subplots(
    nrows=2, ncols=1,
    figsize=(7.5, 7.0),
    gridspec_kw={"height_ratios": [len(overlap_max), len(fallback_max)]},
    sharex=True,
)

linthresh = 15.0
sane_thresh = 15.0  # 15 percentage points is the Riahi-aggregate threshold

# True-overlap species: bars colour-coded green (within 15%), orange
# (15-50%), red (over 50%, the PFC baseline-anomaly cohort).
def _bar_colour(pct: float) -> str:
    if pct < 15:
        return "#4caf50"
    if pct < 50:
        return "#ff9800"
    return "#d43820"


ax_top.barh(
    range(len(overlap_max)), overlap_max.values,
    color=[_bar_colour(v) for v in overlap_max.values],
    edgecolor="black", linewidth=0.4,
)
ax_top.set_yticks(range(len(overlap_max)))
ax_top.set_yticklabels(overlap_max.index)
ax_top.axvline(
    sane_thresh, color="#666", linestyle="--", linewidth=0.7,
    label="15% (Riahi 2026 aggregate-agreement threshold)",
)
ax_top.set_title(
    "True overlap: both pipelines source SSP2-COM "
    f"({len(overlap_max)} species)",
    fontsize=10, loc="left",
)
ax_top.legend(loc="lower right", fontsize=8, frameon=False)
ax_top.set_xscale("symlog", linthresh=linthresh)
ax_top.spines["top"].set_visible(False)
ax_top.spines["right"].set_visible(False)

# L-fallback species: render in grey with hatch to make clear these are
# scenario mismatches, not harmonisation disagreements.
ax_bot.barh(
    range(len(fallback_max)), fallback_max.values,
    color="#bdbdbd", edgecolor="black", linewidth=0.4, hatch="///",
)
ax_bot.set_yticks(range(len(fallback_max)))
ax_bot.set_yticklabels(fallback_max.index)
ax_bot.axvline(sane_thresh, color="#666", linestyle="--", linewidth=0.7)
ax_bot.set_title(
    "Charlie's L-fallback: his CSV lacks these species "
    f"({len(fallback_max)} species; difference is scenario, not harmoniser)",
    fontsize=10, loc="left",
)
ax_bot.set_xscale("symlog", linthresh=linthresh)
ax_bot.set_xlabel(
    "max |relative difference| across 2025/2050/2075/2100 "
    "(symlog, linear inside +/-15%)"
)
ax_bot.spines["top"].set_visible(False)
ax_bot.spines["right"].set_visible(False)

# Custom x-axis ticks at 0, 15, 50, 100, 200 for readability.
xticks = [0, 15, 50, 100, 200]
for ax in (ax_top, ax_bot):
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"{t}%" for t in xticks])
    ax.set_xlim(0, max(250, overlap_max.max() * 1.1))

fig.suptitle(cfg.get("title", FIGURE_ID), fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.97))

# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")

sys.exit(0)
