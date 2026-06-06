# ---
# jupyter:
#   jupytext:
#     formats: notebooks///py:percent,notebooks///ipynb
# ---

# %% [markdown]
# # Figure 03 - GW0-GW8 warming classification per SCM
#
# Cross-source summary of the chapter's per-SCM warming classification.
# Three columns, one per chapter input set; per column a stacked bar per
# SCM (plus an xlsx-MAGICC reference stack for SCI) showing how many
# pathways land in each Riahi 2026 (Table SI.3) GW category.
#
# The SCMs see identical input emissions; the per-stack spread is the
# chapter's three-SCM ensemble value-add over the SCI-vintage MAGICC-only
# baseline.
#
# Inputs (all produced by `scripts/classify.py`):
#
# - `outputs/classification_xlsx.csv` (SCI MAGICC-baked-percentiles
#   regression path)
# - `outputs/classification_per_model.csv` (SCI per-SCM ensemble)
# - `outputs/classification_per_model_scenariomip.csv`
# - `outputs/classification_per_model_ssp2com.csv`
#
# Produce them with:
#
#     pixi run python scripts/classify.py --source xlsx
#     pixi run python scripts/classify.py --source per_model --input-source sci
#     pixi run python scripts/classify.py --source per_model --input-source scenariomip
#     pixi run python scripts/classify.py --source per_model --input-source ssp2com

# %%
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ar7_ch5 import figures
from ar7_ch5.classification import GW_ORDER
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig03_classification_per_scm"

# Per-stack ordering: SCI gets an xlsx-MAGICC baseline plus the three
# SCMs (4 stacks); ScenarioMIP and SSP2-COM get just the three SCMs.
SCM_DISPLAY_ORDER = ["xlsx-MAGICC", "FaIRv2.2.4", "CICERO-SCM-PY2.1.2", "MAGICCv7.5.3"]
SCM_SHORT_LABELS = {
    "xlsx-MAGICC":        "xlsx-MAGICC",
    "FaIRv2.2.4":         "FaIR",
    "CICERO-SCM-PY2.1.2": "CICERO",
    "MAGICCv7.5.3":       "MAGICC",
}


# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)


# %% [markdown]
# ## Helpers

# %%
def _counts_per_stack(df: pd.DataFrame, stack_col: str) -> pd.DataFrame:
    """Pivot a long classification CSV into (GW_category, stack) -> count."""
    counts = (
        df.groupby([stack_col, "category"], observed=True)
        .size()
        .reset_index(name="count")
        .pivot(index="category", columns=stack_col, values="count")
        .reindex(GW_ORDER)
        .fillna(0)
        .astype(int)
    )
    return counts


def _stack_counts_sci() -> pd.DataFrame:
    """Per-SCM SCI counts (vetted only) plus the xlsx-MAGICC reference stack."""
    per_model = pd.read_csv(
        repo_root() / "outputs" / "classification_per_model.csv"
    )
    vetted = per_model.loc[
        (per_model["vetting_status"] == "passed")
        & per_model["climate_model"].notna()
    ].copy()

    per_scm = _counts_per_stack(vetted, "climate_model")

    xlsx_path = repo_root() / "outputs" / "classification_xlsx.csv"
    if xlsx_path.is_file():
        xlsx = pd.read_csv(xlsx_path)
        xlsx_vetted = xlsx.loc[xlsx["vetting_status"] == "passed"].copy()
        xlsx_vetted["climate_model"] = "xlsx-MAGICC"
        xlsx_counts = _counts_per_stack(xlsx_vetted, "climate_model")
        # Concatenate the xlsx reference column on the left.
        per_scm = pd.concat([xlsx_counts, per_scm], axis=1)

    # Order columns by SCM_DISPLAY_ORDER, dropping any missing.
    ordered = [c for c in SCM_DISPLAY_ORDER if c in per_scm.columns]
    return per_scm[ordered]


def _stack_counts_simple(csv_path: Path) -> pd.DataFrame:
    """Per-SCM counts for ScenarioMIP / SSP2-COM (no vetting; classification only)."""
    df = pd.read_csv(csv_path)
    counts = _counts_per_stack(df, "climate_model")
    ordered = [c for c in SCM_DISPLAY_ORDER if c in counts.columns]
    return counts[ordered]


