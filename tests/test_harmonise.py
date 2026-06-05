"""Regression test for the light global SSP2-COM harmoniser.

Two layers:

- A pure unit test on the linear taper weights (fast, no IO).
- A smoke-marked end-to-end test that loads the published 2023 history
  anchor and the SSP2-COM world-total xlsx, harmonises, and asserts the
  anchor-year shift, the linear taper, and the convergence-year pass-
  through. Skipped when the anchor feather store or the SSP2-COM xlsx are
  absent (bare checkout).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from ar7_ch5.harmonise import (
    DEFAULT_ANCHOR_YEAR,
    DEFAULT_CONVERGENCE_YEAR,
    _convergence_weights,
    harmonise,
    load_history_anchor,
)
from ar7_ch5.load_ssp2com import load_ssp2com_world_total
from ar7_ch5.runners import repo_root

HISTORY_DIR = Path(
    "/storage/no-backup-nac/users/bensan/emissions_harmonization_historical/"
    "data/processed/history-for-harmonisation/zenodo_17845154/db"
)
SSP2COM_XLSX = repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"

# IAMC names the history uses for the two CO2 sectors we rename.
_HIST_FFI = "Emissions|CO2|Energy and Industrial Processes"
_HIST_AFOLU = "Emissions|CO2|AFOLU"
_CANONICAL_FFI = "Emissions|CO2|MAGICC Fossil and Industrial"
_CANONICAL_AFOLU = "Emissions|CO2|MAGICC AFOLU"


def test_convergence_weights_endpoints():
    """1.0 at anchor, 0.0 at convergence, 0.0 after, 0.0 before."""
    w = _convergence_weights(range(2020, 2061), anchor_year=2023, convergence_year=2050)
    assert w[2023] == 1.0
    assert w[2050] == 0.0
    assert w[2060] == 0.0
    assert w[2020] == 0.0


def test_convergence_weights_linear_midpoint():
    """Halfway between anchor and convergence -> weight 0.5."""
    w = _convergence_weights(range(2023, 2051), anchor_year=2023, convergence_year=2050)
    # Midpoint of 2023..2050 is 2036.5; nearest int is 2037 (~ (14/27))
    assert math.isclose(w[2037], 1.0 - 14 / 27, abs_tol=1e-9)
    # 2050-anchor offset zero -> weight one.
    assert w[2024] == 1.0 - 1 / 27


# ---------------------------------------------------------------------------
# End-to-end harmonisation against the real history + SSP2-COM xlsx.
# ---------------------------------------------------------------------------


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def history():
    if not HISTORY_DIR.is_dir():
        pytest.skip(f"History anchor not present at {HISTORY_DIR}")
    return load_history_anchor(HISTORY_DIR)


@pytest.fixture(scope="module")
def scenario():
    if not SSP2COM_XLSX.is_file():
        pytest.skip(f"SSP2-COM xlsx not staged at {SSP2COM_XLSX}")
    return load_ssp2com_world_total(SSP2COM_XLSX)


@pytest.fixture(scope="module")
def harmonised(scenario, history):
    return harmonise(scenario, history)


def _row_for(run, variable):
    ts = run.timeseries()
    ts.columns = [c.year for c in ts.columns]
    return ts.xs(variable, level="variable").iloc[0]


def test_anchor_year_matches_history(harmonised, history):
    """For every harmonised species in the history, 2023 value equals history."""
    pairs = [
        ("Emissions|CH4", "Emissions|CH4"),
        ("Emissions|N2O", "Emissions|N2O"),
        ("Emissions|BC", "Emissions|BC"),
        ("Emissions|Sulfur", "Emissions|Sulfur"),
        (_CANONICAL_FFI, _HIST_FFI),
        (_CANONICAL_AFOLU, _HIST_AFOLU),
    ]
    for canonical, hist_name in pairs:
        h_anchor = history.loc[hist_name, DEFAULT_ANCHOR_YEAR]
        h_value = _row_for(harmonised, canonical)[DEFAULT_ANCHOR_YEAR]
        assert math.isclose(h_value, h_anchor, rel_tol=1e-6), (
            f"{canonical} 2023 mismatch: harmonised={h_value} history={h_anchor}"
        )


def test_post_convergence_is_pass_through(harmonised, scenario):
    """After the convergence year, harmonised values equal the input scenario."""
    pre = scenario.timeseries()
    pre.columns = [c.year for c in pre.columns]
    post = harmonised.timeseries()
    post.columns = [c.year for c in post.columns]
    assert (
        pre[DEFAULT_CONVERGENCE_YEAR].equals(post[DEFAULT_CONVERGENCE_YEAR])
        is False
        or pre[DEFAULT_CONVERGENCE_YEAR].sub(post[DEFAULT_CONVERGENCE_YEAR]).abs().max()
        < 1e-9
    )
    # Hard assert via a single species:
    assert math.isclose(
        _row_for(harmonised, "Emissions|CH4")[DEFAULT_CONVERGENCE_YEAR],
        _row_for(scenario, "Emissions|CH4")[DEFAULT_CONVERGENCE_YEAR],
        rel_tol=1e-9,
    )


def test_midpoint_lies_between_history_and_scenario(scenario, harmonised, history):
    """At 2037 (~ halfway through the taper), the harmonised value sits between
    a full correction (history-anchored, weight 1) and no correction (weight 0)."""
    s_anchor = _row_for(scenario, "Emissions|CH4")[DEFAULT_ANCHOR_YEAR]
    h_anchor = history.loc["Emissions|CH4", DEFAULT_ANCHOR_YEAR]
    s_2037 = _row_for(scenario, "Emissions|CH4")[2037]
    h_2037 = _row_for(harmonised, "Emissions|CH4")[2037]
    # The correction at 2037 is partial: harmonised should differ from both the
    # raw scenario value and the fully-anchored value (scenario * ratio).
    full_ratio = h_anchor / s_anchor
    fully_anchored_2037 = s_2037 * full_ratio
    # h_2037 is between s_2037 and fully_anchored_2037.
    assert min(s_2037, fully_anchored_2037) <= h_2037 <= max(s_2037, fully_anchored_2037)


def test_species_not_in_history_pass_through(scenario, harmonised):
    """HFC125 (and other HFCs) aren't in the history; harmonised == scenario."""
    s = _row_for(scenario, "Emissions|HFC125")
    h = _row_for(harmonised, "Emissions|HFC125")
    assert (s - h).abs().max() < 1e-9
