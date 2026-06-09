"""Unit tests for the chapter-owned harmonisation + infilling pipeline helpers.

Covers each named stage of :mod:`ar7_ch5.harmonisation` in isolation. An
end-to-end smoke test against the published SCI ensemble lives at the bottom
and is skipped when the xlsx (or the CMIP7 input files) are absent (bare
checkout).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ar7_ch5.cmip7_inputs import (
    DEFAULT_GHG_INVERSIONS_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_INFILLING_DB_FILE,
    DEFAULT_OVERRIDES_FILE,
)
from ar7_ch5.harmonisation import (
    HarmonisationConfig,
    clean_negatives,
    drop_late_starting_scenarios,
    harmonise_and_infill,
    interpolate_to_annual,
    rename_iamc_to_gcages,
    splice_late_starting_from_history,
)
from ar7_ch5.runners import repo_root

_IDX_NAMES = ["model", "scenario", "region", "variable", "unit"]


def _frame(
    rows: list[tuple], year_columns: list[int], data: np.ndarray
) -> pd.DataFrame:
    """Build a small IAMC-shaped DataFrame for the helper tests."""
    idx = pd.MultiIndex.from_tuples(rows, names=_IDX_NAMES)
    return pd.DataFrame(data, index=idx, columns=year_columns)


# ---------------------------------------------------------------------------
# drop_late_starting_scenarios
# ---------------------------------------------------------------------------


def test_drop_late_starting_scenarios_keeps_early_drops_late():
    """A pathway whose first non-null year is 2025 must be dropped at anchor=2023."""
    rows = [
        ("AIM", "early", "World", "Emissions|CO2", "Mt CO2/yr"),
        ("AIM", "early", "World", "Emissions|BC", "Mt BC/yr"),
        ("AIM", "late", "World", "Emissions|CO2", "Mt CO2/yr"),
        ("AIM", "late", "World", "Emissions|BC", "Mt BC/yr"),
    ]
    yrs = [2010, 2020, 2025, 2030]
    data = np.array(
        [
            [1.0, 1.5, 1.7, 2.0],
            [1.0, 1.5, 1.7, 2.0],
            [np.nan, np.nan, 1.0, 2.0],  # first non-null at 2025 > 2023
            [np.nan, np.nan, 1.0, 2.0],
        ]
    )
    out = drop_late_starting_scenarios(_frame(rows, yrs, data), anchor_year=2023)
    surviving_pairs = out.index.droplevel(["region", "variable", "unit"]).unique()
    assert list(surviving_pairs) == [("AIM", "early")]
    assert out.attrs["dropped_late_starting"] == [("AIM", "late")]


def test_drop_late_starting_scenarios_no_drops_passes_through():
    """When nothing is late, the function should not attach a dropped list."""
    rows = [("AIM", "early", "World", "Emissions|CO2", "Mt CO2/yr")]
    yrs = [2010, 2020, 2023, 2030]
    data = np.array([[1.0, 1.5, 1.7, 2.0]])
    out = drop_late_starting_scenarios(_frame(rows, yrs, data), anchor_year=2023)
    assert len(out) == 1
    assert "dropped_late_starting" not in out.attrs


# ---------------------------------------------------------------------------
# interpolate_to_annual
# ---------------------------------------------------------------------------


def test_interpolate_to_annual_fills_grid_and_clips():
    """Sparse 5-yearly input yields a NaN-free 2023-2100 annual grid."""
    rows = [("AIM", "sA", "World", "Emissions|CO2", "Mt CO2/yr")]
    yrs = [2020, 2025, 2030, 2100]
    data = np.array([[0.0, 5.0, 10.0, 100.0]])
    out = interpolate_to_annual(
        _frame(rows, yrs, data),
        start_year=2010,
        end_year=2100,
        clip_to_year=2023,
    )
    assert list(out.columns) == list(range(2023, 2101))
    assert not out.isnull().any().any()
    # Linear between 2020 (=0) and 2025 (=5): 2023 -> 3.0.
    assert out.iloc[0][2023] == pytest.approx(3.0)
    assert out.iloc[0][2100] == pytest.approx(100.0)


def test_interpolate_to_annual_flat_extrapolates_outside_known_range():
    """Pandas ``interpolate(method="index")`` flat-extrapolates beyond the
    first / last known year.

    This is *not* the protection against late-starting pathways -- that lives
    in :func:`drop_late_starting_scenarios`, which must run first. The test
    pins the documented behaviour so future readers know not to rely on
    interpolation alone to catch a late start.
    """
    rows = [("AIM", "sA", "World", "Emissions|CO2", "Mt CO2/yr")]
    yrs = [2030, 2050]
    data = np.array([[1.0, 2.0]])
    out = interpolate_to_annual(
        _frame(rows, yrs, data),
        start_year=2010,
        end_year=2100,
        clip_to_year=2023,
    )
    # Before the first known year: flat at the first value.
    assert out.iloc[0][2023] == pytest.approx(1.0)
    # After the last known year: flat at the last value.
    assert out.iloc[0][2100] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# rename_iamc_to_gcages
# ---------------------------------------------------------------------------


def test_rename_iamc_to_gcages_maps_co2_sectors_and_drops_aggregates():
    """CO2|EIP -> CO2|Fossil, CO2|AFOLU -> CO2|Biosphere, parents dropped."""
    eip = "Emissions|CO2|Energy and Industrial Processes"
    rows = [
        ("AIM", "sA", "World", eip, "Mt CO2/yr"),
        ("AIM", "sA", "World", "Emissions|CO2|AFOLU", "Mt CO2/yr"),
        ("AIM", "sA", "World", "Emissions|CO2", "Mt CO2/yr"),  # aggregate
        ("AIM", "sA", "World", "Emissions|F-Gases", "kt CO2-equiv/yr"),  # agg
        ("AIM", "sA", "World", "Emissions|Sulfur", "Mt SO2/yr"),
        ("AIM", "sA", "World", "Emissions|HFC|HFC125", "kt HFC125/yr"),
    ]
    df = _frame(rows, [2023, 2024], np.ones((6, 2)))
    out = rename_iamc_to_gcages(df)
    variables = set(out.index.get_level_values("variable").unique())
    assert "Emissions|CO2|Fossil" in variables
    assert "Emissions|CO2|Biosphere" in variables
    assert "Emissions|SOx" in variables
    assert "Emissions|HFC125" in variables
    assert "Emissions|CO2" not in variables
    assert "Emissions|F-Gases" not in variables


# ---------------------------------------------------------------------------
# splice_late_starting_from_history
# ---------------------------------------------------------------------------


def _history_frame(values_by_year: dict[int, float], variable: str) -> pd.DataFrame:
    idx = pd.MultiIndex.from_tuples(
        [(variable, "World", "Mt CO2/yr")], names=["variable", "region", "unit"]
    )
    return pd.DataFrame([values_by_year], index=idx)


def test_splice_history_backfills_and_blends():
    """Late row: history in [anchor, y0-blend], linear blend in (y0-blend, y0)."""
    rows = [("AIM", "late", "World", "Emissions|CO2|Fossil", "Mt CO2/yr")]
    years = list(range(2023, 2036))
    data = np.array([[np.nan] * 7 + [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]])
    # late starts at 2030; blend_years=5 -> exact history in [2023, 2025],
    # linear blend in (2025, 2030).
    df = pd.DataFrame(data, index=pd.MultiIndex.from_tuples(rows, names=_IDX_NAMES))
    df.columns = years

    history = _history_frame(
        {2022: 4.0, 2023: 5.0, 2024: 6.0, 2025: 7.0}, "Emissions|CO2|Fossil"
    )
    out = splice_late_starting_from_history(
        df, history, anchor_year=2023, blend_years=5
    )
    row = out.iloc[0]
    # Exact history at the chapter window head.
    assert row[2023] == pytest.approx(5.0)
    assert row[2024] == pytest.approx(6.0)
    assert row[2025] == pytest.approx(7.0)
    # Linear blend from history(2025)=7 to scenario(2030)=10 across (2025, 2030).
    for y in range(2026, 2030):
        expected = 7.0 + (y - 2025) / 5 * (10.0 - 7.0)
        assert row[y] == pytest.approx(expected)
    # Scenario values untouched from y0 onwards.
    assert row[2030] == pytest.approx(10.0)
    assert row[2031] == pytest.approx(11.0)


def test_splice_history_passes_through_already_anchored():
    """A row with a value at anchor is left untouched."""
    rows = [("AIM", "early", "World", "Emissions|CO2|Fossil", "Mt CO2/yr")]
    years = [2023, 2024, 2025]
    data = np.array([[5.0, 6.0, 7.0]])
    df = pd.DataFrame(data, index=pd.MultiIndex.from_tuples(rows, names=_IDX_NAMES))
    df.columns = years
    history = _history_frame({2023: 99.0}, "Emissions|CO2|Fossil")
    out = splice_late_starting_from_history(
        df, history, anchor_year=2023, blend_years=5
    )
    assert out.iloc[0].tolist() == pytest.approx([5.0, 6.0, 7.0])


def test_splice_history_drops_when_variable_absent_from_history():
    """A late-starting row whose variable isn't in history is dropped + recorded."""
    rows = [("AIM", "late", "World", "Emissions|HFC125", "kt HFC125/yr")]
    years = [2023, 2024, 2030]
    data = np.array([[np.nan, np.nan, 1.0]])
    df = pd.DataFrame(data, index=pd.MultiIndex.from_tuples(rows, names=_IDX_NAMES))
    df.columns = years
    history = _history_frame({2023: 5.0}, "Emissions|CO2|Fossil")  # not HFC125
    out = splice_late_starting_from_history(
        df, history, anchor_year=2023, blend_years=5
    )
    assert out.empty
    assert out.attrs["dropped_no_history"][0][_IDX_NAMES.index("variable")] == (
        "Emissions|HFC125"
    )