def _draw_stacks(
    ax, counts: pd.DataFrame, *, title: str, palette: dict[str, str],
    show_category_legend: bool = False,
) -> None:
    """Draw side-by-side stacked bars (one stack per column of `counts`)."""
    stacks = list(counts.columns)
    positions = np.arange(len(stacks))
    bar_width = 0.7
    bottoms = np.zeros(len(stacks), dtype=float)
    for category in GW_ORDER:
        if category not in counts.index:
            continue
        values = counts.loc[category].values.astype(float)
        if not np.any(values > 0):
            continue
        ax.bar(
            positions, values, bottom=bottoms, width=bar_width,
            color=palette.get(category, "#888888"),
            edgecolor="black", linewidth=0.4,
            label=category if show_category_legend else None,
        )
        bottoms = bottoms + values
    # Per-stack totals above each bar (eyeballing the spread is the point).
    totals = counts.sum(axis=0).values
    for x, total in zip(positions, totals, strict=True):
        if total > 0:
            ax.text(
                x, total + max(totals) * 0.02, f"{int(total)}",
                ha="center", va="bottom", fontsize=8, color="#444",
            )
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [SCM_SHORT_LABELS.get(s, s) for s in stacks],
        rotation=15, ha="right", fontsize=9,
    )
    ax.set_title(title, fontsize=11, loc="left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# %% [markdown]
# ## Load + tally

# %%
sci_counts = _stack_counts_sci()
print("SCI per-stack counts (vetted, columns are stacks, rows are GW categories):")
print(sci_counts.to_string())

scenariomip_csv = (
    repo_root() / "outputs" / "classification_per_model_scenariomip.csv"
)
if scenariomip_csv.is_file():
    scenariomip_counts = _stack_counts_simple(scenariomip_csv)
    print("\nScenarioMIP per-stack counts:")
    print(scenariomip_counts.to_string())
else:
    scenariomip_counts = None
    print(
        "\nWARNING: ScenarioMIP CSV missing. Generate with:\n"
        "  pixi run python scripts/classify.py "
        "--source per_model --input-source scenariomip"
    )

ssp2com_csv = repo_root() / "outputs" / "classification_per_model_ssp2com.csv"
if ssp2com_csv.is_file():
    ssp2com_counts = _stack_counts_simple(ssp2com_csv)
    print("\nSSP2-COM per-stack counts:")
    print(ssp2com_counts.to_string())
else:
    ssp2com_counts = None
    print(
        "\nWARNING: SSP2-COM CSV missing. Generate with:\n"
        "  pixi run python scripts/classify.py "
        "--source per_model --input-source ssp2com"
    )


# %% [markdown]
# ## Plot

# %%
n_panels = 1 + (scenariomip_counts is not None) + (ssp2com_counts is not None)
width_ratios = []
sources_to_plot = []
sources_to_plot.append(("SCI (vetted, 330 pathways)", sci_counts))
width_ratios.append(len(sci_counts.columns))
if scenariomip_counts is not None:
    sources_to_plot.append(("ScenarioMIP CMIP7 (7 pathways)", scenariomip_counts))
    width_ratios.append(len(scenariomip_counts.columns))
if ssp2com_counts is not None:
    sources_to_plot.append(("SSP2-COM (1 pathway)", ssp2com_counts))
    width_ratios.append(len(ssp2com_counts.columns))

# Scale figure width to the total number of stacks across panels.
fig_width = 2.0 + 1.4 * sum(width_ratios)
fig, axes = plt.subplots(
    nrows=1, ncols=n_panels,
    figsize=(fig_width, 5.2),
    gridspec_kw={"width_ratios": width_ratios},
)
if n_panels == 1:
    axes = [axes]

for idx, ((title, counts), ax) in enumerate(zip(sources_to_plot, axes, strict=True)):
    _draw_stacks(
        ax, counts, title=title, palette=style.gw_colors,
        show_category_legend=(idx == 0),
    )
    if idx == 0:
        ax.set_ylabel("Number of pathways")

# Shared GW-category legend at the figure level. matplotlib only honours
# label= on artists drawn on the axis we call .legend() on, so pull
# handles+labels from the first panel and place them on the figure
# instead. Reserve right-edge space via tight_layout's rect so the
# legend doesn't clip.
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(
    handles, labels,
    title="GW category (Riahi 2026 SI.3)",
    loc="center right", bbox_to_anchor=(1.0, 0.5),
    fontsize=8, frameon=False, title_fontsize=9,
)

fig.suptitle(
    cfg.get("title", FIGURE_ID),
    fontsize=12,
)
fig.tight_layout(rect=(0, 0, 0.92, 0.97))


# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")

sys.exit(0)
