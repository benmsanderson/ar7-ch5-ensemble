"""Chapter-owned harmonisation + infilling for raw IAM emissions.

A single pipeline that takes raw IAM scenario emissions (IAMC-wide format,
``CMIP7_SCENARIOMIP`` variable-naming convention) and returns SCM-ready
emissions, harmonised to the chapter history and infilled to the full
GCAGES driving set. The same pipeline serves SCI, ScenarioMIP CMIP7 and
SSP2-COM; per-ensemble specialisation lives in their raw loaders, not here.

Pipeline stages (each exposed as a small named helper, in this order):

1. :func:`drop_late_starting_scenarios` -- discard scenarios whose first
   non-null value occurs after the chapter anchor year. Pragmatic v1
   filter; full treatment of late-starting pathways is deferred.
2. :func:`interpolate_to_annual` -- linear-interpolate the native 5-yearly
   IAMC grid onto annual years; clip to the chapter window.
3. :func:`rename_iamc_to_gcages` -- convert from ``CMIP7_SCENARIOMIP`` to
   ``GCAGES`` naming, drop the aggregate parent variables, strip
   pint-incompatible characters from units.
4. :func:`clean_negatives` -- round near-zero HFC trajectories to zero
   and drop any (model, scenario) with a stray negative value on a
   non-CO2 species.
5. :func:`harmonise_aneris_global` -- delegate to ``gcages`` Aneris
   global harmoniser, anchored at ``harmonisation_year``.
6. :func:`infill_cmip7` -- delegate to ``gcages``
   :class:`CMIP7ScenarioMIPInfiller` (``RMSClosest`` internally), padding
   missing minor-GHG species against the inversion history.

The top-level :func:`harmonise_and_infill` runs all six in order. The
helpers are public so a reviewer can run them on a single scenario in
isolation. The chapter's choice of ``harmonisation_year`` is 2023; the
infiller's ``pre_industrial_year`` is 1750.

The pipeline tracks Zeb Nicholls' demo notebook (PR #26) step-for-step;
divergences from that reference are intentional and noted in the
docstrings of the helpers they appear in.
"""

from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openscm_units
import pandas as pd
import pandas_indexing as pix
import pandas_openscm  # noqa: F401  # registers the pandas accessor used downstream
import pint
from gcages.cmip7_scenariomip.harmonisation import (
    create_cmip7_scenariomip_global_harmoniser,
)
from gcages.cmip7_scenariomip.infilling import (
    CMIP7ScenarioMIPInfiller,
    assert_harmonised,
)
from gcages.renaming import (
    SupportedNamingConventions,
    rename_variables,
)
from gcages.units_helpers import strip_pint_incompatible_characters_from_units
from pandas_openscm.indexing import multi_index_match

from .cmip7_inputs import (
    DEFAULT_GHG_INVERSIONS_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_INFILLING_DB_FILE,
    DEFAULT_OVERRIDES_FILE,
    load_ghg_inversions,
    load_history_emissions,
    load_infilling_db,
)

DEFAULT_HARMONISATION_YEAR: int = 2023
DEFAULT_PRE_INDUSTRIAL_YEAR: int = 1750
DEFAULT_ANNUAL_START_YEAR: int = 2010
DEFAULT_ANNUAL_END_YEAR: int = 2100
DEFAULT_SPLICE_BLEND_YEARS: int = 5
DEFAULT_CHECK_HASH: bool = False
# Aneris is lighter than SCM forking (no MAGICC binary, no FaIR jit), so we
# can run it with more workers than the chapter-wide DEFAULT_MAX_WORKERS cap
# of 12 (which exists to bound NAC memory-overcommit during SCM runs).
DEFAULT_HARMONISATION_WORKERS: int = 36

