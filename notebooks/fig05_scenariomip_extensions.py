# %% [markdown]
# # Figure 05 - ScenarioMIP CMIP7 extensions (fig_extensions reproduction)
#
# Eight-panel diagnostic reproducing the layout of `fig_extensions` from
# scenariomip-paper-plots (Zenodo 20329427,
# `notebooks/0505_extensions_plotting.ipynb`) using the chapter's
# three-SCM pipeline:
#
# - Top row: annual + cumulative CO2 emissions; CH4 emissions; SO2
#   (Sulfur) emissions. These are sourced from the input emissions CSV
#   (`data/scenariomip_cmip7/emissions_1750-2500.csv`); they don't
#   depend on the SCM choice.
# - Middle row left: GHG emissions in CO2-equivalent (AR6 GWP100,
#   mass-adjusted), computed from the input emissions via the GMD
#   paper's `gwp_mass_adjusted_100y.csv`.
# - Bottom three: total effective radiative forcing, atmospheric CO2
#   concentration, and surface air temperature anomaly relative to
#   1850-1900. Each is drawn three times per pathway, one per SCM:
#   `fair` as a solid median + 5-95% percentile band; `ciceroscm` as a
#   dashed median; `magicc` as a dotted median. Pathway colour matches
#   the GMD paper convention.
#
# Inputs
# ------
# - `outputs/scenariomip_cmip7/<scm>/scenariomip_<pathway>.nc` for each
#   `pathway` in {VL, L, LN, M, ML, H, HL} and each `scm` in
#   {fair, ciceroscm, magicc}. Generate with:
#
#       pixi run python scripts/run_scenarios.py \\
#           --experiment scenariomip_cmip7 \\
#           --models fair ciceroscm magicc --n-members 200
#
# - `data/scenariomip_cmip7/emissions_1750-2500.csv` from
#   scenariomip-paper-plots.
# - `data/fair-inputs/gwp_mass_adjusted_100y.csv` from
#   scenariomip-paper-plots (staged externally; defaults to the path
#   on Ben's NAC checkout).

# %%
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scmdata

from ar7_ch5 import figures
from ar7_ch5.runners import repo_root

FIGURE_ID = "fig05_scenariomip_extensions"

# Pathway colours: GMD paper's scenario_colors (scripts/plotting.py), used
# verbatim here for strict reproduction of the published figure look. The
# chapter's shared style.yaml palette is similar but not identical; we
# override locally to stay 1:1 with the GMD reference.
GMD_PATHWAY_COLORS = {
    "VL": "#16188F",
    "LN": "#22e5db",
    "L":  "#20A359",
    "ML": "#dec820",
    "M":  "#fc7b03",
    "H":  "#a41212",
    "HL": "#E744F6",
}

# SCM -> line style. FaIR gets a solid line + the 5-95% band (it is the
# GMD reference). CICERO long-dashes, MAGICC dash-dot. We avoid the
# bare dotted style here because matplotlib renders ":" as very small
# dots that disappear under a 5-95% band at the chapter's default DPI.
SCM_LINESTYLES = {
    "fair":      "-",
    "ciceroscm": (0, (6, 3)),       # long dashes
    "magicc":    (0, (4, 1.5, 1, 1.5)),  # dash-dot-dot
}

DEFAULT_GMD_GWP_CSV = Path(
    "/storage/no-backup-nac/users/bensan/scenariomip-paper-plots/"
    "data/fair-inputs/gwp_mass_adjusted_100y.csv"
)
DEFAULT_EMISSIONS_CSV = (
    repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
)

# Output variable -> scmdata variable name on disk. Matches the openscm-
# runner output vocabulary.
SCM_VARIABLES = {
    "temperature": "Surface Air Temperature Change",
    "forcing":     "Effective Radiative Forcing",
    "co2_conc":    "Atmospheric Concentrations|CO2",
}


# %% [markdown]
# ## Load config + style

# %%
cfg = figures.load_config(FIGURE_ID)
style = figures.load_style()
figures.apply_style(style)

