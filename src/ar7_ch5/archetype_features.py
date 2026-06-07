"""Emissions-feature extraction for archetype clustering.

Computes six clustering features and three partition-axis fields per
pathway from IAMC-style harmonised emissions trajectories (analogue of
scenariocompass notebook 03_metrics).

Output columns
--------------
Clustering features (six, standardised before k-means):
  cum_co2_eip       Trapezoidal integral of EIP CO2, 2020-2100. Gt CO2.
  cdr_fraction      cum_removals / cum_gross_fossil. [0, 1].
  ch4_reduction     CH4(2050) / CH4(2020).
  so2_2050_rel      Sulfur(2050) / Sulfur(2020).
  eip_2050_rel      EIP(2050) / EIP(2020).
  eip_2100_rel      EIP(2100) / EIP(2020).

Partition-axis fields (not standardised):
  cum_co2_afolu     Trapezoidal integral of AFOLU CO2, 2020-2100. Gt CO2.
  cum_co2_net_to_nz Cumulative net CO2 from 2020 to net-zero year (or 2100). Gt CO2.
  drawdown_band     'pos' / 'nz' / 'over'  (post-NZ drawdown categorical).

Identity columns:
  Model, Scenario, source  ('sci' or 'smip')

SCI variable names (5-year grid, 2010-2100):
  'Climate Assessment|Harmonized|Emissions|CO2|Energy and Industrial Processes'
  'Climate Assessment|Harmonized|Emissions|CO2|AFOLU'
  'Carbon Capture|Geological Storage'   (positive Mt CO2/yr stored)
  'Climate Assessment|Harmonized|Emissions|CH4'
  'Climate Assessment|Harmonized|Emissions|Sulfur'

ScenarioMIP variable names (annual half-year offset, e.g. 2020.5):
  'CO2 FFI'    (Fossil and Industrial, same concept as EIP CO2)
  'CO2 AFOLU'
  (no CCS variable → cdr_fraction = 0 for all ScenarioMIP pathways)
  'CH4'
  'Sulfur'

CO2 inputs are Mt CO2/yr; cumulative integrals are converted to Gt CO2
(÷ 1000) to match the CC-bin thresholds in schemes/clustered.json.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .load import load_sci_data_sheet

# ---------------------------------------------------------------------------
# SCI source variable names
# ---------------------------------------------------------------------------
_SCI_EIP = "Climate Assessment|Harmonized|Emissions|CO2|Energy and Industrial Processes"
_SCI_AFOLU = "Climate Assessment|Harmonized|Emissions|CO2|AFOLU"
_SCI_CCS = "Carbon Capture|Geological Storage"
_SCI_CH4 = "Climate Assessment|Harmonized|Emissions|CH4"
_SCI_SULFUR = "Climate Assessment|Harmonized|Emissions|Sulfur"

_SCI_REQUIRED = [_SCI_EIP, _SCI_AFOLU, _SCI_CH4, _SCI_SULFUR]
_SCI_ALL = [_SCI_EIP, _SCI_AFOLU, _SCI_CCS, _SCI_CH4, _SCI_SULFUR]

# ---------------------------------------------------------------------------
# ScenarioMIP source variable names (FaIR convention in the CSV)
# ---------------------------------------------------------------------------
_SMIP_EIP = "CO2 FFI"
_SMIP_AFOLU = "CO2 AFOLU"
_SMIP_CH4 = "CH4"
_SMIP_SULFUR = "Sulfur"

# ---------------------------------------------------------------------------
# SSP2-COM source variable names (canonical IAMC, see ar7_ch5.load_ssp2com)
# ---------------------------------------------------------------------------
_SSP2COM_EIP = "Emissions|CO2|MAGICC Fossil and Industrial"
_SSP2COM_AFOLU = "Emissions|CO2|MAGICC AFOLU"
_SSP2COM_CH4 = "Emissions|CH4"
_SSP2COM_SULFUR = "Emissions|Sulfur"

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

_DRAWDOWN_THRESHOLD = 200.0  # Gt CO2


def _find_netzero_year(
    net_vals: np.ndarray, years: np.ndarray
) -> float:
    """First year net CO2 crosses from positive to non-positive (linear interp).

    Returns NaN if no crossing is found.
    """
    for i in range(len(net_vals) - 1):
        if net_vals[i] > 0 and net_vals[i + 1] <= 0:
            frac = net_vals[i] / (net_vals[i] - net_vals[i + 1])
            return float(years[i] + frac * (years[i + 1] - years[i]))
    return float("nan")


def _integral_range(
    vals: np.ndarray, years: np.ndarray, y_start: float, y_end: float
) -> float:
    """Trapezoidal integral from y_start to y_end using linear interpolation.

    ``vals`` and ``years`` may be on any grid (5-yr, annual, etc.); values
    outside the supplied range are linearly extrapolated from the nearest pair.
    Returns the integral in (units of vals) × years.
    """
    # Build a fine grid limited to [y_start, y_end], adding endpoints via interp
    endpoints = np.array([y_start, y_end])
    # Keep original grid points that fall strictly inside the range
    interior = years[(years > y_start) & (years < y_end)]
    grid = np.concatenate([endpoints[:1], np.sort(interior), endpoints[1:]])
    grid = np.unique(grid)
    interp_vals = np.interp(grid, years, vals)
    return float(np.trapezoid(interp_vals, grid))


def _compute_pathway_features(
    eip: np.ndarray,
    afolu: np.ndarray,
    ccs: np.ndarray | None,
    ch4: np.ndarray,
    sulfur: np.ndarray,
    years: np.ndarray,
) -> dict:
    """Compute all nine feature fields for one pathway.

    All input arrays are aligned to ``years``. CO2 arrays are in Mt CO2/yr;
    outputs are in Gt CO2 where noted.
    """
    # --- Cumulative EIP CO2, 2020-2100, Gt CO2 ---
    cum_co2_eip = _integral_range(eip, years, 2020, 2100) / 1000.0

    # --- Cumulative removals (CCS), 2020-2100, Gt CO2 ---
    if ccs is not None:
        cum_removals = _integral_range(ccs, years, 2020, 2100) / 1000.0
    else:
        cum_removals = 0.0
    cum_gross_fossil = cum_co2_eip + cum_removals
    cdr_fraction = (
        cum_removals / cum_gross_fossil if cum_gross_fossil > 0 else 0.0
    )

    # --- Cumulative AFOLU CO2, 2020-2100, Gt CO2 ---
    cum_co2_afolu = _integral_range(afolu, years, 2020, 2100) / 1000.0

    # --- Net CO2 = EIP + AFOLU (annual resolution for NZ detection) ---
    y_ann = np.arange(int(years.min()), int(years.max()) + 1)
    eip_ann = np.interp(y_ann, years, eip)
    afolu_ann = np.interp(y_ann, years, afolu)
    net_ann = eip_ann + afolu_ann

    # Restrict NZ detection to 2020-2100
    mask_ann = (y_ann >= 2020) & (y_ann <= 2100)
    y_slice = y_ann[mask_ann]
    net_slice = net_ann[mask_ann]

    nz_year = _find_netzero_year(net_slice, y_slice)

    # --- Cumulative net CO2 from 2020 to NZ (or 2100) ---
    end_year = nz_year if not np.isnan(nz_year) else 2100.0
    cum_co2_net_to_nz = (
        _integral_range(
            net_ann, y_ann.astype(float), 2020.0, float(end_year)
        )
        / 1000.0
    )

    # --- Drawdown band ---
    if np.isnan(nz_year):
        drawdown_band = "pos"
    else:
        post_nz_cum = (
            _integral_range(
                net_ann, y_ann.astype(float), float(nz_year), 2100.0
            )
            / 1000.0
        )
        # drawdown = magnitude of net removal after NZ; net_ann < 0 past NZ
        drawdown = -post_nz_cum
        drawdown_band = "over" if drawdown > _DRAWDOWN_THRESHOLD else "nz"

    # --- Ratio features (interp to exact years) ---
    def _ratio(arr: np.ndarray, num_year: float, denom_year: float) -> float:
        num = float(np.interp(num_year, years, arr))
        denom = float(np.interp(denom_year, years, arr))
        if denom == 0 or np.isnan(denom):
            return float("nan")
        return num / denom

    ch4_reduction = _ratio(ch4, 2050, 2020)
    so2_2050_rel = _ratio(sulfur, 2050, 2020)
    eip_2050_rel = _ratio(eip, 2050, 2020)
    eip_2100_rel = _ratio(eip, 2100, 2020)

    return {
        "cum_co2_eip": cum_co2_eip,
        "cdr_fraction": cdr_fraction,
        "ch4_reduction": ch4_reduction,
        "so2_2050_rel": so2_2050_rel,
        "eip_2050_rel": eip_2050_rel,
        "eip_2100_rel": eip_2100_rel,
        "cum_co2_afolu": cum_co2_afolu,
        "cum_co2_net_to_nz": cum_co2_net_to_nz,
        "drawdown_band": drawdown_band,
    }


# ---------------------------------------------------------------------------
# SCI feature extraction
# ---------------------------------------------------------------------------

def compute_features_sci(df: pd.DataFrame) -> pd.DataFrame:
    """Compute archetype features from a SCI IAMC wide-format DataFrame.

    ``df`` is expected to have uppercase IAMC columns (``Model``,
    ``Scenario``, ``Region``, ``Variable``, ``Unit``) plus integer year
    columns (``2010``, ``2015``, ..., ``2100``).  This is the format
    returned by :func:`ar7_ch5.load.load_sci_data_sheet`.

    Only rows with ``Region == 'World'`` are used.  Pathways that are
    missing all four required variables are silently dropped.

    Returns a DataFrame with one row per (Model, Scenario) and columns
    described in the module docstring.
    """
    df = df[df["Region"] == "World"].copy()
    year_cols = sorted(
        [c for c in df.columns if isinstance(c, int) and 2010 <= c <= 2100],
        key=int,
    )
    years = np.array(year_cols, dtype=float)

    records = []
    for (model, scenario), grp in df.groupby(["Model", "Scenario"], sort=True):
        var_map: dict[str, np.ndarray] = {}
        for _, row in grp.iterrows():
            var = row["Variable"]
            if var in _SCI_ALL:
                var_map[var] = row[year_cols].values.astype(float)

        if not all(v in var_map for v in _SCI_REQUIRED):
            continue  # skip pathways missing mandatory variables

        ccs = var_map.get(_SCI_CCS, None)

        feat = _compute_pathway_features(
            eip=var_map[_SCI_EIP],
            afolu=var_map[_SCI_AFOLU],
            ccs=ccs,
            ch4=var_map[_SCI_CH4],
            sulfur=var_map[_SCI_SULFUR],
            years=years,
        )
        feat["Model"] = model
        feat["Scenario"] = scenario
        feat["source"] = "sci"
        records.append(feat)

    return _make_output_df(records)


# ---------------------------------------------------------------------------
# ScenarioMIP feature extraction
# ---------------------------------------------------------------------------

def compute_features_smip(df: pd.DataFrame) -> pd.DataFrame:
    """Compute archetype features from a ScenarioMIP IAMC wide-format DataFrame.

    ``df`` is expected to have lowercase IAMC columns (``model``,
    ``scenario``, ``region``, ``variable``) plus float half-year-offset
    year columns (``1750.5``, ..., ``2100.5``), as produced by
    ``pd.read_csv`` of ``emissions_1750-2500.csv``.

    No CCS variable is present in the ScenarioMIP file;
    ``cdr_fraction`` is set to 0 for all pathways.

    Returns a DataFrame with one row per scenario and the same columns
    as :func:`compute_features_sci`.
    """
    if "region" in df.columns:
        df = df[df["region"] == "World"].copy()

    # Extract year columns: float half-year offsets → round to int for labels
    raw_years = []
    int_years = []
    for c in df.columns:
        try:
            y = float(c)
        except (TypeError, ValueError):
            continue
        if 2010.0 <= y <= 2101.0:
            raw_years.append(c)
            int_years.append(round(y))

    years = np.array(int_years, dtype=float)

    records = []
    scenario_col = "scenario" if "scenario" in df.columns else "Scenario"
    var_col = "variable" if "variable" in df.columns else "Variable"

    for scenario, grp in df.groupby(scenario_col, sort=True):
        var_map: dict[str, np.ndarray] = {}
        for _, row in grp.iterrows():
            var = row[var_col]
            if var in (_SMIP_EIP, _SMIP_AFOLU, _SMIP_CH4, _SMIP_SULFUR):
                var_map[var] = row[raw_years].values.astype(float)

        if not all(v in var_map for v in (_SMIP_EIP, _SMIP_AFOLU, _SMIP_CH4, _SMIP_SULFUR)):
            continue

        feat = _compute_pathway_features(
            eip=var_map[_SMIP_EIP],
            afolu=var_map[_SMIP_AFOLU],
            ccs=None,  # no CCS in ScenarioMIP file
            ch4=var_map[_SMIP_CH4],
            sulfur=var_map[_SMIP_SULFUR],
            years=years,
        )
        feat["Model"] = "scenariomip"
        feat["Scenario"] = scenario
        feat["source"] = "smip"
        records.append(feat)

    return _make_output_df(records)


# ---------------------------------------------------------------------------
# SSP2-COM feature extraction
# ---------------------------------------------------------------------------

def compute_features_ssp2com(df: pd.DataFrame) -> pd.DataFrame:
    """Compute archetype features for the SSP2-COM world-total pathway.

    ``df`` is the long-format timeseries returned by
    ``load_ssp2com_world_total(...).timeseries().reset_index()``: it has a
    ``variable`` column of canonical IAMC names plus one column per
    annual ``datetime`` timestamp (2023-2100).

    No CCS variable is present, so ``cdr_fraction`` is set to 0 (as for
    ScenarioMIP).  Returns a single-row DataFrame with the same columns as
    :func:`compute_features_sci`, tagged ``source='ssp2com'``.
    """
    time_cols = [c for c in df.columns if hasattr(c, "year")]
    years = np.array([c.year for c in time_cols], dtype=float)

    var_map: dict[str, np.ndarray] = {}
    for _, row in df.iterrows():
        var = row["variable"]
        if var in (_SSP2COM_EIP, _SSP2COM_AFOLU, _SSP2COM_CH4, _SSP2COM_SULFUR):
            var_map[var] = row[time_cols].values.astype(float)

    required = (_SSP2COM_EIP, _SSP2COM_AFOLU, _SSP2COM_CH4, _SSP2COM_SULFUR)
    if not all(v in var_map for v in required):
        return _make_output_df([])

    feat = _compute_pathway_features(
        eip=var_map[_SSP2COM_EIP],
        afolu=var_map[_SSP2COM_AFOLU],
        ccs=None,  # no CCS in the SSP2-COM world-total file
        ch4=var_map[_SSP2COM_CH4],
        sulfur=var_map[_SSP2COM_SULFUR],
        years=years,
    )
    feat["Model"] = "ssp2com"
    feat["Scenario"] = "SSP2-com"
    feat["source"] = "ssp2com"
    return _make_output_df([feat])


# ---------------------------------------------------------------------------
# High-level loaders
# ---------------------------------------------------------------------------

def load_and_compute_sci(
    xlsx_path: str | Path,
    *,
    vetted_only: bool = False,
    classification_csv: str | Path | None = None,
) -> pd.DataFrame:
    """Load SCI xlsx and compute archetype features.

    Parameters
    ----------
    xlsx_path
        Path to ``SCI-2025_v1.0_pathways_ensemble_global.xlsx``.
    vetted_only
        If True, restrict to pathways that passed vetting.  Requires
        ``classification_csv``.
    classification_csv
        Path to ``outputs/classification_xlsx.csv`` (or similar);
        used when ``vetted_only=True``.
    """
    df = load_sci_data_sheet(xlsx_path)
    features = compute_features_sci(df)
    if vetted_only:
        if classification_csv is None:
            raise ValueError("vetted_only=True requires classification_csv.")
        vetted_df = pd.read_csv(Path(classification_csv))
        passed = vetted_df.loc[vetted_df["vetting_status"] == "passed", ["Model", "Scenario"]]
        passed = passed.rename(columns={"Model": "Model", "Scenario": "Scenario"})
        features = features.merge(
            passed.assign(_keep=True), on=["Model", "Scenario"], how="inner"
        ).drop(columns=["_keep"])
    return features


def load_and_compute_smip(smip_csv_path: str | Path) -> pd.DataFrame:
    """Load ScenarioMIP emissions CSV and compute archetype features."""
    df = pd.read_csv(Path(smip_csv_path))
    return compute_features_smip(df)


def load_and_compute_ssp2com(ssp2com_xlsx_path: str | Path) -> pd.DataFrame:
    """Load the SSP2-COM world-total xlsx and compute archetype features."""
    from .load_ssp2com import load_ssp2com_world_total

    run = load_ssp2com_world_total(Path(ssp2com_xlsx_path))
    df = run.timeseries().reset_index()
    return compute_features_ssp2com(df)


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------

_OUTPUT_COLUMNS = [
    "Model",
    "Scenario",
    "source",
    "cum_co2_eip",
    "cdr_fraction",
    "ch4_reduction",
    "so2_2050_rel",
    "eip_2050_rel",
    "eip_2100_rel",
    "cum_co2_afolu",
    "cum_co2_net_to_nz",
    "drawdown_band",
]


def _make_output_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)
    out = pd.DataFrame(records)
    # Ensure column order
    present = [c for c in _OUTPUT_COLUMNS if c in out.columns]
    return out[present].reset_index(drop=True)