# Variables kept after the ``CMIP7_SCENARIOMIP -> GCAGES`` rename. The
# IAMC tree has aggregate parents (``Emissions|CO2``, ``Emissions|F-Gases``,
# ``Emissions|HFC``, ...) plus the leaves the harmoniser actually needs;
# we keep the leaves and the two CO2 sectors but drop the aggregates so
# the renamed frame contains no duplicates. Mirrors Zeb's cell 7 in
# PR #26.
_VARIABLE_KEEP_PATTERNS: tuple[str, ...] = (
    "Emissions|*",
    "Emissions|HFC|**",
    # NOTE: SCI publishes ``Emissions|CO2|Energy and Industrial Processes``
    # for some scenarios and a re-aggregation for others -- flagged for a
    # per-IAM audit (see PR description, open question on EIP).
    "Emissions|CO2|Energy and Industrial Processes",
    "Emissions|CO2|AFOLU",
)
_VARIABLE_DROP_AGGREGATES: tuple[str, ...] = (
    "Emissions|F-Gases",
    "Emissions|PFC",
    "Emissions|HFC",
    "Emissions|Kyoto Gases",
    "Emissions|CO2",
)


@dataclass(frozen=True)
class HarmonisationConfig:
    """All knobs exposed to callers of :func:`harmonise_and_infill`.

    Defaults reflect the chapter's first-pass scientific choices (2023
    anchor, 1750 PI year, 2010-2100 annual window). The four file paths
    point to ``data/cmip7/`` by default; override per call for tests or
    alternative input vintages.
    """

    history_path: Path = DEFAULT_HISTORY_FILE
    overrides_path: Path = DEFAULT_OVERRIDES_FILE
    infilling_db_path: Path = DEFAULT_INFILLING_DB_FILE
    ghg_inversions_path: Path = DEFAULT_GHG_INVERSIONS_FILE

    harmonisation_year: int = DEFAULT_HARMONISATION_YEAR
    pre_industrial_year: int = DEFAULT_PRE_INDUSTRIAL_YEAR
    annual_start_year: int = DEFAULT_ANNUAL_START_YEAR
    annual_end_year: int = DEFAULT_ANNUAL_END_YEAR
    splice_blend_years: int = DEFAULT_SPLICE_BLEND_YEARS

    run_checks: bool = True
    check_hash: bool = DEFAULT_CHECK_HASH
    progress: bool = True
    n_processes: int | None = None
    # Sidecar CSV listing pathways the pipeline drops, written next to the
    # output parquet. ``None`` disables the sidecar; the in-memory drop list
    # is still attached to ``df.attrs`` from the helpers.
    drops_sidecar_path: Path | None = None


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def drop_late_starting_scenarios(
    emissions: pd.DataFrame, *, anchor_year: int = DEFAULT_HARMONISATION_YEAR
) -> pd.DataFrame:
    """Drop ``(model, scenario)`` pairs whose first non-null year exceeds anchor.

    The unrecoverable cousin of :func:`splice_late_starting_from_history`.
    Useful when history coverage is unavailable; not used in the default
    pipeline (the splice runs instead).

    Computed as the maximum-over-variables of the year-of-first-non-null
    per row, grouped by ``(model, scenario)``. A scenario survives iff every
    variable it carries has a value at or before ``anchor_year``.
    Dropped pairs land on ``df.attrs['dropped_late_starting']``.
    """
    df = emissions.sort_index(axis="columns")
    first_year = df.isnull().idxmin(axis="columns")
    too_late = (
        first_year.groupby(["model", "scenario"]).max().sort_values()
    )
    dropped = too_late[too_late > anchor_year]
    if dropped.empty:
        return df

    survivors = df.loc[
        ~multi_index_match(df.index, dropped.index)
    ].copy()
    survivors.attrs["dropped_late_starting"] = list(dropped.index)
    return survivors