# ---------------------------------------------------------------------------
# clean_negatives
# ---------------------------------------------------------------------------


def test_clean_negatives_zeros_tiny_hfcs_keeps_negative_co2():
    """Tiny HFC cells zeroed per-cell; non-CO2 negative drops the pathway;
    negative CO2 OK; HFC values that don't round to zero are left alone.

    Pins the per-cell behaviour (not per-row): a trajectory that decays
    toward zero by 2100 keeps its non-zero years intact.
    """
    rows = [
        ("AIM", "tiny_hfc", "World", "Emissions|HFC125", "kt HFC125/yr"),
        ("AIM", "negative_bc", "World", "Emissions|HFC125", "kt HFC125/yr"),
        ("AIM", "negative_bc", "World", "Emissions|BC", "Mt BC/yr"),
        ("AIM", "negative_co2", "World", "Emissions|CO2|Fossil", "Mt CO2/yr"),
        ("AIM", "decaying_hfc", "World", "Emissions|HFC125", "kt HFC125/yr"),
    ]
    data = np.array(
        [
            [-0.0001, 0.0, 0.001],  # only the tiny cells round to zero
            [1.0, 1.0, 1.0],
            [1.0, -0.5, 1.0],  # negative non-CO2 -> drops "negative_bc"
            [-1.0, 0.0, 1.0],  # negative CO2 is allowed
            [5.0, 1.0, 0.0001],  # decays toward zero; only 2025 zeroes
        ]
    )
    out = clean_negatives(_frame(rows, [2023, 2024, 2025], data))
    surviving = out.index.droplevel(["region", "variable", "unit"]).unique().tolist()
    assert ("AIM", "negative_bc") not in surviving
    assert ("AIM", "tiny_hfc") in surviving
    assert ("AIM", "negative_co2") in surviving
    assert ("AIM", "decaying_hfc") in surviving
    # tiny_hfc: -0.0001 -> 0, 0 -> 0, 0.001 -> 0.001 (unchanged).
    tiny = out.loc[
        ("AIM", "tiny_hfc", "World", "Emissions|HFC125", "kt HFC125/yr")
    ]
    assert tiny[2023] == 0.0
    assert tiny[2024] == 0.0
    assert tiny[2025] == pytest.approx(0.001)
    # decaying_hfc: only the final 0.0001 zeros; 5.0 and 1.0 untouched.
    decay = out.loc[
        ("AIM", "decaying_hfc", "World", "Emissions|HFC125", "kt HFC125/yr")
    ]
    assert decay[2023] == pytest.approx(5.0)
    assert decay[2024] == pytest.approx(1.0)
    assert decay[2025] == 0.0
    assert out.attrs["dropped_negative"] == [("AIM", "negative_bc")]


