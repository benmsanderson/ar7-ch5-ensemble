"""ScenarioMIP CMIP7 baseline scenario loader.

Reads the published emissions file from `scenariomip-paper-plots`
(github.com/benmsanderson/scenariomip-paper-plots, Zenodo 20329427)
covering the seven CMIP7 baseline scenarios (VL, L, LN, M, ML, H, HL).
Maps the FaIR variable naming convention onto the adapter-canonical
IAMC names (via :data:`ar7_ch5.load.FAIR_TO_CANONICAL`) and returns a
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

from .load import CANONICAL_EMISSIONS, FAIR_TO_CANONICAL

# Long scenario names in the published file map onto the chapter's short
# labels via the existing ``scenario`` column; keep both for figure-side
# joins that prefer the long form.
SCENARIOS = ("VL", "L", "LN", "M", "ML", "H", "HL")

_REQUIRED_COLUMNS = frozenset({"model", "scenario", "region", "variable", "unit"})


def load_scenariomip_emissions(
    path: str | Path,
    *,
    scenarios: Iterable[str] | None = None,
    region: str = "World",
    end_year: int = 2100,
) -> scmdata.ScmRun:
    """Load ScenarioMIP CMIP7 baseline emissions as a canonical ScmRun.

    Parameters
    ----------
    path
        Path to ``emissions_1750-2500.csv`` from scenariomip-paper-plots.
    scenarios
        Subset of :data:`SCENARIOS` to keep. ``None`` keeps all seven.
    region
        Region to keep. The published file is ``World`` only.
    end_year
        Upper bound on the year axis. Default 2100.
    """
    df = pd.read_csv(Path(path))
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["region"] == region]
    if scenarios is not None:
        wanted = set(scenarios)
        df = df[df["scenario"].isin(wanted)]
        present = set(df["scenario"].unique())
        if wanted - present:
            raise ValueError(
                f"Requested scenarios {sorted(wanted - present)} not present "
                f"in {path}; got {sorted(present)}."
            )

    df["variable"] = df["variable"].map(FAIR_TO_CANONICAL)
    df = df[df["variable"].isin(CANONICAL_EMISSIONS)]
    if df.empty:
        raise ValueError(
            f"No ScenarioMIP rows survived canonicalisation of {path} "
            f"(scenarios={scenarios!r}, region={region!r})."
        )

    # Half-year offset columns -> integer years; drop years beyond end_year.
    year_cols = []
    new_names = {}
    for c in df.columns:
        try:
            y = float(c)
        except (TypeError, ValueError):
            continue
        year_int = int(y)
        if year_int <= end_year:
            year_cols.append(c)
            new_names[c] = year_int
    keep_cols = list(_REQUIRED_COLUMNS) + ["long_scenario"] * ("long_scenario" in df.columns) + year_cols
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols].rename(columns=new_names)

    # scmdata expects no duplicate column labels; the half-year convention can
    # produce two .5 offsets falling into the same integer year (rare; drop
    # duplicates by keeping the first).
    df = df.loc[:, ~df.columns.duplicated()]

    return scmdata.ScmRun(df)