def splice_late_starting_from_history(
    emissions: pd.DataFrame,
    history: pd.DataFrame,
    *,
    anchor_year: int = DEFAULT_HARMONISATION_YEAR,
    blend_years: int = DEFAULT_SPLICE_BLEND_YEARS,
) -> pd.DataFrame:
    """Backfill late-starting trajectories from chapter history.

    For each row whose first non-null year ``y0 > anchor_year``:

    * ``[anchor_year, y0 - blend_years]`` is filled with the chapter
      history values for that variable (year-by-year exact).
    * ``[y0 - blend_years, y0]`` linearly blends from the history value
      at ``y0 - blend_years`` to the scenario value at ``y0`` (so the
      scenario's first reported year is hit exactly; the blend smooths
      the kink across the chosen window).
    * ``[y0, end]`` is left untouched.

    Rows whose variable is absent from ``history`` are dropped; the dropped
    list lands on ``df.attrs['dropped_no_history']`` as
    ``[(model, scenario, variable), ...]`` so the caller can report them.

    Inputs must already be in the GCAGES naming convention (i.e. run
    :func:`rename_iamc_to_gcages` first) so the variable look-up against
    history matches.
    """
    # Work on a sorted-by-year copy so ``idxmin`` is meaningful.
    out = emissions.copy().sort_index(axis="columns")
    year_cols = [c for c in out.columns if isinstance(c, int)]
    if not year_cols:
        return out

    first_year = out[year_cols].notna().idxmax(axis="columns")
    # ``idxmax`` returns the FIRST True; rows with no True become the
    # first column (since ``notna`` is all-False). Mask those out.
    all_null = ~out[year_cols].notna().any(axis="columns")
    first_year = first_year.where(~all_null, other=pd.NA)

    late_mask = first_year > anchor_year
    if not late_mask.any():
        return out

    history_lookup = _history_by_variable(history)

    dropped_rows: list[tuple] = []
    survivors: list[pd.Series] = []
    for row_idx, is_late in late_mask.items():
        row = out.loc[row_idx]
        if not is_late:
            survivors.append(row)
            continue
        variable = _level_value(row_idx, out.index.names, "variable")
        hist = history_lookup.get(variable)
        if hist is None:
            dropped_rows.append(row_idx)
            continue
        y0 = int(first_year.loc[row_idx])
        spliced = _splice_one_row(
            row,
            history_series=hist,
            anchor_year=anchor_year,
            y0=y0,
            blend_years=blend_years,
            year_cols=year_cols,
        )
        survivors.append(spliced)

    if not survivors:
        # Every row dropped: preserve the input's column shape so callers
        # see a same-shape empty frame rather than a typeless one.
        empty = out.iloc[:0].copy()
        if dropped_rows:
            empty.attrs["dropped_no_history"] = list(dropped_rows)
        return empty

    spliced_df = pd.DataFrame(survivors)[out.columns]
    if dropped_rows:
        spliced_df.attrs["dropped_no_history"] = list(dropped_rows)
    return spliced_df


def _history_by_variable(history: pd.DataFrame) -> dict[str, pd.Series]:
    """Return ``{variable: Series(year -> value)}`` for fast row-wise lookup.

    History is GCAGES-named, indexed at least on ``variable``; multiple
    rows per variable (different units / regions) collapse to the first.
    """
    out: dict[str, pd.Series] = {}
    for var, sub in history.groupby(level="variable"):
        # Take the first row -- the global history has one row per variable
        # in the chapter's setup (region=World, single unit).
        series = sub.iloc[0]
        out[str(var)] = series
    return out


def _level_value(row_idx, names, level: str):
    """Look up a named level value from a row index tuple."""
    if isinstance(row_idx, tuple):
        return row_idx[list(names).index(level)]
    return row_idx


def _splice_one_row(
    row: pd.Series,
    *,
    history_series: pd.Series,
    anchor_year: int,
    y0: int,
    blend_years: int,
    year_cols: list[int],
) -> pd.Series:
    """Apply the backfill + blend rule to a single row."""
    out = row.copy()
    # Years where we expect history values (exact).
    blend_start = max(anchor_year, y0 - blend_years)
    for y in range(anchor_year, blend_start + 1):
        if y in history_series.index:
            out[y] = float(history_series[y])
    # Blend window: linearly interpolate from out[blend_start] to row[y0]
    # across (blend_start, y0).
    if y0 > blend_start:
        anchor_val = out[blend_start]
        target_val = row[y0]
        span = y0 - blend_start
        for y in range(blend_start + 1, y0):
            frac = (y - blend_start) / span
            out[y] = anchor_val + frac * (target_val - anchor_val)
    return out[year_cols]