# ---------------------------------------------------------------------------
# End-to-end smoke (skipped when data is absent)
# ---------------------------------------------------------------------------


SCI_XLSX = repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
SSP2COM_XLSX = repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"
SMIP_CMIP7_CSV = (
    repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
)

_INPUT_FILES = (
    SCI_XLSX,
    DEFAULT_HISTORY_FILE,
    DEFAULT_OVERRIDES_FILE,
    DEFAULT_INFILLING_DB_FILE,
    DEFAULT_GHG_INVERSIONS_FILE,
)


FIXTURE_DIR = repo_root() / "tests" / "fixtures"
SCI_FIXTURE = FIXTURE_DIR / "sci_harmonised_infilled_tiny.parquet"
SSP2COM_FIXTURE = FIXTURE_DIR / "ssp2com_harmonised_infilled_tiny.parquet"
SMIP_CMIP7_FIXTURE = FIXTURE_DIR / "scenariomip_cmip7_harmonised_infilled_tiny.parquet"


def _two_pathway_sci_slice() -> pd.DataFrame:
    """Load the same 2 SCI pathways used to build the golden fixture."""
    from pandas_openscm.indexing import multi_index_match

    from ar7_ch5.load import load_sci_raw_iamc

    raw = load_sci_raw_iamc(SCI_XLSX)
    pairs = list(raw.index.droplevel(["region", "variable", "unit"]).unique())[:2]
    return raw.loc[
        multi_index_match(
            raw.index, pd.MultiIndex.from_tuples(pairs, names=["model", "scenario"])
        )
    ]


