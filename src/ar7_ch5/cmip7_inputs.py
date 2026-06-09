"""Default paths and loader shortcuts for the CMIP7 ScenarioMIP harmonisation
and infilling inputs.

The chapter's harmonise+infill pipeline (:mod:`ar7_ch5.harmonisation`) consumes
four files lifted from the CMIP7 ScenarioMIP workflow:

* a ``history`` file (per-species global emissions 1750-2023);
* an ``aneris-overrides`` file (per-(model, variable) harmonisation method
  overrides applied by the global Aneris harmoniser);
* an ``infilling-db`` file (the population of harmonised pathways the
  RMSClosest infiller draws templates from); and
* a ``ghg-inversions`` file (a secondary minor-GHG history series used by the
  infiller).

These files encode chapter-owned scientific choices (which history vintage,
which IAM-specific overrides, which infilling DB version) and live under
``data/cmip7/``. This module resolves the default paths and exposes loader
shortcuts that emit data in the GCAGES variable-naming convention, which is
the convention carried through the chapter pipeline.

The loaders defer to ``gcages.cmip7_scenariomip``; this module is a thin
chapter-side wrapper.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from gcages.cmip7_scenariomip.harmonisation import (
    load_aneris_overrides_file as _gcages_load_aneris_overrides_file,
)
from gcages.cmip7_scenariomip.harmonisation import (
    load_cmip7_scenariomip_historical_emissions as _gcages_load_history,
)
from gcages.cmip7_scenariomip.infilling import (
    load_cmip7_scenariomip_ghg_inversions as _gcages_load_ghg_inversions,
)
from gcages.cmip7_scenariomip.infilling import (
    load_cmip7_scenariomip_infilling_db as _gcages_load_infilling_db,
)
from gcages.renaming import SupportedNamingConventions, convert_variable_name
from pandas_openscm.index_manipulation import update_index_levels_func

from .runners import repo_root

DEFAULT_CMIP7_DIR: Path = repo_root() / "data" / "cmip7"

DEFAULT_HISTORY_FILE: Path = DEFAULT_CMIP7_DIR / "history_cmip7_scenariomip.csv"
DEFAULT_OVERRIDES_FILE: Path = DEFAULT_CMIP7_DIR / "aneris-overrides-global.csv"
DEFAULT_INFILLING_DB_FILE: Path = (
    DEFAULT_CMIP7_DIR / "infilling_db_cmip7_scenariomip_20566343.csv"
)
DEFAULT_GHG_INVERSIONS_FILE: Path = DEFAULT_CMIP7_DIR / "cmip7_ghg_inversions.csv"


def _rename_variable_level(
    df: pd.DataFrame,
    *,
    from_convention: SupportedNamingConventions,
    to_convention: SupportedNamingConventions = SupportedNamingConventions.GCAGES,
) -> pd.DataFrame:
    """Map the ``variable`` index level from one naming convention to another."""
    return update_index_levels_func(
        df,
        {
            "variable": lambda x: convert_variable_name(
                x, from_convention=from_convention, to_convention=to_convention
            )
        },
        copy=False,
    )


def load_history_emissions(
    path: str | Path | None = None,
    *,
    check_hash: bool = True,
) -> pd.DataFrame:
    """Load the CMIP7 ScenarioMIP global history with GCAGES variable names.

    Drops the ``model`` / ``scenario`` index levels so the result is keyed on
    ``(variable, region, unit)`` only -- the shape the Aneris harmoniser and
    the infiller's ``assert_harmonised`` check both expect.
    """
    fp = Path(path) if path is not None else DEFAULT_HISTORY_FILE
    _require_file(fp, "history", "https://zenodo.org/records/20566343")
    df = _gcages_load_history(filepath=fp, check_hash=check_hash)
    df = df.reset_index(
        df.index.names.difference(["variable", "region", "unit"]),  # type: ignore[arg-type]
        drop=True,
    )
    return _rename_variable_level(
        df, from_convention=SupportedNamingConventions.CMIP7_SCENARIOMIP
    )


def load_aneris_overrides(path: str | Path | None = None) -> pd.Series:
    """Load the global Aneris overrides series with GCAGES variable names."""
    fp = Path(path) if path is not None else DEFAULT_OVERRIDES_FILE
    _require_file(fp, "aneris overrides", "PR #26 (Zeb)")
    series = _gcages_load_aneris_overrides_file(filepath=fp)
    # Round-trip through a frame so the variable rename can use the shared
    # ``update_index_levels_func`` (it operates on frames). Mirrors the gcages
    # ``create_cmip7_scenariomip_global_harmoniser`` factory.
    renamed = _rename_variable_level(
        series.to_frame(name="method"),
        from_convention=SupportedNamingConventions.CMIP7_SCENARIOMIP,
    )
    return renamed["method"]


def load_infilling_db(
    path: str | Path | None = None,
    *,
    check_hash: bool = False,
) -> pd.DataFrame:
    """Load the ScenarioMIP infilling database with GCAGES variable names.

    ``check_hash`` defaults to ``False`` because the file is fetched from
    Zenodo and the hash table inside gcages may lag new releases. Enable in
    contexts where the exact Zenodo revision matters.
    """
    fp = Path(path) if path is not None else DEFAULT_INFILLING_DB_FILE
    _require_file(fp, "infilling DB", "https://zenodo.org/records/20566343")
    df = _gcages_load_infilling_db(filepath=fp, check_hash=check_hash)
    return _rename_variable_level(
        df, from_convention=SupportedNamingConventions.CMIP7_SCENARIOMIP
    )


def load_ghg_inversions(path: str | Path | None = None) -> pd.DataFrame:
    """Load the secondary GHG-inversion history with GCAGES variable names.

    The source file ships with ``OPENSCM_RUNNER`` variable names (unlike the
    other three inputs which use ``CMIP7_SCENARIOMIP``); the conversion is
    handled here so callers see a single convention.
    """
    fp = Path(path) if path is not None else DEFAULT_GHG_INVERSIONS_FILE
    _require_file(fp, "GHG inversions", "PR #26 (Zeb)")
    df = _gcages_load_ghg_inversions(filepath=fp)
    return _rename_variable_level(
        df, from_convention=SupportedNamingConventions.OPENSCM_RUNNER
    )


def _require_file(path: Path, label: str, hint: str) -> None:
    if path.is_file():
        return
    raise FileNotFoundError(
        f"CMIP7 {label} file not found: {path}. Fetch from {hint} and place "
        f"under {DEFAULT_CMIP7_DIR}. See docs/data_setup.md."
    )