def interpolate_to_annual(
    emissions: pd.DataFrame,
    *,
    start_year: int = DEFAULT_ANNUAL_START_YEAR,
    end_year: int = DEFAULT_ANNUAL_END_YEAR,
    clip_to_year: int = DEFAULT_HARMONISATION_YEAR,
    allow_leading_nan: bool = False,
) -> pd.DataFrame:
    """Linear-interpolate sparse year columns onto an annual grid.

    Adds any missing integer-year column in ``[start_year, end_year]`` as
    NaN, interpolates along the year axis with ``method="index"``, then
    slices to ``[clip_to_year, end_year]``.

    When ``allow_leading_nan`` is ``False`` (legacy default), asserts that
    the post-clip window contains no NaN -- callers must run
    :func:`drop_late_starting_scenarios` first. When ``True``, leading NaNs
    survive the slice so :func:`splice_late_starting_from_history` can
    fill them from chapter history. The default chapter pipeline uses
    ``True`` (the splice is the chapter's late-start treatment).
    """
    df = emissions.copy().sort_index(axis="columns")
    for y in range(start_year, end_year + 1):
        if y not in df.columns:
            df[y] = np.nan
    df = (
        df.T.interpolate(method="index")
        .T.sort_index(axis="columns")
        .loc[:, clip_to_year:end_year]
    )
    if not allow_leading_nan and df.isnull().any().any():
        raise AssertionError(
            "Annual interpolation left NaNs in the post-clip window; "
            "did drop_late_starting_scenarios run first?"
        )
    return df


def rename_iamc_to_gcages(emissions: pd.DataFrame) -> pd.DataFrame:
    """Convert variable names from ``CMIP7_SCENARIOMIP`` to ``GCAGES``.

    Filters to the species the harmoniser drives (drops the aggregate
    parents like ``Emissions|CO2`` to avoid duplicates after renaming),
    runs the gcages renamer, then strips pint-incompatible characters
    from the ``unit`` index level so the harmoniser's unit machinery
    works downstream.
    """
    mask = pix.ismatch(variable=list(_VARIABLE_KEEP_PATTERNS)) & ~pix.isin(
        variable=list(_VARIABLE_DROP_AGGREGATES)
    )
    selected = emissions.loc[mask]
    renamed = rename_variables(
        selected,
        from_convention=SupportedNamingConventions.CMIP7_SCENARIOMIP,
        to_convention=SupportedNamingConventions.GCAGES,
    )
    return strip_pint_incompatible_characters_from_units(
        renamed, units_index_level="unit"
    )


def clean_negatives(
    emissions: pd.DataFrame, *, hfc_zero_tolerance: int = 3
) -> pd.DataFrame:
    """Round near-zero HFC cells to zero, then drop scenarios with negatives.

    Two-stage cleanup:

    1. For HFC rows, individual cells that round to zero at
       ``hfc_zero_tolerance`` decimal places are forced to exact zero.
       This kills spurious tiny-negative HFC noise (typically
       ``~ 1e-6 kt/yr`` from IAM output rounding) without affecting the
       other years of the trajectory. Mirrors Zeb's notebook intent;
       differs in being **per-cell** rather than per-row -- the per-row
       variant zeroes a whole HFC trajectory if any single year happens
       to round to zero, which silently wipes legitimate trajectories
       that decay toward zero by 2100.
    2. Any ``(model, scenario)`` that still has a negative value on any
       non-CO2 species is dropped entirely. Pragmatic v1 filter -- a
       single bad value drops the whole pathway.

    The list of dropped pairs is attached as ``df.attrs['dropped_negative']``.
    """
    out = emissions.copy()
    hfc_mask = pix.ismatch(variable="**HFC**")
    hfc_rows = out.loc[hfc_mask]
    if not hfc_rows.empty:
        zero_cells = hfc_rows.round(hfc_zero_tolerance) == 0.0
        out.loc[hfc_mask] = hfc_rows.where(~zero_cells, 0.0)

    non_co2 = out.loc[~pix.ismatch(variable="**CO2**")]
    negative_rows = (non_co2 < 0).any(axis=1)
    dropped_pairs = (
        negative_rows[negative_rows]
        .index.droplevel(["region", "variable", "unit"])
        .drop_duplicates()
    )
    if not dropped_pairs.empty:
        out = out.loc[~multi_index_match(out.index, dropped_pairs)].copy()
        out.attrs["dropped_negative"] = list(dropped_pairs)
    return out


