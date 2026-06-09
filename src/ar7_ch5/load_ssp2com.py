"""SSP2-COM world-total ingestion.

Reads the published SSP2-COM world-total xlsx (one model, one scenario,
World region, 23 species, 2023-2100 mixed 1-/5-yearly) and returns a
canonical :class:`scmdata.ScmRun` whose variable names match the adapter
convention. Pre-2023 is left to each SCM's bundle / historical splice
(FaIR / CICERO run from 1750, MAGICC from 1765); harmonisation to a
published 2023 history endpoint is the next stage (see
:mod:`ar7_ch5.harmonisation`).

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
    _load_harmonised_cache,
    _resolve_cache_path,
)

# Chapter pathway identifier (preserved on the ``pathway_id`` meta column).
SSP2COM_PATHWAY_ID = "SSP2-com"
SSP2COM_MODEL = "MESSAGE-BASED"
# Canonical RCMIP3 scenario whose bundle row supplies the historical splice
# and natural / land-use forcings (set on the ``scenario`` meta column).
SSP2COM_CANONICAL_SCENARIO = canonical_for(SSP2COM_PATHWAY_ID)

_REQUIRED_COLUMNS = frozenset({"model", "scenario", "region", "variable", "unit"})


def load_ssp2com_world_total(
    path: str | Path | None = None,
    *,
    region: str = "World",
    sheet: str = "data",  # legacy; ignored once cache is resolved
    to_annual: bool = True,  # legacy; cache is already annual
) -> scmdata.ScmRun:
    """Load chapter-harmonised+infilled SSP2-COM emissions as a canonical ScmRun.

    Reads the parquet cache produced by ``scripts/harmonise.py --ensemble
    ssp2com``. Variable names follow the **GCAGES** convention through
    the body of the repository; the openscm-runner adapter rename is
    applied at the runner boundary.

    Parameters
    ----------
    path
        Either the SSP2-COM xlsx (legacy entry point; sibling
        ``cache/ssp2com_harmonised_infilled.parquet`` is read), or the
        cache parquet directly. ``None`` resolves to the default cache
        location under ``data/ssp2com/cache/``.
    region
        Region to keep. The world-total file is ``World`` only.
    sheet, to_annual
        Legacy parameters; ignored because the cache is parquet and is
        already on the 2023-2100 annual grid.
    """
    del sheet, to_annual
    cache_path = _resolve_cache_path(path, ensemble="ssp2com")
    df = _load_harmonised_cache(cache_path, region=region)
    if df.empty:
        raise ValueError(
            f"No SSP2-COM rows in {cache_path} (region={region!r})."
        )
    # Attach pathway_id (the chapter identifier) and rewrite scenario to the
    # RCMIP3 canonical name the upstream runner splices against. See
    # ar7_ch5._rcmip3_naming.canonical_for and docs/engine_upstream_switch.md.
    df["pathway_id"] = df["scenario"]
    df["scenario"] = df["scenario"].map(canonical_for)
    return scmdata.ScmRun(df)


def load_ssp2com_raw_iamc(
    path: str | Path,
    *,
    region: str = "World",
    sheet: str = "data",
) -> pd.DataFrame:
    """Return SSP2-COM world-total emissions in CMIP7_SCENARIOMIP IAMC form.

    The published xlsx already uses the ``CMIP7_SCENARIOMIP`` variable
    convention (``Emissions|HFC|HFC125``, ``Emissions|CO2|AFOLU``,
    ``Emissions|Sulfur``) with Title-cased IAMC meta columns, so the
    loader is a thin normaliser: lower-case the meta columns,
    integerise the string year headers, and set the MultiIndex.

    The chapter ``MESSAGE-BASED`` model is **not** listed in
    ``aneris-overrides-global.csv`` (only seven IAMs are); the
    harmoniser will apply Aneris default heuristics per species. This
    is one of the open questions for the PR review.
    """
    df = pd.read_excel(Path(path), sheet_name=sheet)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required IAMC columns: {sorted(missing)}."
        )

    df = df[df["region"] == region].copy()
    if df.empty:
        raise ValueError(f"No rows for region={region!r} in {path}.")

    df = df.set_index(list(_REQUIRED_COLUMNS))
    new_cols = []
    for c in df.columns:
        try:
            new_cols.append(int(c))
        except (TypeError, ValueError):
            new_cols.append(c)
    df.columns = new_cols
    return df
