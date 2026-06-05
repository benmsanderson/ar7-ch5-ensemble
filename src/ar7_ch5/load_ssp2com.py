"""SSP2-COM world-total ingestion.

Reads the published SSP2-COM world-total xlsx (one model, one scenario,
World region, 23 species, 2023-2100 mixed 1-/5-yearly) and returns a
canonical :class:`scmdata.ScmRun` whose variable names match the adapter
convention. Pre-2023 is left to each SCM's bundle / historical splice
(FaIR / CICERO run from 1750, MAGICC from 1765); harmonisation to a
published 2023 history endpoint is the next stage (see
:mod:`ar7_ch5.harmonise`).

The xlsx is small (~17 KB, 23 x 28 cells) so we skip the CSV-cache dance
:mod:`ar7_ch5.load` does for the much larger SCI file. Variable / unit /
species canonicalisation is shared with the SCI loader so SSP2-COM and SCI
inputs are indistinguishable to the adapter pool downstream.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import scmdata

from ._rcmip3_naming import canonical_for
from .load import (
    CANONICAL_EMISSIONS,
    _canonicalise_unit,
    _canonicalise_variable,
    _interpolate_annual,
)

# Chapter pathway identifier (preserved on the ``pathway_id`` meta column).
SSP2COM_PATHWAY_ID = "SSP2-com"
SSP2COM_MODEL = "MESSAGE-BASED"
# Canonical RCMIP3 scenario whose bundle row supplies the historical splice
# and natural / land-use forcings (set on the ``scenario`` meta column).
SSP2COM_CANONICAL_SCENARIO = canonical_for(SSP2COM_PATHWAY_ID)

_REQUIRED_COLUMNS = frozenset({"model", "scenario", "region", "variable", "unit"})


def load_ssp2com_world_total(
    path: str | Path,
    *,
    region: str = "World",
    sheet: str = "data",
    to_annual: bool = True,
) -> scmdata.ScmRun:
    """Load SSP2-COM world-total emissions as a canonical ScmRun.

    Parameters
    ----------
    path
        Path to ``ssp2-com_world_total.xlsx``.
    region
        Region to keep. The world-total file is ``World`` only.
    sheet
        Worksheet to read (SSP2-COM convention: ``data``).
    to_annual
        If ``True`` (default), linearly interpolate the native 2023-2100
        mixed-interval timeseries onto an annual grid, matching the SCI
        loader so downstream consumers see one shape.
    """
    path = Path(path)
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["region"] == region].copy()
    df["variable"] = df["variable"].map(_canonicalise_variable)
    df["unit"] = df["unit"].map(_canonicalise_unit)
    df = df[df["variable"].isin(CANONICAL_EMISSIONS)]

    if df.empty:
        raise ValueError(
            f"No SSP2-COM rows survived canonicalisation of {path} "
            f"(region={region!r})."
        )

    # Attach pathway_id (the chapter identifier) and rewrite scenario to the
    # RCMIP3 canonical name the upstream runner splices against. See
    # ar7_ch5._rcmip3_naming.canonical_for and docs/engine_upstream_switch.md.
    df["pathway_id"] = df["scenario"]
    df["scenario"] = df["scenario"].map(canonical_for)

    run = scmdata.ScmRun(df)
    if to_annual:
        run = _interpolate_annual(run)
    return run
