"""Scenario loaders for the SCI input set.

Reads the SCI 2025 ensemble xlsx (the ``data`` sheet, IAMC wide format) and
returns a canonical :class:`scmdata.ScmRun` whose variable names match the
openscm-runner adapter convention.

SCI ships SCM-ready driving emissions pre-harmonised and infilled under the
``Climate Assessment|Infilled|Emissions|*`` namespace (54 species). This loader
lifts those directly (no re-harmonisation; see harmonise.py and the brief).

The variable relabelling mirrors the convention the openscm-runner
``scenarios.load_iamc`` loader used on the ``modernisation/integration`` engine
branch. The branch we now pin (``feat/fair2-ciceroscmpy2-adapters-and-runmode``)
does not ship that loader, so the canonicalisation lives here. After stripping
the ``Climate Assessment|Infilled|`` namespace each body is the short IAMC form
(``HFC|HFC125``, ``CO2|Energy and Industrial Processes``) that the adapters
expect once parents are stripped and CO2 sectors mapped to MAGICC names. We keep
the physical ``Emissions|CO2|AFOLU`` and drop ``[NGHGI]`` (see the brief).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import pandas as pd
import scmdata

from ._rcmip3_naming import canonical_for

SCI_INFILLED_NAMESPACE = "Climate Assessment|Infilled|"

# Parents stripped when present at the head of the variable body (after
# ``Emissions|``). Longest-prefix-first so ``F-Gases|HFC|`` matches before the
# bare ``F-Gases|``.
_PARENT_PATHS = (
    "F-Gases|HFC|",
    "F-Gases|PFC|",
    "F-Gases|CFC|",
    "F-Gases|",
    "Montreal Gases|",
    "HFC|",
    "PFC|",
    "CFC|",
)

_SPECIES_RENAMES = {
    "HFC4310": "HFC4310mee",
    "HFC43-10": "HFC4310mee",
    "SOx": "Sulfur",
    "NMVOC": "VOC",
}

# Source CO2 sector names (left) to canonical MAGICC names (right). The
# physical ``AFOLU`` is kept; ``AFOLU [NGHGI]`` is intentionally absent.
_CO2_SECTOR_RENAMES = {
    "Energy and Industrial Processes": "MAGICC Fossil and Industrial",
    "AFOLU": "MAGICC AFOLU",
}

# Canonical emissions species the adapters know how to drive. Anything outside
# this set (e.g. the Montreal gases SCI also infills) is dropped; the adapter's
# bundle / historical splice fills those as concentration inputs.
_EMISSIONS_SPECIES = (
    "CO2|MAGICC Fossil and Industrial",
    "CO2|MAGICC AFOLU",
    "CH4",
    "N2O",
    "HFC125",
    "HFC134a",
    "HFC143a",
    "HFC227ea",
    "HFC23",
    "HFC245fa",
    "HFC32",
    "HFC4310mee",
    "CF4",
    "C2F6",
    "C6F14",
    "SF6",
    "BC",
    "OC",
    "Sulfur",
    "NOx",
    "NH3",
    "VOC",
    "CO",
)
CANONICAL_EMISSIONS = frozenset(f"Emissions|{s}" for s in _EMISSIONS_SPECIES)

# Map FaIR-style variable names (used by scenariomip-paper-plots and Charlie
# Koven's ar7_wg1_ch5) onto the adapter-canonical IAMC names this repo uses.
# Species the FaIR convention writes but we don't drive in v1 (additional HFCs,
# CFCs, halons) are absent; the filter to ``CANONICAL_EMISSIONS`` drops them.
FAIR_TO_CANONICAL: dict[str, str] = {
    "BC": "Emissions|BC",
    "C2F6": "Emissions|C2F6",
    "C6F14": "Emissions|C6F14",
    "CF4": "Emissions|CF4",
    "CH4": "Emissions|CH4",
    "CO": "Emissions|CO",
    "CO2 AFOLU": "Emissions|CO2|MAGICC AFOLU",
    "CO2 FFI": "Emissions|CO2|MAGICC Fossil and Industrial",
    "HFC-125": "Emissions|HFC125",
    "HFC-134a": "Emissions|HFC134a",
    "HFC-143a": "Emissions|HFC143a",
    "HFC-227ea": "Emissions|HFC227ea",
    "HFC-23": "Emissions|HFC23",
    "HFC-245fa": "Emissions|HFC245fa",
    "HFC-32": "Emissions|HFC32",
    "HFC-4310mee": "Emissions|HFC4310mee",
    "N2O": "Emissions|N2O",
    "NH3": "Emissions|NH3",
    "NOx": "Emissions|NOx",
    "OC": "Emissions|OC",
    "SF6": "Emissions|SF6",
    "Sulfur": "Emissions|Sulfur",
    "VOC": "Emissions|VOC",
}

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
    sheet: str = "data",
    to_annual: bool = True,
) -> scmdata.ScmRun:
    """Load SCI infilled driving emissions as a canonical ScmRun.

    The returned ScmRun carries both ``pathway_id`` (the chapter pathway
    identifier, e.g. ``SSP1-19``) and ``scenario`` (the canonical RCMIP3
    name the runner splices against, e.g. ``ssp119``). See
    :mod:`ar7_ch5._rcmip3_naming` for the mapping and
    ``docs/engine_upstream_switch.md`` for why.

    Parameters
    ----------
    path
        Path to the SCI ensemble ``.xlsx``.
    scenario, model
        Optional filters. ``scenario`` selects on the chapter pathway id
        (the original SCI scenario value). SCI scenario names are not
        unique across IAMs, so passing ``model`` as well selects a single
        pathway.
    region
        Region to keep (SCI global file is ``World`` only).
    sheet
        Worksheet to read (SCI convention: ``data``).
    to_annual
        If ``True`` (default), linearly interpolate the native 5-yearly
        timeseries onto an annual grid, which is what the SCM adapters drive on.

    Returns
    -------
    scmdata.ScmRun
        One timeseries per (model, pathway_id, scenario, variable);
        variable names canonicalised to the adapter convention.
    """
    path = Path(path)
    df = _prepare_sci_frame(path, region=region, sheet=sheet)
    if scenario is not None:
        df = df[df["scenario"] == scenario]
    if model is not None:
        df = df[df["model"] == model]

    if df.empty:
        raise ValueError(
            f"No SCI infilled rows survived filtering of {path} "
            f"(scenario={scenario!r}, model={model!r}, region={region!r})."
        )

    df = _attach_rcmip3_canonical(df)
    run = scmdata.ScmRun(df)
    if to_annual:
        run = _interpolate_annual(run)
    return run


def iter_sci_infilled(
    path: str | Path,
    *,
    region: str = "World",
    sheet: str = "data",
    to_annual: bool = True,
    pathways: Iterable[tuple[str, str]] | None = None,
) -> Iterator[tuple[str, str, scmdata.ScmRun]]:
    """Yield ``(model, pathway_id, ScmRun)`` for every pathway in the SCI file.

    Reads and canonicalises the worksheet once (via the CSV cache), then
    groups by ``(model, scenario)`` (the chapter pathway), attaches
    ``pathway_id`` + canonical ``scenario`` meta columns, and yields one
    driving-emissions ScmRun per pathway. This is the batch entry point:
    it avoids re-reading the cache once per scenario, which
    ``load_sci_infilled`` would do when looped.

    If ``pathways`` is given, only ``(model, pathway_id)`` pairs in
    that set are yielded; the others are skipped silently. Use this to
    restrict the batch to e.g. the vetted subset (see
    :func:`vetted_sci_pathways`).
    """
    path = Path(path)
    df = _prepare_sci_frame(path, region=region, sheet=sheet)
    wanted: set[tuple[str, str]] | None = (
        {(str(m), str(p)) for m, p in pathways} if pathways is not None else None
    )
    for (model, pathway_id), group in df.groupby(["model", "scenario"], sort=True):
        if wanted is not None and (str(model), str(pathway_id)) not in wanted:
            continue
        group = _attach_rcmip3_canonical(group)
        run = scmdata.ScmRun(group)
        if to_annual:
            run = _interpolate_annual(run)
        yield str(model), str(pathway_id), run


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


def _prepare_sci_frame(
    path: Path, *, region: str, sheet: str
) -> pd.DataFrame:
    """Load the SCI sheet and return the canonicalised infilled-emissions rows.

    Strips the infilled namespace, maps variable and unit names to the adapter
    convention, keeps ``region`` only, and drops anything outside
    :data:`CANONICAL_EMISSIONS`. All ``(model, scenario)`` pairs are retained;
    callers filter further.
    """
    df = load_sci_data_sheet(path, sheet=sheet)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["variable"].astype(str).str.startswith(SCI_INFILLED_NAMESPACE)]
    df = df.copy()
    df["variable"] = df["variable"].str.slice(len(SCI_INFILLED_NAMESPACE))
    df["variable"] = df["variable"].map(_canonicalise_variable)
    df["unit"] = df["unit"].map(_canonicalise_unit)

    df = df[df["region"] == region]
    df = df[df["variable"].isin(CANONICAL_EMISSIONS)]
    return df


def _interpolate_annual(run: scmdata.ScmRun) -> scmdata.ScmRun:
    years = range(run["year"].min(), run["year"].max() + 1)
    target = [pd.Timestamp(y, 1, 1) for y in years]
    return run.interpolate(target)


def _canonicalise_unit(u: str) -> str:
    if not isinstance(u, str):
        return u
    if "HFC43-10" in u:
        u = u.replace("HFC43-10", "HFC4310mee")
    elif "HFC4310" in u and "HFC4310mee" not in u:
        u = u.replace("HFC4310", "HFC4310mee")
    if "SOx" in u:
        u = u.replace("SOx", "Sulfur")
    if "NMVOC" in u:
        u = u.replace("NMVOC", "VOC")
    return u


def _canonicalise_variable(name: str) -> str:
    if not isinstance(name, str) or not name.startswith("Emissions|"):
        return name
    body = name[len("Emissions|") :]

    if body.startswith("CO2|"):
        sector = body[len("CO2|") :]
        mapped = _CO2_SECTOR_RENAMES.get(sector)
        if mapped is not None:
            return f"Emissions|CO2|{mapped}"
        return name  # let the allowlist drop unmapped CO2 subcategories

    for parent in _PARENT_PATHS:
        if body.startswith(parent):
            body = body[len(parent) :]
            break

    body = _SPECIES_RENAMES.get(body, body)
    return f"Emissions|{body}"


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
