"""Scenario loaders for the SCI input set.

Reads the chapter-harmonised+infilled SCI parquet cache (built by
``scripts/harmonise.py --ensemble sci``) and returns a canonical
:class:`scmdata.ScmRun` whose variable names follow the **GCAGES**
convention. The openscm-runner adapter rename is applied at the runner
boundary (see :mod:`ar7_ch5.runners.orchestrate.rename_to_openscm_runner`).

Convenience accessors for the legacy SCI xlsx (the published ensemble
file) are retained: :func:`load_sci_data_sheet` returns the raw sheet
through the local CSV cache; :func:`load_sci_iamc_global` returns the
wide IAMC frame the classification port (vetting / feasibility / archetype
features) consumes; :func:`load_sci_raw_iamc` returns the raw IAM
``Emissions|*`` rows the harmonisation pipeline starts from.

The shipped ``Climate Assessment|Infilled|*`` namespace used as a
validation reference (see ``scripts/validate_sci_vs_shipped.py``) is
identified by :data:`SCI_INFILLED_NAMESPACE`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import pandas as pd
import scmdata

from ._rcmip3_naming import canonical_for

SCI_INFILLED_NAMESPACE = "Climate Assessment|Infilled|"

_REQUIRED_COLUMNS = frozenset({"model", "scenario", "region", "variable", "unit"})


def _source_fingerprint(path: Path) -> dict:
    """Cheap change-detection key for the source xlsx (no full content hash)."""
    st = path.stat()
    return {"name": path.name, "size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns}


def _restore_year_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce all-digit column names back to ``int`` after a CSV round-trip.

    The source sheet has integer year headers (``2010``, ``2015``, ...); CSV
    stringifies them, and scmdata.ScmRun needs them back as ints to recognise
    the time axis.
    """
    df.columns = [
        int(c) if isinstance(c, str) and c.isdigit() else c for c in df.columns
    ]
    return df


def load_sci_data_sheet(
    path: str | Path, *, sheet: str = "data", refresh: bool = False
) -> pd.DataFrame:
    """Return the SCI worksheet as a DataFrame, via a local CSV cache.

    The published SCI input is a ~120 MB xlsx that openpyxl takes minutes to
    parse. We archive the sheet as a CSV beside the source the first time it is
    read (under ``<source-dir>/cache/``, gitignored) and reuse it thereafter,
    re-parsing the xlsx only when the source file changes (a new published
    version, detected by name/size/mtime) or ``refresh=True``.
    """
    path = Path(path)
    cache = path.parent / "cache" / f"{path.stem}.{sheet}.csv"
    fingerprint = path.parent / "cache" / f"{path.stem}.{sheet}.source.json"
    current = _source_fingerprint(path)

    if not refresh and cache.is_file() and fingerprint.is_file():
        try:
            cached = json.loads(fingerprint.read_text())
        except json.JSONDecodeError:
            cached = None
        if cached == current:
            return _restore_year_columns(pd.read_csv(cache))

    df = pd.read_excel(path, sheet_name=sheet)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    fingerprint.write_text(json.dumps(current, indent=2, sort_keys=True))
    return df


def load_sci_infilled(
    path: str | Path,
    *,
    scenario: str | None = None,
    model: str | None = None,
    region: str = "World",
    sheet: str = "data",  # legacy; ignored once cache path is resolved
    to_annual: bool = True,  # legacy; cache is already annual
) -> scmdata.ScmRun:
    """Load chapter-harmonised+infilled SCI emissions as a canonical ScmRun.

    Reads the parquet cache produced by ``scripts/harmonise.py --ensemble
    sci``. The returned ScmRun carries both ``pathway_id`` (the chapter
    pathway identifier, e.g. ``SSP1-19``) and ``scenario`` (the canonical
    RCMIP3 name the runner splices against, e.g. ``ssp119``). Variable
    names follow the **GCAGES** convention through the body of the
    repository; the openscm-runner adapter rename is applied at the
    runner boundary (see :mod:`ar7_ch5.runners.orchestrate`).

    Parameters
    ----------
    path
        Either the SCI ensemble xlsx (the legacy entry point; the sibling
        ``cache/sci_harmonised_infilled.parquet`` is read), or the
        cache parquet directly (resolved as-is). ``None`` resolves to the
        default cache location under ``data/SCI/cache/``.
    scenario, model
        Optional filters. ``scenario`` selects on the chapter pathway id
        (the original SCI scenario value). SCI scenario names are not
        unique across IAMs, so passing ``model`` as well selects a single
        pathway.
    region
        Region to keep (SCI global file is ``World`` only).
    sheet
        Legacy parameter; ignored once the parquet cache is read.
    to_annual
        Legacy parameter; ignored because the cache is already on the
        2023-2100 annual grid.

    Returns
    -------
    scmdata.ScmRun
        One timeseries per (model, pathway_id, scenario, variable);
        variable names in the GCAGES convention.
    """
    del sheet, to_annual  # legacy parameters; document then drop
    cache_path = _resolve_cache_path(path, ensemble="sci")
    df = _load_harmonised_cache(cache_path, region=region)
    if scenario is not None:
        df = df[df["scenario"] == scenario]
    if model is not None:
        df = df[df["model"] == model]
    if df.empty:
        raise ValueError(
            f"No SCI rows survived filtering of {cache_path} "
            f"(scenario={scenario!r}, model={model!r}, region={region!r})."
        )
    df = _attach_rcmip3_canonical(df)
    return scmdata.ScmRun(df)


