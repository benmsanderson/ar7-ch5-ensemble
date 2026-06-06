"""Warming metrics derived from the SCM ensemble outputs.

Bridges the per-(pathway, model) NetCDFs the SCI batch writes into the
peak/end-of-century warming percentiles that the classification consumes.
Built on top of :mod:`gcages.ar6.post_processing` (Nicholls, AR6 successor to
climate-assessment), which supplies the AR6 historical anchoring and the
quantile/peak/exceedance machinery; the multi-SCM combination axis is the
piece this module adds.

Combination modes (the open Ch5 science decision lives in the ``source``
parameter; see ``project_classification_warming_contract``):

- ``"per_model"`` (B1): percentiles within each climate_model, AR6-style.
  Per-model anchoring; per-model quantiles. Most directly comparable to AR6.
- ``"pooled"`` (B2): per-model anchoring (each SCM still calibrated to its
  own assessment-period match), then quantiles taken across the union of
  members across all climate_models. Widens the spread relative to B1.

Inputs are the NetCDFs written by :func:`ar7_ch5.experiments.sci_ensemble.run_sci_batch`
under ``<outputs_dir>/<scm>/sci_<iam>_<pathway_id>.nc``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import pandas as pd
import scmdata
from gcages.ar6.post_processing import get_temperatures_in_line_with_assessment
from pandas_openscm.grouping import (
    fix_index_name_after_groupby_quantile,
    groupby_except,
)

GSAT_VARIABLE = "Surface Air Temperature Change"

# AR6 GSAT assessment anchoring (climate-assessment defaults).
AR6_ASSESSMENT_MEDIAN = 0.85  # K
AR6_ASSESSMENT_PERIOD = tuple(range(1995, 2015))  # 1995-2014 inclusive
AR6_PRE_INDUSTRIAL_PERIOD = tuple(range(1850, 1901))  # 1850-1900 inclusive

# Quantiles needed by the GW0-GW8 classification (Riahi 2026 Table SI.3).
# Median for peak / end-of-century, 67th for "likely below 2C" (GW3).
CLASSIFICATION_QUANTILES: tuple[float, ...] = (0.5, 0.67)

# Anchoring is always per-model so each SCM is calibrated to its own
# assessment-period match before any cross-model pooling happens.
_ANCHOR_GROUP_COLS = ["climate_model", "model", "pathway_id"]

Source = Literal["per_model", "pooled"]


def pathway_nc_name(iam: str, pathway_id: str) -> str:
    """Match the filename convention written by run_sci_batch.

    Keys on the chapter ``pathway_id`` (e.g. ``SSP1-19``) rather than the
    canonical RCMIP3 ``scenario`` (e.g. ``ssp119``), because multiple
    pathways can share a canonical and would clobber a scenario-keyed
    filename. See ``docs/engine_upstream_switch.md``.
    """
    stem = f"sci_{iam}_{pathway_id}".replace("/", "-").replace(" ", "-")
    return f"{stem}.nc"


def load_pathway_outputs(
    pathways: Iterable[tuple[str, str]],
    models: Sequence[str],
    outputs_dir: str | Path,
    *,
    variable: str = GSAT_VARIABLE,
    region: str = "World",
) -> pd.DataFrame:
    """Load per-pathway, per-model SCM outputs into one DataFrame.

    Parameters
    ----------
    pathways
        Iterable of ``(iam, pathway_id)`` pairs to load (chapter
        identifiers, e.g. ``("AIM/CGE 2.0", "SSP1-19")``).
    models
        SCM subdirectory names under ``outputs_dir``
        (``"fair", "ciceroscm", "magicc"``).
    outputs_dir
        Root of the per-model NetCDF tree (``<outputs_dir>/<scm>/<file>.nc``).
    variable
        Variable to keep. Default GSAT.
    region
        Region to keep. Default ``"World"``.

    Returns
    -------
    pandas DataFrame in the pandas-openscm MultiIndex convention: index levels
    ``(variable, unit, region, model, pathway_id, climate_model, run_id)``;
    columns are integer years. Raises ``FileNotFoundError`` if no NetCDF is
    found for any of the requested pathways.
    """
    out_dir = Path(outputs_dir)
    pieces: list[pd.DataFrame] = []
    missing: list[tuple[str, str, str]] = []
    for iam, pathway_id in pathways:
        for scm in models:
            path = out_dir / scm / pathway_nc_name(iam, pathway_id)
            if not path.is_file():
                missing.append((scm, iam, pathway_id))
                continue
            run = scmdata.ScmRun.from_nc(path)
            run = run.filter(variable=variable, region=region)
            if len(run) == 0:
                continue
            ts = run.timeseries()
            ts.columns = pd.Index([t.year for t in ts.columns], name="year")
            # Adapters disagree on what the IAMC ``model`` and ``pathway_id``
            # meta carry through (FaIR drops them, CICERO mirrors scenario
            # into both, MAGICC preserves them). Overwrite from the input
            # pair so all SCMs share the same (model, pathway_id) group key.
            ts = _set_index_level(ts, "model", iam)
            ts = _set_index_level(ts, "pathway_id", pathway_id)
            pieces.append(ts)

    if not pieces:
        raise FileNotFoundError(
            f"No SCM output NetCDFs found under {out_dir} for {list(pathways)}."
        )
    if missing:
        # Don't crash if a single SCM is missing for some pathways: the
        # combination just runs over fewer members. But warn so the user
        # knows the ensemble has shrunk for those pathways.
        print(
            f"NOTE: skipped {len(missing)} missing per-(scm, pathway) NetCDFs "
            f"under {out_dir} (first 3: {missing[:3]})."
        )
    return pd.concat(pieces)


def _set_index_level(df: pd.DataFrame, level: str, value: str) -> pd.DataFrame:
    """Set a MultiIndex level to a constant value, adding the level if absent.

    The adapters disagree on which meta columns they carry through (and
    older SCI NetCDFs from before the pathway_id refactor don't have it at
    all). Treat the input pair from :func:`load_pathway_outputs` as the
    source of truth: if the level exists, overwrite it; if it doesn't,
    append it.
    """
    df = df.copy()
    if level in df.index.names:
        levels = [
            [value] * df.shape[0] if name == level
            else df.index.get_level_values(name)
            for name in df.index.names
        ]
        df.index = pd.MultiIndex.from_arrays(levels, names=df.index.names)
    else:
        new_names = [*df.index.names, level]
        new_arrays = [
            df.index.get_level_values(n) for n in df.index.names
        ] + [[value] * df.shape[0]]
        df.index = pd.MultiIndex.from_arrays(new_arrays, names=new_names)
    return df


def anchor_to_assessment(
    raw_temperatures: pd.DataFrame,
    *,
    assessment_median: float = AR6_ASSESSMENT_MEDIAN,
    assessment_period: Sequence[int] = AR6_ASSESSMENT_PERIOD,
    pre_industrial_period: Sequence[int] = AR6_PRE_INDUSTRIAL_PERIOD,
    group_cols: Sequence[str] = _ANCHOR_GROUP_COLS,
) -> pd.DataFrame:
    """Adjust raw GSAT timeseries to match the AR6 historical assessment.

    Subtract each run's pre-industrial-period mean, then recentre the per-
    climate-model assessment-period median onto ``assessment_median``. Wraps
    :func:`gcages.ar6.post_processing.get_temperatures_in_line_with_assessment`
    with the AR6 defaults.
    """
    return get_temperatures_in_line_with_assessment(
        raw_temperatures,
        assessment_median=assessment_median,
        assessment_time_period=tuple(assessment_period),
        assessment_pre_industrial_period=tuple(pre_industrial_period),
        group_cols=list(group_cols),
    )


def _quantile_levels(source: Source) -> tuple[str, list[str]]:
    """Return ``(groupby_except_levels, group_index_levels)`` for ``source``."""
    if source == "per_model":
        return "run_id", ["model", "pathway_id", "climate_model"]
    if source == "pooled":
        return ["run_id", "climate_model"], ["model", "pathway_id"]
    raise ValueError(
        f"unknown source={source!r}; expected 'per_model' or 'pooled'"
    )


def compute_warming_metrics(
    anchored_temperatures: pd.DataFrame,
    *,
    source: Source = "per_model",
    quantiles: Sequence[float] = CLASSIFICATION_QUANTILES,
) -> pd.DataFrame:
    """Peak and end-of-century warming at the requested quantiles.

    Parameters
    ----------
    anchored_temperatures
        Output of :func:`anchor_to_assessment`.
    source
        Multi-SCM combination axis. See module docstring.
    quantiles
        Quantiles to evaluate. Must include 0.5 and 0.67 for the GW0-GW8
        classification.

    Returns
    -------
    DataFrame with one row per pathway group (``(model, pathway_id,
    climate_model)`` for ``per_model``; ``(model, pathway_id)`` for
    ``pooled``) and columns
    ``peak_warming_<qq>`` and ``eoc_warming_<qq>`` for each quantile (e.g.
    ``peak_warming_50``, ``peak_warming_67``), plus ``declining`` (median
    2100 < median 2090; None if either is missing).
    """
    quantiles = tuple(quantiles)
    if 0.5 not in quantiles or 0.67 not in quantiles:
        raise ValueError(
            "quantiles must include 0.5 and 0.67 for GW0-GW8 classification; "
            f"got {quantiles}."
        )

    groupby_except_levels, index_levels = _quantile_levels(source)

    peak = anchored_temperatures.max(axis="columns")
    eoc = anchored_temperatures[2100]

    peak_q = fix_index_name_after_groupby_quantile(
        groupby_except(peak, groupby_except_levels).quantile(list(quantiles)),
        new_name="quantile",
    )
    eoc_q = fix_index_name_after_groupby_quantile(
        groupby_except(eoc, groupby_except_levels).quantile(list(quantiles)),
        new_name="quantile",
    )

    # Per-year median timeseries; used to assess whether warming is still
    # declining at end-of-century (median 2100 < median 2090).
    median_ts = groupby_except(
        anchored_temperatures, groupby_except_levels,
    ).quantile(0.5)

    peak_wide = _quantile_to_wide(peak_q, "peak_warming", index_levels)
    eoc_wide = _quantile_to_wide(eoc_q, "eoc_warming", index_levels)
    declining = _declining_from_median_ts(median_ts, index_levels)

    metrics = peak_wide.join(eoc_wide).join(declining)
    return metrics


def _quantile_to_wide(
    quantile_series: pd.Series,
    prefix: str,
    index_levels: Sequence[str],
) -> pd.DataFrame:
    """Pivot a (..., quantile) Series into wide columns ``<prefix>_<qq>``."""
    series = quantile_series.copy()
    keep = [*index_levels, "quantile"]
    series = series.reset_index(
        [lvl for lvl in series.index.names if lvl not in keep],
        drop=True,
    )
    wide = series.unstack("quantile")
    wide.columns = [f"{prefix}_{int(round(q * 100))}" for q in wide.columns]
    return wide


def _declining_from_median_ts(
    median_ts: pd.DataFrame,
    index_levels: Sequence[str],
) -> pd.Series:
    """Boolean Series ``declining`` aligned to ``index_levels``."""
    median_ts = median_ts.reset_index(
        [lvl for lvl in median_ts.index.names if lvl not in index_levels],
        drop=True,
    )
    if 2090 not in median_ts.columns or 2100 not in median_ts.columns:
        return pd.Series(
            [None] * len(median_ts),
            index=median_ts.index, name="declining",
        )
    declining = median_ts[2100] < median_ts[2090]
    declining.name = "declining"
    return declining


def warming_metrics_from_outputs(
    pathways: Iterable[tuple[str, str]],
    models: Sequence[str],
    outputs_dir: str | Path,
    *,
    source: Source = "per_model",
    quantiles: Sequence[float] = CLASSIFICATION_QUANTILES,
    assessment_median: float = AR6_ASSESSMENT_MEDIAN,
    assessment_period: Sequence[int] = AR6_ASSESSMENT_PERIOD,
    pre_industrial_period: Sequence[int] = AR6_PRE_INDUSTRIAL_PERIOD,
    region: str = "World",
) -> pd.DataFrame:
    """End-to-end: load NetCDFs, anchor to assessment, return metrics frame.

    Thin convenience over :func:`load_pathway_outputs`,
    :func:`anchor_to_assessment`, and :func:`compute_warming_metrics`.
    """
    raw = load_pathway_outputs(pathways, models, outputs_dir, region=region)
    anchored = anchor_to_assessment(
        raw,
        assessment_median=assessment_median,
        assessment_period=assessment_period,
        pre_industrial_period=pre_industrial_period,
    )
    return compute_warming_metrics(anchored, source=source, quantiles=quantiles)
