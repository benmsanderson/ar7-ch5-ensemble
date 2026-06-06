# ---
# jupyter:
#   jupytext:
#     formats: notebooks///py:percent,notebooks///ipynb
# ---

# %% [markdown]
# # Figure 06 - Per-SCM grid (CO2, CH4, ERF, GSAT)
#
# Four-row, three-column grid where each column is one SCM (FaIR,
# CICERO-SCM, MAGICC) and each row is one diagnostic:
#
# 1. Atmospheric CO2 concentration (ppm)
# 2. Atmospheric CH4 concentration (ppb)
# 3. Total effective radiative forcing (W/m^2)
# 4. Surface air temperature anomaly above 1850-1900 (K)
#
# Per panel, all seven ScenarioMIP CMIP7 pathways are overlaid with
# the GMD pathway colours, each as a 5-95% percentile band + median
# line across that SCM's posterior members. Easier than fig05 to read
# the per-SCM behaviour because the SCMs are separated by column
# rather than overlaid in the same panel.
#
# Inputs: `outputs/scenariomip_cmip7/<scm>/scenariomip_<pathway>.nc`
# for each scm in {fair, ciceroscm, magicc} and pathway in
# {VL, L, LN, M, ML, H, HL}. Produce with:
#
#     pixi run python scripts/run_scenarios.py \\
#         --experiment scenariomip_cmip7 \\
#         --models fair ciceroscm magicc \\
#         --n-members 200 --end-year 2500

# %%
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import scmdata

from ar7_ch5 import figures
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig06_per_scm_grid"

GMD_PATHWAY_COLORS = {
    "VL": "#16188F",
    "LN": "#22e5db",
    "L":  "#20A359",
    "ML": "#dec820",
    "M":  "#fc7b03",
    "H":  "#a41212",
    "HL": "#E744F6",
}

SCM_LABELS = {
    "fair":      "FaIR 2.x",
    "ciceroscm": "CICERO-SCM 2.1.2",
    "magicc":    "MAGICC v7.5.3",
}

# (row label, openscm-runner variable, unit, y-axis lower-bound).
ROWS = [
    ("Atmospheric CO$_2$, ppm",
     "Atmospheric Concentrations|CO2", None),
    ("Atmospheric CH$_4$, ppb",
     "Atmospheric Concentrations|CH4", None),
    ("Total ERF, W m$^{-2}$",
     "Effective Radiative Forcing", None),
    ("GSAT anomaly vs 1850-1900, K",
     "Surface Air Temperature Change", "anomaly"),
]


# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)

pathways = list(cfg.get("pathways", GMD_PATHWAY_COLORS))
models = list(cfg.get("models", list(SCM_LABELS)))


# %% [markdown]
# ## Helpers

# %%
def _nc_path(scm: str, pathway: str) -> Path:
    return (
        repo_root() / "outputs" / "scenariomip_cmip7" / scm
        / f"scenariomip_{pathway}.nc"
    )


def _quantiles(
    scm: str, pathway: str, variable: str,
    qs: tuple[float, ...] = (0.05, 0.5, 0.95),
    anomaly_baseline: tuple[int, int] | None = None,
) -> pd.DataFrame | None:
    """Return columns {0.05, 0.5, 0.95} indexed by integer year.

    Returns ``None`` if the NetCDF is missing or the variable absent.
    If ``anomaly_baseline`` is set (e.g. ``(1850, 1900)``), subtract
    the median pre-baseline so the trace is an anomaly.
    """
    nc = _nc_path(scm, pathway)
    if not nc.is_file():
        print(f"  missing: {nc.relative_to(repo_root())}", file=sys.stderr)
        return None
    run = scmdata.ScmRun.from_nc(nc).filter(variable=variable)
    if run.shape[0] == 0:
        return None
    ts = run.timeseries(time_axis="year").astype(float)
    q = ts.quantile(list(qs), axis=0).T.rename(
        columns=dict(zip(qs, qs, strict=True))
    )
    if anomaly_baseline is not None:
        ref_years = [
            y for y in q.index
            if anomaly_baseline[0] <= y <= anomaly_baseline[1]
        ]
        if ref_years:
            q = q - q.loc[ref_years, 0.5].mean()
    return q