pathways = list(cfg.get("pathways", GMD_PATHWAY_COLORS))
models = list(cfg.get("models", list(SCM_LINESTYLES)))


# %% [markdown]
# ## Helpers: emissions + GHG CO2-eq + SCM NC loader / quantiles

# %%
def _load_input_emissions(csv: Path) -> pd.DataFrame:
    """Long form of the GMD CSV: (scenario_code, variable, year) -> value.

    The CSV uses the FaIR half-year convention (1750.5, 1751.5, ...);
    we truncate to integer years to match the SCM outputs' time axis.
    """
    df = pd.read_csv(csv)
    long_cols = [c for c in df.columns if c in {
        "model", "long_scenario", "region", "variable", "unit", "scenario",
    }]
    year_cols = []
    new_names = {}
    for c in df.columns:
        try:
            y = float(c)
        except (TypeError, ValueError):
            continue
        year_cols.append(c)
        new_names[c] = int(y)
    df = df[long_cols + year_cols].rename(columns=new_names)
    # Half-year columns can hit the same integer twice; drop duplicates.
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _emissions_series(
    emissions: pd.DataFrame, scenario_code: str, variable: str,
) -> pd.Series:
    row = emissions.loc[
        (emissions["scenario"] == scenario_code)
        & (emissions["variable"] == variable),
        :,
    ]
    if row.empty:
        return pd.Series(dtype=float)
    year_cols = [c for c in row.columns if isinstance(c, int)]
    s = row[year_cols].iloc[0]
    return pd.Series(s.values.astype(float), index=year_cols)


# AR6 WG1 GWP100 (mass-based) for the dominant Kyoto basket species. The
# GMD paper's mass-adjusted-GWP CSV uses a non-obvious unit convention;
# we recompute CO2-eq explicitly using AR6 WG1 SI Table 7.SM.7. Values
# kept short -- aerosols and ozone precursors carry GWP=0 by definition.
AR6_GWP100 = {
    "CO2 FFI":    1.0,
    "CO2 AFOLU":  1.0,
    "CH4":        27.9,
}
# Halocarbons (kt species). GWP values from AR6 WG1 7.SM.7; truncated to
# the species the chapter actually drives. Native emissions are in kt; the
# helper below converts to Mt before multiplying so output stays in
# MtCO2e/yr like the Mt species.
AR6_GWP100_KT = {
    "N2O":      273.0,
    "HFC-23":   14600.0, "HFC-32":     771.0,
    "HFC-125":  3740.0,  "HFC-134a":  1530.0,
    "HFC-143a": 5810.0,  "HFC-152a":   164.0,
    "HFC-227ea":3600.0,  "HFC-236fa": 8690.0,
    "HFC-245fa":962.0,   "HFC-365mfc": 914.0,
    "HFC-4310mee":1600.0,
    "CF4":      7380.0,  "C2F6":     12400.0,
    "C3F8":     9290.0,  "C4F10":   10000.0,
    "C5F12":    9220.0,  "C6F14":   10200.0,
    "C7F16":    9220.0,  "C8F18":   10300.0,
    "c-C4F8":  10200.0,  "SF6":     25200.0,
    "NF3":     17400.0,
    "CFC-11":  6230.0,   "CFC-12": 12500.0,
    "CFC-113": 6520.0,   "CFC-114": 9430.0,
    "CFC-115": 9600.0,
    "HCFC-22": 1960.0,   "HCFC-141b":860.0,  "HCFC-142b":2300.0,
    "CCl4":    2200.0,   "CH3Br":     2.4,    "CH3CCl3":  161.0,
    "CH3Cl":     5.5,    "CH2Cl2":   11.2,    "CHCl3":    20.6,
    "Halon-1202": 231.0, "Halon-1211":1990.0,
    "Halon-1301":7200.0, "Halon-2402":2170.0,
}


