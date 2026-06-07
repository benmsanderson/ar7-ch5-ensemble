# %% [markdown]
# # Figure 07 - Emissions archetypes grid (strategy × GW class)
#
# Canonical strategy × warming grid: each cell shows the (Model, Scenario)
# selected as representative for that (emissions-strategy cluster, GW class)
# combination.  Where a reference pathway (ScenarioMIP CMIP7 or SSP2-COM)
# shares a cell's strategy cluster and GW class it is the representative pick,
# coloured with the fig05 GMD palette; the remaining cells use the SCI
# nearest-centroid scenario.
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

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Patch

from ar7_ch5 import figures
from ar7_ch5.classification import GW_ORDER
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig07_archetypes"

# Reference-pathway colours, matching fig05_scenariomip_extensions.py.
GMD_PATHWAY_COLORS = {
    "VL": "#16188F",
    "LN": "#22e5db",
    "L": "#20A359",
    "ML": "#dec820",
    "M": "#fc7b03",
    "H": "#a41212",
    "HL": "#E744F6",
}
# SSP2-COM is not part of the GMD ScenarioMIP set; use its classification colour.
SSP2COM_COLOR = "#8ecda0"


def _reference_color(source: str, scenario: str) -> str:
    """Fill colour for a reference cell representative."""
    if source == "ssp2com":
        return SSP2COM_COLOR
    return GMD_PATHWAY_COLORS.get(str(scenario), "#d4e8ff")


def _text_color(hex_color: str) -> str:
    """Black or white text depending on the background luminance."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[k : k + 2], 16) / 255 for k in (0, 2, 4))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luminance > 0.6 else "#ffffff"

# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)

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
# cell_map[(strategy, gw)] = (short_label, source, scenario)
cell_map: dict[tuple[str, str], tuple[str, str, str]] = {}
for _, row in archetypes.iterrows():
    strat = row["strategy_label"]
    gw = row["gw_class"]
    source = str(row["source"])
    scenario = str(row["Scenario"])
    # Short label: references show the scenario id; SCI shows IAM + scenario
    if source in ("smip", "ssp2com"):
        short = scenario
    else:
        # Abbreviate IAM model name
        model_abbrev = str(row["Model"]).split("/")[0][:8]
        scen_abbrev = scenario[:12]
        short = f"{model_abbrev}\n{scen_abbrev}"
    cell_map[(strat, gw)] = (short, source, scenario)

# %% [markdown]
# ## Draw figure

# %%
fig_width = max(10, n_cols * 1.8)*0.5
fig_height = max(6, n_rows * 0.65)*0.7
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
        short_label, source, scenario = cell_map[key]
        is_ref = source in ("smip", "ssp2com")
        if is_ref:
            fc = _reference_color(source, scenario)
            ec = "#222222"
            lw = 1.2
        else:
            fc = "#ffffff"
            ec = "#aaaaaa"
            lw = 0.5
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
        fontsize = 4.5 if not is_ref else 6
        ax.text(
            j, i, short_label,
            ha="center", va="center",
            fontsize=fontsize,
            color=_text_color(fc) if is_ref else "#222222",
            fontweight="bold" if is_ref else "normal",
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
    "Coloured = ScenarioMIP CMIP7 / SSP2-COM reference;  White = SCI nearest-centroid",
    fontsize=9,
    pad=10,
)

ax.tick_params(axis="both", which="both", length=0)
ax.spines[["top", "right", "bottom", "left"]].set_visible(False)

# Legend: reference pathways present in the grid, coloured by the GMD palette.
present_refs = {
    (src, scen)
    for (_short, src, scen) in cell_map.values()
    if src in ("smip", "ssp2com")
}
legend_handles = []
for scen in [s for s in GMD_PATHWAY_COLORS if ("smip", s) in present_refs]:
    legend_handles.append(
        Patch(facecolor=GMD_PATHWAY_COLORS[scen], edgecolor="#222222", label=scen)
    )
if any(src == "ssp2com" for src, _ in present_refs):
    legend_handles.append(
        Patch(facecolor=SSP2COM_COLOR, edgecolor="#222222", label="SSP2-COM")
    )
legend_handles.append(
    Patch(facecolor="#ffffff", edgecolor="#aaaaaa", label="SCI nearest-centroid")
)
ax.legend(
    handles=legend_handles,
    loc="upper left", bbox_to_anchor=(1.01, 1.0),
    fontsize=6.5, frameon=False,
    title="Reference scenarios", title_fontsize=7,
)

# ---- Explanatory key in the empty corners of the (triangular) grid ----
# The label format is CC{budget}-{drawdown}-{strategy}; each segment is decoded
# below.  The grid only populates a diagonal band, leaving the top-right and
# bottom-left corners free for the key.
_BUDGET_KEY = [
    ("CC1000", "\u2264 1000 Gt net CO\u2082 to net-zero"),
    ("CC1500", "1000\u20131500 Gt"),
    ("CC3000", "1500\u20133000 Gt"),
    ("CC3000+", "> 3000 Gt"),
]
_DRAWDOWN_KEY = [
    ("over", "net-negative overshoot after net-zero"),
    ("nz", "settles around net-zero"),
    ("pos", "stays net-positive"),
]
_STRATEGY_KEY = [
    ("base", "no single dominant lever"),
    ("cdr", "CDR \u2265 25% of gross CO\u2082 removed"),
    ("ch4", "methane cut \u2265 50% by 2050"),
    ("slcf", "aerosol / SO\u2082 cleanup dominant"),
    ("lockin", "fossil lock-in / deferred action"),
]


def _draw_key(x, y, title, entries, *, ha="left"):
    """Draw a titled, monospace-aligned decoder block in axes fractions."""
    ax.text(
        x, y, title, transform=ax.transAxes, ha=ha, va="top",
        fontsize=7.5, fontweight="bold", color="#222222",
    )
    width = max(len(tok) for tok, _ in entries)
    body = "\n".join(f"{tok:<{width}s}  {desc}" for tok, desc in entries)
    ax.text(
        x, y - 0.035, body, transform=ax.transAxes, ha=ha, va="top",
        fontsize=6, family="monospace", color="#333333", linespacing=1.45,
    )


# Only show strategy tokens that actually appear in the grid.
_present_strats = {lbl.split("-", 2)[2] for lbl in strategies if lbl.count("-") >= 2}
_strategy_entries = [e for e in _STRATEGY_KEY if e[0] in _present_strats]

# Top-right empty triangle: carbon budget + drawdown band.
_draw_key(0.62, 0.985, "Carbon budget  (CC\u2026)", _BUDGET_KEY)
_draw_key(0.62, 0.80, "Drawdown band", _DRAWDOWN_KEY)

# Bottom-left empty triangle: dominant mitigation strategy.
_draw_key(0.015, 0.26, "Dominant strategy", _strategy_entries)

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
