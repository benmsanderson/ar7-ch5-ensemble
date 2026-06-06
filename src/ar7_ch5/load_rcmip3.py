"""RCMIP Phase 3 protocol loader (concentration-driven scenarios).

Reads the canonical RCMIP3 concentrations CSV from the published Zenodo
bundle (record 20430630) and returns a :class:`scmdata.ScmRun` of
``Atmospheric Concentrations|*`` rows shaped for the openscm-runner
adapters' concentration-driven mode.

The bundle ships three wide-table CSVs (concentrations, emissions,
forcing); v1 of this loader covers concentrations only -- the chapter's
RCMIP3 use is the diagnostics set (abrupt-CO2 family, 1pctCO2, ssp*-conc,
piControl). Forcing-driven and emissions-driven RCMIP3 scenarios are
deferred until the engine's run-mode surface or a separate loader covers
them.

CSV layout (wide):

    Model,Scenario,Region,Variable,Unit,Activity_Id,Type,Priority,
    Mip_Era,Version,1750,1751,...,2500

Variable names use the IAMC hierarchical convention with pipe
separators (``Atmospheric Concentrations|F-Gases|HFC|HFC125``), which the
adapters already consume directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import scmdata

# Default RCMIP3 diagnostics subset for the chapter. Concentration-driven
# CO2 idealised + 1pctCO2 + piControl + one SSP for cross-comparison. The
# loader accepts any subset of the 25 RCMIP3 conc-driven scenarios; this
# constant is just the default when the caller doesn't pin a subset.
DEFAULT_DIAGNOSTICS: tuple[str, ...] = (
    "abrupt-2xCO2",
    "abrupt-4xCO2",
    "1pctCO2",
    "piControl",
    "ssp245",
)

_REQUIRED_COLUMNS = frozenset(
    {"model", "scenario", "region", "variable", "unit"}
)

_CANONICAL_FILENAME = "rcmip_phase3_concentrations_v2.0.0.csv"


def resolve_concentrations_csv(bundle_path: str | Path) -> Path:
    """Resolve ``bundle_path`` to the concentrations CSV.

    Accepts either the direct CSV, the bundle root, or the
    ``RCMIP3_input_datafiles`` subdirectory.
    """
    p = Path(bundle_path)
    if p.is_file():
        return p
    for candidate in (
        p / _CANONICAL_FILENAME,
        p / "RCMIP3_input_datafiles" / _CANONICAL_FILENAME,
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"RCMIP3 concentrations CSV not found under {p}. Expected "
        f"{_CANONICAL_FILENAME} either at the path itself, directly inside it, "
        "or under an `RCMIP3_input_datafiles/` subdirectory. Download the "
        "bundle from https://zenodo.org/records/20430630."
    )


def load_rcmip3_concentrations(
    bundle_path: str | Path,
    *,
    scenarios: Iterable[str] | None = None,
    region: str = "World",
    end_year: int = 2100,
) -> scmdata.ScmRun:
    """Load RCMIP3 concentration-driven scenarios as a canonical ScmRun.

    Parameters
    ----------
    bundle_path
        Path to the published RCMIP3 bundle (root, ``RCMIP3_input_datafiles/``
        subdir, or the concentrations CSV itself).
    scenarios
        Subset of RCMIP3 scenarios to keep. ``None`` keeps
        :data:`DEFAULT_DIAGNOSTICS`.
    region
        Region to keep. The published file is ``World`` only.
    end_year
        Year axis clip. Default 2100, matching the SCI / SSP2-COM /
        ScenarioMIP horizons.

    Returns
    -------
    scmdata.ScmRun
        One timeseries per ``(scenario, variable)`` with
        ``Atmospheric Concentrations|*`` variable names; ready to be passed
        to :func:`ar7_ch5.runners.orchestrate.run_models` in concentration-
        driven mode.
    """
    csv = resolve_concentrations_csv(bundle_path)
    df = pd.read_csv(csv)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{csv} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["region"] == region]
    wanted = tuple(scenarios) if scenarios is not None else DEFAULT_DIAGNOSTICS
    df = df[df["scenario"].isin(wanted)]
    present = set(df["scenario"].unique())
    if set(wanted) - present:
        raise ValueError(
            f"Requested RCMIP3 scenarios {sorted(set(wanted) - present)} not "
            f"present in {csv}; got {sorted(present)}."
        )

    if df.empty:
        raise ValueError(
            f"No RCMIP3 concentration rows survived filtering of {csv} "
            f"(scenarios={list(wanted)!r}, region={region!r})."
        )

    # Year columns come as strings on disk; clip to end_year and rename to
    # int so scmdata picks up the time axis.
    year_cols = []
    rename: dict[str, int] = {}
    for c in df.columns:
        if isinstance(c, str) and c.isdigit():
            year_int = int(c)
            if year_int <= end_year:
                year_cols.append(c)
                rename[c] = year_int
    meta_cols = [c for c in df.columns if not (isinstance(c, str) and c.isdigit())]
    df = df[meta_cols + year_cols].rename(columns=rename)

    # RCMIP3 scenarios are already canonical; pathway_id == scenario by
    # construction. We emit the column for cross-experiment uniformity --
    # figures, metrics, and the cache reporter all index by pathway_id
    # regardless of input set; see docs/engine_upstream_switch.md.
    df = df.copy()
    df["pathway_id"] = df["scenario"]

    return scmdata.ScmRun(df)
