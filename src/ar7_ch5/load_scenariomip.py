"""ScenarioMIP CMIP7 baseline scenario loader.

Reads the published emissions file from `scenariomip-paper-plots`
(github.com/benmsanderson/scenariomip-paper-plots, Zenodo 20329427)
covering the seven CMIP7 baseline scenarios (VL, L, LN, M, ML, H, HL).
Maps the FaIR variable naming convention onto the adapter-canonical
CMIP7_SCENARIOMIP IAMC names (via :func:`flat_to_cmip7_iamc`) and returns a
canonical :class:`scmdata.ScmRun`.

The source uses FaIR's half-year offset convention for years (1750.5,
..., 2500.5). We truncate to integer years and clip to ``end_year``
(default 2100, matching the SCI / SSP2-COM horizons and the FaIR
calibration's tested range).

Pre-2010 history in the loaded frame is replaced by each SCM's own
bundle / historical splice at run time, so the file's actual 1750
starting point is informational rather than driving.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import scmdata

from ._rcmip3_naming import canonical_for
from .load import (
    _load_harmonised_cache,
    _resolve_cache_path,
)

# Chapter pathway identifiers (the short labels used throughout the
# chapter / figures). These flow through to the ``pathway_id`` meta column
# on the loaded ScmRun; the ``scenario`` column carries the canonical
# RCMIP3 name (see :mod:`ar7_ch5._rcmip3_naming`).
SCENARIOS = ("VL", "L", "LN", "M", "ML", "H", "HL")

_REQUIRED_COLUMNS = frozenset({"model", "scenario", "region", "variable", "unit"})


def load_scenariomip_emissions(
    path: str | Path | None = None,
    *,
    scenarios: Iterable[str] | None = None,
    region: str = "World",
    end_year: int = 2100,
    extension_csv: str | Path | None = None,
) -> scmdata.ScmRun:
    """Load chapter-harmonised+infilled ScenarioMIP CMIP7 emissions as ScmRun.

    Reads the parquet cache produced by ``scripts/harmonise.py --ensemble
    scenariomip-cmip7``. Variable names follow the **GCAGES** convention
    through the body of the repository; the openscm-runner adapter
    rename is applied at the runner boundary.

    For ``end_year > 2100`` the chapter cache (the harmonise+infill
    output, which ends at 2100) is spliced with the raw IAM emissions
    from ``emissions_1750-2500.csv`` for 2101-``end_year``. The chapter
    owns 2023-2100; the IAM passes through verbatim for the extension
    period (matching the pre-PR-#28 behaviour). Species the IAM does not
    report past 2100 hold flat at their 2100 chapter value.

    Parameters
    ----------
    path
        Either ``emissions_1750-2500.csv`` from scenariomip-paper-plots
        (legacy entry point; sibling cache parquet is read), or the
        cache parquet directly. ``None`` resolves to the default cache
        location.
    scenarios
        Subset of :data:`SCENARIOS` to keep. ``None`` keeps all seven.
    region
        Region to keep.
    end_year
        Upper bound on the year axis. ``2100`` (the cache horizon) is
        the default; higher values trigger the IAM-extension splice.
    extension_csv
        Path to the raw ``emissions_1750-2500.csv`` used for the
        2101-``end_year`` extension. ``None`` resolves to the default
        SMIP CMIP7 source under ``data/scenariomip_cmip7/``.
    """
    cache_path = _resolve_cache_path(path, ensemble="scenariomip-cmip7")
    df = _load_harmonised_cache(cache_path, region=region)
    if scenarios is not None:
        wanted = set(scenarios)
        df = df[df["scenario"].isin(wanted)]
        present = set(df["scenario"].unique())
        if wanted - present:
            raise ValueError(
                f"Requested scenarios {sorted(wanted - present)} not present "
                f"in {cache_path}; got {sorted(present)}."
            )
    if df.empty:
        raise ValueError(
            f"No ScenarioMIP CMIP7 rows in {cache_path} "
            f"(scenarios={scenarios!r}, region={region!r})."
        )

    if end_year > 2100:
        df = _splice_iam_extension(
            df,
            scenarios=scenarios,
            region=region,
            end_year=end_year,
            extension_csv=extension_csv,
            cache_path_for_default=path,
        )

    # Preserve the chapter pathway id on ``pathway_id`` and rewrite ``scenario``
    # to the RCMIP3 canonical the runner splices against.
    df["pathway_id"] = df["scenario"]
    df["scenario"] = df["scenario"].map(canonical_for)
    return scmdata.ScmRun(df)


def _splice_iam_extension(
    df: pd.DataFrame,
    *,
    scenarios: Iterable[str] | None,
    region: str,
    end_year: int,
    extension_csv: str | Path | None,
    cache_path_for_default: str | Path | None,
) -> pd.DataFrame:
    """Splice raw IAM emissions for 2101-``end_year`` onto the chapter cache.

    The cache contributes (model, scenario, region, variable, unit) rows
    with integer year columns 2023..2100. The IAM CSV contributes the
    same species under its flat name convention; we map them to GCAGES
    and concatenate the 2101..end_year columns. Species the IAM does not
    publish (the chapter's 29 infilled species) hold their 2100 value
    flat through the extension period.
    """
    ext_csv = _resolve_extension_csv(extension_csv, cache_path_for_default)
    if not Path(ext_csv).is_file():
        raise FileNotFoundError(
            f"SMIP CMIP7 extension CSV not found: {ext_csv}. "
            "Required for end_year > 2100 (the chapter cache stops at "
            "2100; the IAM CSV provides 2101-2500)."
        )

    raw = load_scenariomip_cmip7_raw_iamc(ext_csv, region=region, end_year=end_year)
    if scenarios is not None:
        wanted = set(scenarios)
        raw = raw[raw.index.get_level_values("scenario").isin(wanted)]

    # Rename CMIP7_SCENARIOMIP -> GCAGES so the splice variable names
    # match the cache. Defer to the chapter pipeline's helper.
    from .harmonisation import rename_iamc_to_gcages

    raw = rename_iamc_to_gcages(raw)
    raw = raw.reset_index()

    # Keep only the 2101..end_year cols + meta.
    meta_cols = ["model", "scenario", "region", "variable", "unit"]
    ext_years = [y for y in range(2101, end_year + 1) if y in raw.columns]
    if not ext_years:
        return df
    raw = raw[meta_cols + ext_years]

    # Concatenate cache (2023..2100) + IAM extension (2101..end_year) per
    # (model, scenario, region, variable, unit). Rows present only in
    # the cache (the infilled-only species) extend flat from 2100.
    merged = df.merge(raw, on=meta_cols, how="left", suffixes=("", "_ext"))
    for y in ext_years:
        col_ext = y if y in raw.columns else f"{y}_ext"
        merged[y] = merged.get(col_ext, merged.get(2100))
        if col_ext in merged.columns and col_ext != y:
            merged.drop(columns=[col_ext], inplace=True)
    # Fill remaining post-2100 NaNs (infilled-only species) with the 2100 value.
    for y in ext_years:
        merged[y] = merged[y].fillna(merged[2100])
    return merged


def _resolve_extension_csv(
    extension_csv: str | Path | None,
    cache_path_for_default: str | Path | None,
) -> Path:
    """Find the raw IAM CSV; prefer an explicit override, then the default."""
    if extension_csv is not None:
        return Path(extension_csv)
    if cache_path_for_default is not None:
        candidate = Path(cache_path_for_default)
        if candidate.suffix == ".csv":
            return candidate
    # Fall back to the canonical staged location.
    from .runners import repo_root

    return repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"


# The scenariomip-paper-plots emissions file
# (``data/scenariomip_cmip7/emissions_1750-2500.csv``, Zenodo 20329427) ships
# variable names in a flat, FaIR-style convention (``BC``, ``CO2 FFI``,
# ``HFC-125``, ``CFC-11``, ``Halon-1211``, ``c-C4F8``, ``HFC-4310mee``). The
# chapter harmonise+infill pipeline wants ``CMIP7_SCENARIOMIP`` IAMC names.
# We resolve the conversion in two stages: a small normaliser to the
# OPENSCM_RUNNER body, then defer to ``gcages.convert_variable_name`` for the
# OPENSCM_RUNNER -> CMIP7_SCENARIOMIP translation. All 52 species present in
# the file convert cleanly under this scheme; see tests/test_load_scenariomip.
_FLAT_TO_OPENSCM_RUNNER_BODY_OVERRIDES: dict[str, str] = {
    "CO2 FFI": "CO2|MAGICC Fossil and Industrial",
    "CO2 AFOLU": "CO2|MAGICC AFOLU",
    "HFC-43-10mee": "HFC4310mee",
    "c-C4F8": "cC4F8",
}
_HYPHEN_STRIPPED_PREFIXES: tuple[str, ...] = (
    "HFC-",
    "CFC-",
    "HCFC-",
    "Halon-",
)


def _flat_to_openscm_runner_body(flat: str) -> str:
    """Map a scenariomip-paper-plots flat name to the OPENSCM_RUNNER body."""
    if flat in _FLAT_TO_OPENSCM_RUNNER_BODY_OVERRIDES:
        return _FLAT_TO_OPENSCM_RUNNER_BODY_OVERRIDES[flat]
    for prefix in _HYPHEN_STRIPPED_PREFIXES:
        if flat.startswith(prefix):
            return prefix.rstrip("-") + flat[len(prefix):]
    return flat


def flat_to_cmip7_iamc(flat: str) -> str:
    """Convert a scenariomip-paper-plots flat name to ``CMIP7_SCENARIOMIP`` IAMC.

    Public so the raw-load tests can pin every published species against the
    gcages converter.
    """
    from gcages.renaming import SupportedNamingConventions, convert_variable_name

    body = _flat_to_openscm_runner_body(flat)
    return convert_variable_name(
        f"Emissions|{body}",
        from_convention=SupportedNamingConventions.OPENSCM_RUNNER,
        to_convention=SupportedNamingConventions.CMIP7_SCENARIOMIP,
    )


# Species stripped from the ScenarioMIP CMIP7 raw input before
# harmonisation; the infiller re-supplies them from the inversion history.
# IAM submissions carry non-zero 2023 values that the chapter history files
# as zero, which aneris cannot reconcile while landing exactly on history
# (no anchor-respecting method exists for IAM > 0 vs history == 0).
# Treating them as infillable matches their natural role in the
# harmonise+infill split and avoids per-(model, variable) hist_zero
# overrides for an inconsistent species set.
# See docs/harmonisation_open_questions.md (Q1).
_HALON_STRIP_VARIABLES_IAMC: frozenset[str] = frozenset({
    "Emissions|Halon1202",
    "Emissions|Halon2402",
})


def load_scenariomip_cmip7_raw_iamc(
    path: str | Path,
    *,
    region: str = "World",
    end_year: int = 2100,
) -> pd.DataFrame:
    """Return ScenarioMIP CMIP7 raw IAM emissions in CMIP7_SCENARIOMIP IAMC form.

    Reads ``emissions_1750-2500.csv`` from scenariomip-paper-plots (Zenodo
    20329427), converts the flat variable names to ``CMIP7_SCENARIOMIP``
    IAMC, truncates the half-year time stamps to integer years and clips
    to ``end_year``. Output shape matches what
    :mod:`ar7_ch5.harmonisation` consumes: a MultiIndex of
    ``(model, scenario, region, variable, unit)`` with integer year columns.

    The ``scenario`` column carries the chapter pathway short code
    (``VL``, ``L``, ..., ``HL``); the ``long_scenario`` IAMC label is
    dropped here -- it's an audit-only field downstream of harmonisation.

    ``Emissions|Halon1202`` / ``Emissions|Halon2402`` are stripped from the
    output (see ``_HALON_STRIP_VARIABLES_IAMC``); the infiller re-supplies
    them from the inversion history.
    """
    df = pd.read_csv(Path(path))
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["region"] == region].copy()
    if df.empty:
        raise ValueError(f"No rows for region={region!r} in {path}.")

    df["variable"] = df["variable"].map(flat_to_cmip7_iamc)
    df = df[~df["variable"].isin(_HALON_STRIP_VARIABLES_IAMC)]

    year_cols: list = []
    rename: dict = {}
    for c in df.columns:
        try:
            y = float(c)
        except (TypeError, ValueError):
            continue
        year_int = int(y)
        if year_int <= end_year:
            year_cols.append(c)
            rename[c] = year_int

    drop_cols = ["long_scenario"] if "long_scenario" in df.columns else []
    keep_cols = list(_REQUIRED_COLUMNS) + year_cols
    df = df[keep_cols + [c for c in df.columns if c == "long_scenario"]].drop(
        columns=drop_cols
    )
    df = df.rename(columns=rename)
    df = df.loc[:, ~df.columns.duplicated()]
    return df.set_index(list(_REQUIRED_COLUMNS))
