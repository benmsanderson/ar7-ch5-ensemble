"""Lightweight global emissions harmonisation.

v1 deliberately avoids a full harmonisation/infilling stack (no aneris).
SCI and ScenarioMIP CMIP7 inputs already ship harmonised and infilled, so
they are used as-is. SSP2-COM is the only input that needs harmonising.

This module provides a light-touch GLOBAL (World-total) harmoniser. For
each species, the value at ``anchor_year`` (default 2023) is shifted onto
the published 2023 history endpoint (the global anchor from
emissions-harmonisation-historical, Zenodo 17845154); the correction then
tapers linearly to zero by ``convergence_year`` (default 2050). After the
convergence year the scenario passes through unchanged, preserving the
IAM's long-term trajectory in the AR6-aneris convention.

Per-species method: ratio convergence for positive-definite species,
offset convergence for zero-crossing species (``CO2|AFOLU``, ``CO2|EIP``).
The two CO2 sector names from the IAMC convention map onto the adapter-
canonical ``MAGICC`` names through :data:`_CANONICAL_TO_HISTORY`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import scmdata

# Adapter-canonical variable names that the history file calls by their IAMC
# names. Other species (CH4, N2O, HFCs, PFCs, etc.) match directly.
_CANONICAL_TO_HISTORY: dict[str, str] = {
    "Emissions|CO2|MAGICC Fossil and Industrial": (
        "Emissions|CO2|Energy and Industrial Processes"
    ),
    "Emissions|CO2|MAGICC AFOLU": "Emissions|CO2|AFOLU",
}

# Species where the trajectory can change sign over time, so an additive
# (offset) correction is used rather than a multiplicative (ratio) one.
_OFFSET_SPECIES: frozenset[str] = frozenset({
    "Emissions|CO2|MAGICC Fossil and Industrial",
    "Emissions|CO2|MAGICC AFOLU",
})

DEFAULT_ANCHOR_YEAR = 2023
DEFAULT_CONVERGENCE_YEAR = 2050


def load_history_anchor(path: str | Path) -> pd.DataFrame:
    """Load the global history anchor from its sharded feather store.

    Parameters
    ----------
    path
        Directory holding ``index.feather``, ``filemap.feather``, and the
        per-shard ``<n>.feather`` files (the published store from Zenodo
        17845154).

    Returns
    -------
    DataFrame indexed by ``variable`` (IAMC name, World only), with year-int
    columns 1750-2023.
    """
    path = Path(path)
    filemap = pd.read_feather(path / "filemap.feather")
    pieces = [pd.read_feather(path / f) for f in filemap["file_path"]]
    df = pd.concat(pieces).reset_index()
    df = df[df["region"] == "World"]
    year_cols = sorted(c for c in df.columns if isinstance(c, int))
    return df.set_index("variable")[year_cols]


def harmonise(
    scenario: scmdata.ScmRun,
    history: pd.DataFrame,
    *,
    anchor_year: int = DEFAULT_ANCHOR_YEAR,
    convergence_year: int = DEFAULT_CONVERGENCE_YEAR,
) -> scmdata.ScmRun:
    """Anchor scenario's per-species value at ``anchor_year`` to history.

    The correction tapers linearly to zero at ``convergence_year``; after
    that year the scenario is passed through unchanged. Returns a new
    :class:`scmdata.ScmRun` with the harmonised values.

    Species in the scenario but absent from the history are passed through
    untouched (with a one-line NOTE). Species with a zero value at
    ``anchor_year`` are passed through in the ratio path (avoids div-by-
    zero); in the offset path the additive shift still applies.
    """
    if convergence_year <= anchor_year:
        raise ValueError(
            f"convergence_year ({convergence_year}) must exceed "
            f"anchor_year ({anchor_year})."
        )

    ts = scenario.timeseries().copy()
    ts.columns = [c.year if hasattr(c, "year") else c for c in ts.columns]
    year_cols = sorted(c for c in ts.columns if isinstance(c, int))
    if anchor_year not in year_cols:
        raise ValueError(
            f"anchor_year={anchor_year} not in scenario year range "
            f"[{year_cols[0]}, {year_cols[-1]}]."
        )

    weights = _convergence_weights(year_cols, anchor_year, convergence_year)
    out = ts.copy()
    skipped: list[str] = []
    for idx, row in ts.iterrows():
        meta = dict(zip(ts.index.names, idx))
        variable = meta["variable"]
        history_name = _CANONICAL_TO_HISTORY.get(variable, variable)
        if history_name not in history.index:
            skipped.append(variable)
            continue

        scenario_anchor = row[anchor_year]
        history_anchor = history.loc[history_name, anchor_year]

        if variable in _OFFSET_SPECIES:
            full_offset = history_anchor - scenario_anchor
            for y, w in weights.items():
                out.at[idx, y] = row[y] + full_offset * w
        else:
            if scenario_anchor == 0:
                continue
            ratio_at_anchor = history_anchor / scenario_anchor
            for y, w in weights.items():
                factor = 1.0 + (ratio_at_anchor - 1.0) * w
                out.at[idx, y] = row[y] * factor

    if skipped:
        unique_skipped = sorted(set(skipped))
        print(
            f"NOTE: {len(unique_skipped)} variables not in history, "
            f"passed through unharmonised (first 5: {unique_skipped[:5]})."
        )

    out.columns = pd.to_datetime([f"{y}-01-01" for y in out.columns])
    return scmdata.ScmRun(out.reset_index())


def _convergence_weights(
    year_cols: Iterable[int], anchor_year: int, convergence_year: int
) -> dict[int, float]:
    """Linear taper from 1 at ``anchor_year`` to 0 at ``convergence_year``.

    Pre-anchor years get weight 0 (no correction); post-convergence years get
    weight 0 (scenario passes through).
    """
    out: dict[int, float] = {}
    for y in year_cols:
        if y < anchor_year or y >= convergence_year:
            out[y] = 0.0
        else:
            out[y] = 1.0 - (y - anchor_year) / (convergence_year - anchor_year)
    return out