def harmonise_aneris_global(
    emissions: pd.DataFrame,
    *,
    config: HarmonisationConfig | None = None,
) -> pd.DataFrame:
    """Run the gcages CMIP7 global Aneris harmoniser.

    Returns harmonised emissions on the same index shape as the input;
    species absent from the history file are rejected by the harmoniser's
    internal checks. The harmoniser is created via the gcages factory,
    which loads the history and overrides files itself (with
    ``check_hash=True`` on the history) and applies the GCAGES rename.
    """
    cfg = config or HarmonisationConfig()
    harmoniser = create_cmip7_scenariomip_global_harmoniser(
        cmip7_scenariomip_global_historical_emissions_file=cfg.history_path,
        aneris_global_overrides_file=cfg.overrides_path,
        run_checks=cfg.run_checks,
        progress=cfg.progress,
        n_processes=_resolve_n_processes(cfg.n_processes),
    )
    return harmoniser(emissions)


def infill_cmip7(
    harmonised_emissions: pd.DataFrame,
    *,
    config: HarmonisationConfig | None = None,
) -> pd.DataFrame:
    """Infill harmonised emissions onto the full GCAGES driving set.

    Loads the infilling DB, the GHG inversion series and the history (all
    via :mod:`ar7_ch5.cmip7_inputs`, so they arrive in GCAGES naming),
    asserts the input is harmonised at ``harmonisation_year``, then runs
    the gcages ``CMIP7ScenarioMIPInfiller``. Returns the input species
    plus every infilled species the infiller emits, on the same
    ``(model, scenario, region, unit)`` index shape.
    """
    cfg = config or HarmonisationConfig()
    ur = openscm_units.unit_registry
    pint.set_application_registry(ur)

    infilling_db = load_infilling_db(cfg.infilling_db_path, check_hash=False)
    cmip7_ghg_inversions = load_ghg_inversions(cfg.ghg_inversions_path)
    historical_emissions = load_history_emissions(
        cfg.history_path, check_hash=cfg.check_hash
    )

    if cfg.run_checks:
        assert_harmonised(
            harmonised_emissions,
            history=historical_emissions.reset_index(
                level=[
                    lvl
                    for lvl in ["model", "scenario"]
                    if lvl in historical_emissions.index.names
                ],
                drop=True,
            ),
            harmonisation_time=cfg.harmonisation_year,
            history_unit_level="unit",
            ur=ur,
        )

    infiller = CMIP7ScenarioMIPInfiller(
        infilling_db=infilling_db,
        historical_emissions=historical_emissions,
        cmip7_ghg_inversions=cmip7_ghg_inversions,
        harmonisation_year=cfg.harmonisation_year,
        pre_industrial_year=cfg.pre_industrial_year,
        run_checks=cfg.run_checks,
        ur=ur,
    )
    return infiller(harmonised_emissions)


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def harmonise_and_infill(
    raw_emissions_iamc: pd.DataFrame,
    *,
    config: HarmonisationConfig | None = None,
) -> pd.DataFrame:
    """Run the full chapter harmonise+infill pipeline on raw IAM emissions.

    ``raw_emissions_iamc`` is a wide-format DataFrame with a MultiIndex of
    ``(model, scenario, region, variable, unit)`` and integer-year columns,
    carrying variable names in the ``CMIP7_SCENARIOMIP`` convention. The
    returned DataFrame is harmonised at ``config.harmonisation_year``,
    infilled to the GCAGES driving set, and ready for the chapter SCM
    runners (after a final GCAGES -> OPENSCM_RUNNER rename applied at the
    runner boundary).

    The intermediate per-stage outputs are not returned; callers wanting
    them should invoke the helpers individually. Stage-specific drop
    lists land on ``raw_emissions_iamc.attrs`` via the helpers, so they
    survive on the input frame after the call.
    """
    cfg = config or HarmonisationConfig()
    annual = interpolate_to_annual(
        raw_emissions_iamc,
        start_year=cfg.annual_start_year,
        end_year=cfg.annual_end_year,
        clip_to_year=cfg.harmonisation_year,
        allow_leading_nan=True,
    )
    renamed = rename_iamc_to_gcages(annual)
    history_for_splice = load_history_emissions(
        cfg.history_path, check_hash=cfg.check_hash
    )
    spliced = splice_late_starting_from_history(
        renamed,
        history_for_splice,
        anchor_year=cfg.harmonisation_year,
        blend_years=cfg.splice_blend_years,
    )
    cleaned = clean_negatives(spliced)
    if cfg.drops_sidecar_path is not None:
        _write_drops_sidecar(
            cfg.drops_sidecar_path,
            spliced_no_history=spliced.attrs.get("dropped_no_history", []),
            negative_pathways=cleaned.attrs.get("dropped_negative", []),
        )
    harmonised = harmonise_aneris_global(cleaned, config=cfg)
    infilled = infill_cmip7(harmonised, config=cfg)
    return _canonicalise_output_index(infilled)