def _co2e_series(
    emissions: pd.DataFrame, scenario_code: str,
) -> pd.Series:
    """Sum species * AR6 GWP100 to MtCO2e/yr.

    Mt-unit species (CO2, CH4) multiplied directly; kt-unit halocarbons
    converted to Mt first. Aerosols and ozone precursors (BC, OC, SO2,
    NH3, NOx, CO, VOC) carry GWP=0 by AR6 convention and are skipped.
    """
    co2e: pd.Series | None = None
    for variable, weight in AR6_GWP100.items():
        s = _emissions_series(emissions, scenario_code, variable) * weight
        co2e = s if co2e is None else co2e.add(s, fill_value=0.0)
    for variable, weight in AR6_GWP100_KT.items():
        s = _emissions_series(emissions, scenario_code, variable)
        # native kt -> Mt before multiplying by GWP
        co2e = (s * weight / 1000.0).add(co2e, fill_value=0.0)
    if co2e is None:
        return pd.Series(dtype=float)
    return co2e


def _nc_path(scm: str, pathway: str) -> Path:
    return (
        repo_root() / "outputs" / "scenariomip_cmip7" / scm
        / f"scenariomip_{pathway}.nc"
    )


def _load_scm_quantiles(
    scm: str, pathway: str, variable_long: str,
    qs: tuple[float, ...] = (0.05, 0.5, 0.95),
) -> pd.DataFrame | None:
    """Return columns {0.05, 0.5, 0.95} indexed by integer year.

    Returns ``None`` (with a stderr note) if the NetCDF is missing so the
    figure can still render whatever is present. Cache-checked panels
    will warn at the end.
    """
    nc = _nc_path(scm, pathway)
    if not nc.is_file():
        print(f"  missing: {nc.relative_to(repo_root())}", file=sys.stderr)
        return None
    run = scmdata.ScmRun.from_nc(nc).filter(variable=variable_long)
    if run.shape[0] == 0:
        return None
    ts = run.timeseries(time_axis="year").astype(float)
    return ts.quantile(list(qs), axis=0).T.rename(
        columns=dict(zip(qs, qs, strict=True))
    )


# %% [markdown]
# ## Load inputs

# %%
emissions = _load_input_emissions(DEFAULT_EMISSIONS_CSV)
print(
    f"loaded emissions: {len(emissions)} rows "
    f"({emissions['scenario'].nunique()} scenarios, "
    f"{emissions['variable'].nunique()} species)"
)

# GWP100 weights are AR6 WG1 SI Table 7.SM.7 hard-coded above; no external
# CSV needed. AR6_GWP100 keys cover Mt-unit species, AR6_GWP100_KT covers
# the kt-unit halocarbon basket.
print(
    f"GHG CO2-eq computed from {len(AR6_GWP100)} Mt species + "
    f"{len(AR6_GWP100_KT)} kt species using AR6 WG1 GWP100."
)

available_ncs = {
    (scm, p): _nc_path(scm, p).is_file()
    for scm in models for p in pathways
}
missing = sorted([k for k, v in available_ncs.items() if not v])
if missing:
    print(
        f"WARNING: {len(missing)} (scm, pathway) NetCDFs are missing; "
        f"those bands will be skipped. First few: {missing[:5]}"
    )
    print(
        "  produce with: pixi run python scripts/run_scenarios.py "
        f"--experiment scenariomip_cmip7 --models {' '.join(models)} "
        "--n-members 200"
    )


# %% [markdown]
# ## Plot

# %%
HIST_END = 2024     # last historical year drawn in black
PLOT_END = 2500     # x-axis upper bound, matching the GMD CSV horizon
                    # (the chapter's emissions are extended to 2500 to
                    # exercise the long-tail extension period)
PLOT_START = 1850   # x-axis lower bound; pre-1980 is uninteresting
                    # historical and gets crowded.

fig, axes = plt.subplots(nrows=4, ncols=2, figsize=(13, 14), sharex=True)
ax = axes.flatten()