_ENSEMBLE_CACHE_FILENAMES: dict[str, str] = {
    "sci": "sci_harmonised_infilled.parquet",
    "ssp2com": "ssp2com_harmonised_infilled.parquet",
    "scenariomip-cmip7": "scenariomip_cmip7_harmonised_infilled.parquet",
}


def _resolve_cache_path(
    path: str | Path | None, *, ensemble: str
) -> Path:
    """Resolve a loader argument to a harmonised+infilled cache parquet.

    * ``None`` -> default location ``data/<ensemble>/cache/<file>.parquet``
      under the repo root.
    * A path ending in ``.parquet`` is returned as-is (caller already
      pointed at a cache parquet, e.g. the test fixture).
    * Any other path (typically the legacy source-file xlsx / csv) is
      mapped to its sibling ``cache/<ensemble>_harmonised_infilled.parquet``.

    Raises :class:`FileNotFoundError` with a clear hint to run
    ``scripts/harmonise.py`` when the resolved cache is absent.
    """
    from .runners import repo_root  # local import to avoid cycle

    cache_filename = _ENSEMBLE_CACHE_FILENAMES[ensemble]
    default_dir = {
        "sci": repo_root() / "data" / "SCI" / "cache",
        "ssp2com": repo_root() / "data" / "ssp2com" / "cache",
        "scenariomip-cmip7": repo_root() / "data" / "scenariomip_cmip7" / "cache",
    }[ensemble]

    if path is None:
        cache = default_dir / cache_filename
    else:
        path = Path(path)
        if path.suffix == ".parquet":
            cache = path
        else:
            cache = path.parent / "cache" / cache_filename

    if not cache.is_file():
        raise FileNotFoundError(
            f"Harmonised+infilled cache not found: {cache}. "
            f"Build it with: pixi run python scripts/harmonise.py --ensemble {ensemble}"
        )
    return cache


def _load_harmonised_cache(cache: Path, *, region: str) -> pd.DataFrame:
    """Read a harmonised+infilled parquet cache into a tidy IAMC frame.

    The parquet stores the multi-indexed wide DataFrame written by
    :func:`ar7_ch5.harmonisation.harmonise_and_infill`. This helper
    returns a tidy frame keyed on ``model, scenario, region, variable,
    unit`` with integer year columns -- the shape ``scmdata.ScmRun``
    consumes. The ``region`` filter is applied here so downstream code
    doesn't have to.
    """
    wide = pd.read_parquet(cache)
    if region in wide.index.get_level_values("region").unique():
        wide = wide.xs(region, level="region", drop_level=False)
    return wide.reset_index()


def iter_sci_infilled(
    path: str | Path,
    *,
    region: str = "World",
    sheet: str = "data",
    to_annual: bool = True,
    pathways: Iterable[tuple[str, str]] | None = None,
) -> Iterator[tuple[str, str, scmdata.ScmRun]]:
    """Yield ``(model, pathway_id, ScmRun)`` for every pathway in the SCI cache.

    Reads the harmonised+infilled parquet cache once, groups by
    ``(model, scenario)`` (the chapter pathway), attaches ``pathway_id``
    + canonical ``scenario`` meta columns, and yields one driving-emissions
    ScmRun per pathway. Variable names follow the GCAGES convention.

    If ``pathways`` is given, only ``(model, pathway_id)`` pairs in
    that set are yielded; the others are skipped silently. Use this to
    restrict the batch to e.g. the vetted subset (see
    :func:`vetted_sci_pathways`).
    """
    del sheet, to_annual  # legacy parameters; document then drop
    cache_path = _resolve_cache_path(path, ensemble="sci")
    df = _load_harmonised_cache(cache_path, region=region)
    wanted: set[tuple[str, str]] | None = (
        {(str(m), str(p)) for m, p in pathways} if pathways is not None else None
    )
    for (model, pathway_id), group in df.groupby(["model", "scenario"], sort=True):
        if wanted is not None and (str(model), str(pathway_id)) not in wanted:
            continue
        group = _attach_rcmip3_canonical(group)
        yield str(model), str(pathway_id), scmdata.ScmRun(group)


def vetted_sci_pathways(
    classification_csv: str | Path,
) -> list[tuple[str, str]]:
    """Return ``[(model, pathway_id), ...]`` for every SCI pathway passing vetting.

    Reads a ``classification_xlsx.csv`` (or per_model / pooled variant)
    produced by ``scripts/classify.py`` and filters to rows with
    ``vetting_status == "passed"``. The result is sorted by
    ``(model, pathway_id)`` for stable iteration order.
    """
    df = pd.read_csv(Path(classification_csv))
    required = {"Model", "Scenario", "vetting_status"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{classification_csv}: missing classification columns "
            f"{sorted(missing)}; expected output of classify.py."
        )
    vetted = df.loc[df["vetting_status"] == "passed", ["Model", "Scenario"]]
    pairs = [(str(m), str(s)) for m, s in vetted.itertuples(index=False)]
    return sorted(pairs)


