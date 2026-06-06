# %% [markdown]
# # Figure 03 - GW0-GW8 warming classification per SCM
#
# Cross-source summary of the chapter's per-SCM warming classification.
#
# - Left panel: SCI per-SCM stacked bars (4 stacks side by side --
#   xlsx-MAGICC regression reference, FaIR, CICERO, MAGICC -- each
#   stack a tally of how many of the 330 vetted SCI pathways land in
#   each Riahi 2026 (Table SI.3) GW category).
# - Right panel: 3 (SCM) x 8 (pathway) coloured grid covering the
#   ScenarioMIP CMIP7 baselines (VL, L, LN, M, ML, H, HL) and SSP2-COM.
#   Each cell coloured by GW category; text shows the GW short id and
#   the median end-of-century warming in K. Pathways ordered by mean
#   EoC warming across SCMs (cold left -> hot right).
#
# The SCMs see identical input emissions; the per-stack / per-cell
# spread is the chapter's three-SCM ensemble value-add over the
# SCI-vintage MAGICC-only baseline.
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

# Per-stack ordering for the SCI panel: xlsx-MAGICC baseline plus the
# three SCMs.
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


def _per_pathway_grid(*csv_paths: Path) -> pd.DataFrame:
    """Long DataFrame combining ScenarioMIP CMIP7 + SSP2-COM classifications.

    Returns rows of (climate_model, Scenario, category, eoc_warming_50).
    Only includes CSVs that exist on disk. Used for the per-pathway grid
    on the right of fig03.
    """
    pieces: list[pd.DataFrame] = []
    for p in csv_paths:
        if not p.is_file():
            continue
        df = pd.read_csv(p)[
            ["climate_model", "Scenario", "category", "eoc_warming_50"]
        ].copy()
        pieces.append(df)
    if not pieces:
        return pd.DataFrame(
            columns=["climate_model", "Scenario", "category", "eoc_warming_50"]
        )
    return pd.concat(pieces, ignore_index=True)


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


def _draw_pathway_grid(
    ax, df: pd.DataFrame, *,
    scm_order: list[str], palette: dict[str, str],
) -> None:
    """3 x n_pathway colour grid; cells coloured by GW category.

    Each cell shows the category short id and the median EoC warming.
    Pathways are ordered ascending by mean EoC warming across SCMs.
    """
    pathway_order = (
        df.groupby("Scenario", observed=True)["eoc_warming_50"]
        .mean().sort_values().index.tolist()
    )
    cat_grid = df.pivot(
        index="climate_model", columns="Scenario", values="category",
    ).reindex(index=scm_order, columns=pathway_order)
    eoc_grid = df.pivot(
        index="climate_model", columns="Scenario", values="eoc_warming_50",
    ).reindex(index=scm_order, columns=pathway_order)

    for i in range(len(scm_order)):
        for j in range(len(pathway_order)):
            category = cat_grid.iat[i, j]
            colour = palette.get(category, "#dddddd")
            ax.add_patch(plt.Rectangle(
                (j, len(scm_order) - 1 - i), 1, 1,
                facecolor=colour, edgecolor="white", linewidth=1.0,
            ))
            eoc = eoc_grid.iat[i, j]
            # GW4 / GW5 (yellow / orange) read better with black text;
            # the darker GW0-GW3 and GW6-GW8 cells get white text.
            light_cats = {"GW4", "GW5", "unclassified"}
            text_colour = "black" if category in light_cats else "white"
            ax.text(
                j + 0.5, len(scm_order) - 1 - i + 0.5,
                f"{category}\n{eoc:.1f} K",
                ha="center", va="center",
                fontsize=8, color=text_colour, weight="bold",
            )

    ax.set_xlim(0, len(pathway_order))
    ax.set_ylim(0, len(scm_order))
    ax.set_aspect("equal")
    ax.set_xticks(np.arange(len(pathway_order)) + 0.5)
    ax.set_xticklabels(pathway_order, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(np.arange(len(scm_order)) + 0.5)
    ax.set_yticklabels(
        [SCM_SHORT_LABELS.get(s, s) for s in reversed(scm_order)],
        fontsize=9,
    )
    ax.set_title(
        "ScenarioMIP CMIP7 + SSP2-COM per (SCM, pathway)",
        fontsize=11, loc="left",
    )
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(length=0)


SCM_GRID_ORDER = ["FaIRv2.2.4", "CICERO-SCM-PY2.1.2", "MAGICCv7.5.3"]


# %% [markdown]
# ## Load + tally

# %%
sci_counts = _stack_counts_sci()
print("SCI per-stack counts (vetted, columns are stacks, rows are GW categories):")
print(sci_counts.to_string())

scenariomip_csv = (
    repo_root() / "outputs" / "classification_per_model_scenariomip.csv"
)
ssp2com_csv = repo_root() / "outputs" / "classification_per_model_ssp2com.csv"

# Combined per-pathway frame for the right panel.
per_pathway = _per_pathway_grid(scenariomip_csv, ssp2com_csv)
if not per_pathway.empty:
    print(
        f"\nPer-pathway grid (ScenarioMIP CMIP7 + SSP2-COM): "
        f"{per_pathway['Scenario'].nunique()} pathways "
        f"x {per_pathway['climate_model'].nunique()} SCMs."
    )
else:
    print(
        "\nWARNING: ScenarioMIP / SSP2-COM CSVs missing. Generate with:\n"
        "  pixi run python scripts/classify.py "
        "--source per_model --input-source scenariomip\n"
        "  pixi run python scripts/classify.py "
        "--source per_model --input-source ssp2com"
    )


# %% [markdown]
# ## Plot

# %%
has_grid = not per_pathway.empty
n_grid_pathways = per_pathway["Scenario"].nunique() if has_grid else 0

if has_grid:
    width_ratios = [len(sci_counts.columns), n_grid_pathways]
    fig_width = 2.0 + 1.4 * sum(width_ratios)
    fig, (ax_sci, ax_grid) = plt.subplots(
        nrows=1, ncols=2,
        figsize=(fig_width, 5.8),
        gridspec_kw={"width_ratios": width_ratios},
    )
else:
    fig, ax_sci = plt.subplots(
        nrows=1, ncols=1,
        figsize=(2.0 + 1.4 * len(sci_counts.columns), 5.2),
    )

_draw_stacks(
    ax_sci, sci_counts,
    title="SCI (vetted, 330 pathways)",
    palette=style.gw_colors,
    show_category_legend=True,
)
ax_sci.set_ylabel("Number of pathways")

if has_grid:
    _draw_pathway_grid(
        ax_grid, per_pathway,
        scm_order=SCM_GRID_ORDER, palette=style.gw_colors,
    )

# Shared GW-category legend at the figure level. matplotlib only honours
# label= on artists drawn on the axis we call .legend() on, so pull
# handles+labels from the SCI stack and place them on the figure.
handles, labels = ax_sci.get_legend_handles_labels()
fig.legend(
    handles, labels,
    title="GW category (Riahi 2026 SI.3)",
    loc="center right", bbox_to_anchor=(1.0, 0.5),
    fontsize=8, frameon=False, title_fontsize=9,
)

fig.suptitle(cfg.get("title", FIGURE_ID), fontsize=12)
fig.tight_layout(rect=(0, 0, 0.92, 0.96))


# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")

sys.exit(0)