# %% [markdown]
# ## Load all (scm, pathway, variable) quantile slices

# %%
data: dict[tuple[str, str, str], pd.DataFrame | None] = {}
for scm in models:
    for pathway in pathways:
        for _, variable, mode in ROWS:
            anchor = (1850, 1900) if mode == "anomaly" else None
            data[(scm, pathway, variable)] = _quantiles(
                scm, pathway, variable, anomaly_baseline=anchor,
            )

missing = sum(1 for v in data.values() if v is None)
if missing:
    print(
        f"WARNING: {missing} (scm, pathway, variable) slices missing; "
        "those bands will be skipped."
    )
    print(
        "  produce with: pixi run python scripts/run_scenarios.py "
        f"--experiment scenariomip_cmip7 --models {' '.join(models)} "
        "--n-members 200 --end-year 2500"
    )


# %% [markdown]
# ## Plot the 4 x 3 grid

# %%
PLOT_START = 1980
PLOT_END = 2500

fig, axes = plt.subplots(
    nrows=len(ROWS), ncols=len(models),
    figsize=(4.2 * len(models), 3.0 * len(ROWS)),
    sharex=True,
)
if len(ROWS) == 1:
    axes = [axes]
if len(models) == 1:
    axes = [[a] for a in axes]

for row_idx, (row_label, variable, _) in enumerate(ROWS):
    for col_idx, scm in enumerate(models):
        ax = axes[row_idx][col_idx]
        for pathway in pathways:
            q = data.get((scm, pathway, variable))
            if q is None:
                continue
            years = [y for y in q.index if PLOT_START <= y <= PLOT_END]
            if not years:
                continue
            qs = q.loc[years]
            col = GMD_PATHWAY_COLORS[pathway]
            ax.fill_between(
                qs.index, qs[0.05].values, qs[0.95].values,
                color=col, alpha=0.20, lw=0,
            )
            ax.plot(
                qs.index, qs[0.5].values,
                color=col, lw=1.4, label=pathway,
            )
        # Reference zero line for ERF and anomaly rows.
        ax.axhline(0, ls=":", color="k", lw=0.5)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(PLOT_START, PLOT_END)
        # Column header on the top row only.
        if row_idx == 0:
            ax.set_title(SCM_LABELS.get(scm, scm), fontsize=11, loc="center")
        # Row label on the left column only.
        if col_idx == 0:
            ax.set_ylabel(row_label, fontsize=9)
        # X-axis label on the bottom row only.
        if row_idx == len(ROWS) - 1:
            ax.set_xlabel("Year")

# Shared y-axis range per row so panels are comparable across SCMs.
for row_idx in range(len(ROWS)):
    row_axes = axes[row_idx]
    ymin = min(a.get_ylim()[0] for a in row_axes)
    ymax = max(a.get_ylim()[1] for a in row_axes)
    for a in row_axes:
        a.set_ylim(ymin, ymax)

# Single pathway legend at the bottom of the figure.
pathway_handles = [
    plt.Line2D(
        [], [], color=GMD_PATHWAY_COLORS[p], lw=2.2, label=p,
    )
    for p in pathways
]
fig.legend(
    handles=pathway_handles,
    loc="lower center", ncols=len(pathways), bbox_to_anchor=(0.5, -0.01),
    fontsize=9, frameon=False, title="Pathway",
)

fig.suptitle(cfg.get("title", FIGURE_ID), fontsize=12)
fig.tight_layout(rect=(0, 0.03, 1, 0.97))


# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")

sys.exit(0)