def _attach_rcmip3_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Attach ``pathway_id`` (original) and overwrite ``scenario`` (canonical).

    The chapter pathway id is preserved on a parallel ``pathway_id`` meta
    column; ``scenario`` is overwritten with the RCMIP3 canonical name the
    runner expects. Both flow through to the output ScmRun as first-class
    meta columns.
    """
    df = df.copy()
    df["pathway_id"] = df["scenario"]
    df["scenario"] = df["scenario"].map(canonical_for)
    return df


def load_sci_raw_iamc(
    path: str | Path,
    *,
    region: str = "World",
    sheet: str = "data",
) -> pd.DataFrame:
    """Return the raw IAM ``Emissions|*`` rows from the SCI ensemble file.

    Output shape matches what :mod:`ar7_ch5.harmonisation` consumes: a
    MultiIndex of ``(model, scenario, region, variable, unit)`` and integer
    year columns, carrying the ``CMIP7_SCENARIOMIP`` variable-naming
    convention as published by SCI. No filtering beyond the variable-prefix
    and region restriction; the harmonisation pipeline handles late-start
    drops, interpolation, naming and vetting.

    This is the entry point for the chapter's chapter-owned harmonisation
    path (PR #26's reference implementation), as distinct from
    :func:`load_sci_infilled` which lifts SCI's shipped
    ``Climate Assessment|Infilled|*`` namespace.
    """
    df = load_sci_data_sheet(Path(path), sheet=sheet)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )
    df = df.set_index(["model", "scenario", "region", "variable", "unit"])
    # Variable prefix filter via the index level. ``Emissions**`` matches
    # every ``Emissions|...`` row including the ``Climate Assessment|...``
    # namespace (which we exclude explicitly), so we use a narrower prefix
    # match here.
    keep = df.index.get_level_values("variable").astype(str).str.startswith(
        "Emissions|"
    )
    region_match = df.index.get_level_values("region") == region
    out = df.loc[keep & region_match]
    out.columns = out.columns.astype(int)
    return out


def available_sci_scenarios(
    path: str | Path, *, sheet: str = "data"
) -> Sequence[tuple[str, str]]:
    """Return the (model, scenario) pairs present in the SCI file."""
    df = load_sci_data_sheet(Path(path), sheet=sheet)
    cols = {c.lower(): c for c in df.columns if isinstance(c, str)}
    pairs = (
        df[[cols["model"], cols["scenario"]]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    return sorted(pairs)


# IAMC convention year columns used by the classification pipeline (5-yearly
# 2010-2100 inclusive, as strings to match scenariocompass).
IAMC_YEAR_COLS = [str(y) for y in range(2010, 2105, 5)]


def load_sci_iamc_global(
    path: str | Path, *, region: str | None = "World", sheet: str = "data"
) -> pd.DataFrame:
    """Return the SCI wide IAMC frame the classification port consumes.

    The classification modules (vetting, feasibility, classification) port from
    scenariocompass, which expects the IAMC convention: Title-case meta columns
    ``Model, Scenario, Region, Variable, Unit`` and *string* year headers
    (``"2010"``, ``"2015"``, ...). :func:`load_sci_data_sheet` returns int
    year columns for ScmRun compatibility, so this helper stringifies them
    back and filters to ``region`` (the global file is ``World`` only).
    """
    df = load_sci_data_sheet(Path(path), sheet=sheet)
    df.columns = [str(c) if isinstance(c, int) else c for c in df.columns]
    if region is not None and "Region" in df.columns:
        df = df.loc[df["Region"] == region].copy()
    return df


def get_variable(df: pd.DataFrame, variable: str) -> pd.DataFrame:
    """Rows for ``variable`` with the ``Variable`` column dropped (tidy frame)."""
    out = df.loc[df["Variable"] == variable].copy()
    return out.drop(columns=["Variable"])


def list_scenarios(df: pd.DataFrame) -> pd.DataFrame:
    """Unique ``(Model, Scenario)`` pairs in ``df``."""
    return df[["Model", "Scenario"]].drop_duplicates().reset_index(drop=True)


def pivot_scenarios(df: pd.DataFrame, variable: str) -> pd.DataFrame:
    """Wide ``(Model, Scenario)``-indexed frame for one variable.

    Filters to ``variable``, keeps the year columns, sets ``(Model, Scenario)``
    as the index, and coerces numeric so the result is ready for arithmetic.
    """
    rows = get_variable(df, variable)
    year_cols = [c for c in rows.columns if isinstance(c, str) and c.isdigit()]
    rows = rows.set_index(["Model", "Scenario"])[year_cols]
    return rows.apply(pd.to_numeric, errors="coerce")