@pytest.mark.skipif(
    not all(p.is_file() for p in _INPUT_FILES),
    reason="SCI xlsx or CMIP7 input files absent; bare checkout",
)
def test_harmonise_and_infill_smoke_two_sci_pathways():
    """Run the full pipeline on two SCI pathways and check output shape."""
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    out = harmonise_and_infill(_two_pathway_sci_slice(), config=cfg)
    assert out.index.names == _IDX_NAMES
    species = out.index.get_level_values("variable").unique()
    # All 52 GCAGES driving species should be present after infilling.
    assert len(species) == 52
    assert list(out.columns) == list(range(2023, 2101))
    assert not out.isnull().any().any()


@pytest.mark.skipif(
    not (
        all(p.is_file() for p in _INPUT_FILES[1:])  # CMIP7 inputs only
        and SSP2COM_XLSX.is_file()
    ),
    reason="SSP2-COM xlsx or CMIP7 input files absent",
)
def test_harmonise_and_infill_smoke_ssp2com():
    """SSP2-COM ships in CMIP7_SCENARIOMIP IAMC convention and runs cleanly
    through the pipeline; this test pins that path against silent breakage.
    """
    from ar7_ch5.load_ssp2com import load_ssp2com_raw_iamc

    raw = load_ssp2com_raw_iamc(SSP2COM_XLSX)
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    out = harmonise_and_infill(raw, config=cfg)
    species = out.index.get_level_values("variable").unique()
    assert len(species) == 52
    assert list(out.columns) == list(range(2023, 2101))
    assert not out.isnull().any().any()