def _draw_emissions_panel(
    ax, ylabel: str, fn,
    *, divisor: float = 1.0,
) -> None:
    """Draw the input-emissions traces, one line per pathway + historical."""
    for pathway in pathways:
        s = fn(pathway)
        if s.empty:
            continue
        years = [y for y in s.index if y <= PLOT_END]
        vals = (s.loc[years] / divisor).values
        ax.plot(
            years, vals,
            color=GMD_PATHWAY_COLORS[pathway], lw=1.5, label=pathway,
        )
    # Historical (any pathway works -- pre-2024 emissions are shared);
    # draw in black on top.
    pioneer = pathways[0]
    s = fn(pioneer)
    if not s.empty:
        years = [y for y in s.index if y <= HIST_END]
        ax.plot(
            years, (s.loc[years] / divisor).values,
            color="k", lw=1.2,
        )
    ax.set_ylabel(ylabel)
    ax.axhline(0, ls=":", color="k", lw=0.5)
    ax.grid(True, alpha=0.3)


# (0) annual CO2 = FFI + AFOLU
def _co2_total(pathway: str) -> pd.Series:
    ffi = _emissions_series(emissions, pathway, "CO2 FFI")
    afolu = _emissions_series(emissions, pathway, "CO2 AFOLU")
    if ffi.empty and afolu.empty:
        return pd.Series(dtype=float)
    return ffi.add(afolu, fill_value=0.0)


_draw_emissions_panel(
    ax[0], r"CO$_2$ emissions, GtCO$_2$ yr$^{-1}$",
    _co2_total, divisor=1000.0,
)
ax[0].set_title("(a) annual CO$_2$", loc="left", fontsize=10)
ax[0].legend(ncols=4, fontsize=8, frameon=False, loc="upper center")

# (1) cumulative CO2
def _co2_cumulative(pathway: str) -> pd.Series:
    s = _co2_total(pathway)
    if s.empty:
        return s
    return pd.Series(np.cumsum(s.values), index=s.index)


_draw_emissions_panel(
    ax[1], r"Cumulative CO$_2$, GtCO$_2$",
    _co2_cumulative, divisor=1000.0,
)
ax[1].set_title("(b) cumulative CO$_2$", loc="left", fontsize=10)

# (2) CH4
_draw_emissions_panel(
    ax[2], r"CH$_4$ emissions, MtCH$_4$ yr$^{-1}$",
    lambda p: _emissions_series(emissions, p, "CH4"),
)
ax[2].set_title("(c) CH$_4$", loc="left", fontsize=10)

# (3) SO2 (Sulfur in FaIR vocabulary)
_draw_emissions_panel(
    ax[3], r"SO$_2$ emissions, MtS yr$^{-1}$",
    lambda p: _emissions_series(emissions, p, "Sulfur"),
)
ax[3].set_title("(d) SO$_2$ (Sulfur)", loc="left", fontsize=10)

# (4) GHG CO2-eq (deterministic from input emissions + GWP)
_draw_emissions_panel(
    ax[4], r"GHG emissions, GtCO$_2$eq yr$^{-1}$",
    lambda p: _co2e_series(emissions, p), divisor=1000.0,
)
ax[4].set_title("(e) GHG (CO$_2$-eq, AR6 GWP100)", loc="left", fontsize=10)


