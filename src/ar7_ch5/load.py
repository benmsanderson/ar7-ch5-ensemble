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
from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import scmdata

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

    Parameters
    ----------
    path
        Path to the SCI ensemble ``.xlsx``.
    scenario, model
        Optional filters. SCI scenario names are not unique across IAMs, so
        passing ``model`` as well selects a single pathway.
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
        One timeseries per (model, scenario, variable), variable names
        canonicalised to the adapter convention.
    """
    path = Path(path)
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
    if scenario is not None:
        df = df[df["scenario"] == scenario]
    if model is not None:
        df = df[df["model"] == model]
    df = df[df["variable"].isin(CANONICAL_EMISSIONS)]

    if df.empty:
        raise ValueError(
            f"No SCI infilled rows survived filtering of {path} "
            f"(scenario={scenario!r}, model={model!r}, region={region!r})."
        )

    run = scmdata.ScmRun(df)
    if to_annual:
        run = _interpolate_annual(run)
    return run


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