@pytest.mark.skipif(
    not (
        all(p.is_file() for p in _INPUT_FILES[1:])  # CMIP7 inputs only
        and SMIP_CMIP7_CSV.is_file()
    ),
    reason="ScenarioMIP CMIP7 csv or CMIP7 input files absent",
)
def test_harmonise_and_infill_smoke_scenariomip_cmip7():
    """End-to-end smoke for ScenarioMIP CMIP7 (all 7 pathways).

    Relies on the chapter-side Halon strip in the raw loader (see
    ``ar7_ch5.load_scenariomip._HALON_STRIP_VARIABLES_IAMC``). If this
    test starts failing on the Halon anchor mismatch again, the strip
    has been removed or the overrides file changed in an incompatible way.
    """
    from ar7_ch5.load_scenariomip import load_scenariomip_cmip7_raw_iamc

    raw = load_scenariomip_cmip7_raw_iamc(SMIP_CMIP7_CSV)
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    out = harmonise_and_infill(raw, config=cfg)
    pathways = out.index.droplevel(["region", "variable", "unit"]).nunique()
    assert pathways == 7
    species = out.index.get_level_values("variable").unique()
    assert len(species) == 52
    assert list(out.columns) == list(range(2023, 2101))
    assert not out.isnull().any().any()


def _golden_assert(fresh: pd.DataFrame, fixture_path: Path) -> None:
    golden = pd.read_parquet(fixture_path)
    fresh_sorted = fresh.sort_index().sort_index(axis="columns")
    golden_sorted = golden.sort_index().sort_index(axis="columns")
    pd.testing.assert_frame_equal(
        fresh_sorted,
        golden_sorted,
        check_exact=False,
        rtol=1e-10,
        atol=1e-12,
    )


@pytest.mark.skipif(
    not all(p.is_file() for p in _INPUT_FILES) or not SCI_FIXTURE.is_file(),
    reason="SCI xlsx, CMIP7 inputs, or golden fixture absent",
)
def test_harmonise_and_infill_matches_sci_golden_fixture():
    """End-to-end regression: a fresh run on 2 SCI pathways must reproduce
    the committed fixture parquet within tight numerical tolerance.

    Fixtures are built by ``scripts/harmonise.py --ensemble <X> --limit N``;
    refresh them intentionally when a chapter-owned harmonisation /
    infilling choice changes (see ``docs/harmonisation_open_questions.md``),
    and unintentionally never.
    """
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    fresh = harmonise_and_infill(_two_pathway_sci_slice(), config=cfg)
    _golden_assert(fresh, SCI_FIXTURE)


@pytest.mark.skipif(
    not (
        all(p.is_file() for p in _INPUT_FILES[1:])
        and SSP2COM_XLSX.is_file()
        and SSP2COM_FIXTURE.is_file()
    ),
    reason="SSP2-COM xlsx, CMIP7 inputs, or golden fixture absent",
)
def test_harmonise_and_infill_matches_ssp2com_golden_fixture():
    """Golden regression for the full SSP2-COM ensemble (1 pathway)."""
    from ar7_ch5.load_ssp2com import load_ssp2com_raw_iamc

    raw = load_ssp2com_raw_iamc(SSP2COM_XLSX)
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    fresh = harmonise_and_infill(raw, config=cfg)
    _golden_assert(fresh, SSP2COM_FIXTURE)


@pytest.mark.skipif(
    not (
        all(p.is_file() for p in _INPUT_FILES[1:])
        and SMIP_CMIP7_CSV.is_file()
        and SMIP_CMIP7_FIXTURE.is_file()
    ),
    reason="ScenarioMIP CMIP7 csv, CMIP7 inputs, or golden fixture absent",
)
def test_harmonise_and_infill_matches_scenariomip_cmip7_golden_fixture():
    """Golden regression for the full ScenarioMIP CMIP7 ensemble (7 pathways)."""
    from ar7_ch5.load_scenariomip import load_scenariomip_cmip7_raw_iamc

    raw = load_scenariomip_cmip7_raw_iamc(SMIP_CMIP7_CSV)
    cfg = HarmonisationConfig(progress=False, n_processes=1)
    fresh = harmonise_and_infill(raw, config=cfg)
    _golden_assert(fresh, SMIP_CMIP7_FIXTURE)