def _write_drops_sidecar(
    path: Path,
    *,
    spliced_no_history: list,
    negative_pathways: list,
) -> None:
    """Write the pipeline's drop list to a sidecar CSV.

    Columns: ``reason``, ``model``, ``scenario``, ``variable``. The
    ``variable`` column is empty for pathway-level drops; the
    ``scenario`` column is empty when only a (model, scenario) tuple is
    recorded without per-variable detail. Empty drop list still writes
    the header so the cache flow is uniform.
    """
    import csv as _csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = _csv.writer(fh)
        writer.writerow(["reason", "model", "scenario", "variable"])
        for row_idx in spliced_no_history:
            tup = row_idx if isinstance(row_idx, tuple) else (row_idx,)
            model = tup[0] if len(tup) > 0 else ""
            scenario = tup[1] if len(tup) > 1 else ""
            variable = tup[3] if len(tup) > 3 else ""
            writer.writerow(["no_history_for_variable", model, scenario, variable])
        for pair in negative_pathways:
            tup = pair if isinstance(pair, tuple) else (pair,)
            model = tup[0] if len(tup) > 0 else ""
            scenario = tup[1] if len(tup) > 1 else ""
            writer.writerow(["negative_non_co2", model, scenario, ""])


# Canonical IAMC index ordering carried through chapter caches and tests.
# gcages preserves the *names* of the input index levels but does not
# guarantee their *order*; under multiprocessing the level order can flip
# silently. Pinning the order here keeps cached parquets reproducible.
_CANONICAL_INDEX_ORDER: tuple[str, ...] = (
    "model",
    "scenario",
    "region",
    "variable",
    "unit",
)


def _canonicalise_output_index(emissions: pd.DataFrame) -> pd.DataFrame:
    """Reorder the index levels to ``(model, scenario, region, variable, unit)``."""
    if list(emissions.index.names) == list(_CANONICAL_INDEX_ORDER):
        return emissions.sort_index()
    return emissions.reorder_levels(list(_CANONICAL_INDEX_ORDER)).sort_index()


def _resolve_n_processes(requested: int | None) -> int | None:
    """Map the chapter's ``None = autoselect`` to a concrete worker count.

    ``None`` means "use one process per CPU"; on NAC's 256-core boxes that
    is excessive, so we cap at :data:`DEFAULT_HARMONISATION_WORKERS`.
    Aneris does not fork SCM binaries, so it can use more workers than the
    chapter's SCM-run cap (:data:`runners.DEFAULT_MAX_WORKERS = 12`).
    Callers can pass an explicit integer to override the cap entirely.
    """
    if requested is not None:
        return requested
    return min(multiprocessing.cpu_count(), DEFAULT_HARMONISATION_WORKERS)