def _draw_scm_panel(
    ax, ylabel: str, variable_long: str,
    *, anomaly_baseline: tuple[int, int] | None = None,
    ymax: float | None = None,
) -> None:
    """SCM panel: 5-95 band for fair, median lines for all three.

    Drawing order matters: paint all FaIR bands first (so they sit at
    the bottom), then all median lines on top. Otherwise a later
    pathway's band overlays the earlier pathway's dotted/dashed
    medians and the SCM-line distinction visually collapses.
    """
    # Cache per-(scm, pathway) quantiles so we don't read each NC twice.
    cache: dict[tuple[str, str], pd.DataFrame | None] = {}
    for pathway in pathways:
        for scm in models:
            q = _load_scm_quantiles(scm, pathway, variable_long)
            if q is None:
                cache[(scm, pathway)] = None
                continue
            years = [y for y in q.index if y <= PLOT_END]
            if not years:
                cache[(scm, pathway)] = None
                continue
            qs = q.loc[years]
            if anomaly_baseline is not None:
                ref_years = [
                    y for y in q.index
                    if anomaly_baseline[0] <= y <= anomaly_baseline[1]
                ]
                if ref_years:
                    ref = q.loc[ref_years, 0.5].mean()
                    qs = qs - ref
            cache[(scm, pathway)] = qs

    # Bands first (FaIR only).
    for pathway in pathways:
        qs = cache.get(("fair", pathway))
        if qs is None:
            continue
        col = GMD_PATHWAY_COLORS[pathway]
        ax.fill_between(
            qs.index, qs[0.05].values, qs[0.95].values,
            color=col, alpha=0.22, lw=0,
        )
    # Medians second, all SCMs. Bottom-to-top draw order:
    # fair (solid, in band), then ciceroscm (long dashes),
    # then magicc (dash-dot, thickest -- it stops at 2100 so needs to
    # punch through the early years where all three SCMs co-locate).
    scm_visual = {
        "fair":      {"lw": 1.6, "alpha": 0.95},
        "ciceroscm": {"lw": 1.3, "alpha": 0.95},
        "magicc":    {"lw": 1.7, "alpha": 1.0},
    }
    for scm in models:
        for pathway in pathways:
            qs = cache.get((scm, pathway))
            if qs is None:
                continue
            col = GMD_PATHWAY_COLORS[pathway]
            kwargs = scm_visual.get(scm, {"lw": 1.3, "alpha": 0.95})
            ax.plot(
                qs.index, qs[0.5].values,
                color=col, linestyle=SCM_LINESTYLES[scm],
                **kwargs,
            )
            # MAGICC ends at 2100. Mark its endpoint with a filled
            # circle so the reader can see where it stopped before
            # FaIR + CICERO extend into the long tail.
            if scm == "magicc":
                end_year = int(qs.index.max())
                ax.plot(
                    [end_year], [qs.loc[end_year, 0.5]],
                    marker="o", markersize=4, color=col,
                    markeredgecolor="white", markeredgewidth=0.6,
                    linestyle="none",
                )
    ax.set_ylabel(ylabel)
    ax.axhline(0, ls=":", color="k", lw=0.5)
    ax.grid(True, alpha=0.3)
    if ymax is not None:
        ax.set_ylim(top=ymax)


# (5) ERF
_draw_scm_panel(
    ax[5], r"Effective radiative forcing, W m$^{-2}$",
    SCM_VARIABLES["forcing"],
)
ax[5].set_title("(f) total ERF (5-95% across members)", loc="left", fontsize=10)

# (6) Atmospheric CO2 concentration
_draw_scm_panel(
    ax[6], r"Atmospheric CO$_2$, ppm",
    SCM_VARIABLES["co2_conc"],
)
ax[6].set_title("(g) atmospheric CO$_2$", loc="left", fontsize=10)

# (7) Temperature anomaly relative to 1850-1900
_draw_scm_panel(
    ax[7], r"Temperature above 1850-1900, K",
    SCM_VARIABLES["temperature"],
    anomaly_baseline=(1850, 1900),
)
ax[7].set_title("(h) surface air temperature anomaly", loc="left", fontsize=10)


# SCM legend on the last panel (line-style key).
SCM_LABELS = {
    "fair":      "FaIR (median + 5-95% band)",
    "ciceroscm": "CICERO-SCM (median)",
    "magicc":    "MAGICC (median; ends at 2100)",
}
scm_handles = [
    plt.Line2D(
        [], [], color="k", lw=1.6 if scm == "fair" else 1.3,
        linestyle=SCM_LINESTYLES[scm], label=SCM_LABELS.get(scm, scm),
        marker="o" if scm == "magicc" else None, markersize=4,
        markeredgecolor="white",
    )
    for scm in models
]
ax[7].legend(
    handles=scm_handles, ncols=1,
    loc="upper left", fontsize=8, frameon=False,
)

for a in ax:
    a.set_xlim(PLOT_START, PLOT_END)

fig.suptitle(cfg.get("title", FIGURE_ID), fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.98))


# %% [markdown]
# ## Save

# %%
written = figures.save(fig, FIGURE_ID, cfg, style)
for p in written:
    print(f"wrote {p.relative_to(repo_root())}")

sys.exit(0)
