"""Regression test for the classification port (vetting + feasibility + sustainability).

Pins the counts against scenariocompass's own smoke-test output on the same
SCI 2025 v1.0 global dataset, run via
``scenariocompass/tests/smoke_test.py`` with our cached SCI CSV as input.
The numbers are the ground truth our port must reproduce.

Skipped when the SCI xlsx is absent, so a bare checkout collects cleanly.

To regenerate the reference numbers (e.g. when the SCI dataset is updated):

    /path/to/ar7-ch5-ensemble/.pixi/envs/default/bin/python \\
        /path/to/scenariocompass/tests/smoke_test.py
"""

from __future__ import annotations

import pytest

from ar7_ch5.feasibility import apply_feasibility, apply_sustainability
from ar7_ch5.load import load_sci_iamc_global
from ar7_ch5.runners import repo_root
from ar7_ch5.vetting import apply_vetting

SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)


pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def sci_df():
    if not SCI_XLSX.is_file():
        pytest.skip(f"SCI xlsx not present at {SCI_XLSX}")
    return load_sci_iamc_global(SCI_XLSX)


@pytest.fixture(scope="module")
def vetting(sci_df):
    return apply_vetting(sci_df)


@pytest.fixture(scope="module")
def vetted_df(sci_df, vetting):
    passed = vetting.loc[vetting["vetting_status"] == "passed", ["Model", "Scenario"]]
    return sci_df.merge(passed, on=["Model", "Scenario"])


def test_vetting_counts(vetting):
    """scenariocompass smoke_test on the SCI 2025 v1.0 global file."""
    counts = vetting["vetting_status"].value_counts().to_dict()
    assert counts == {"failed": 1245, "passed": 330, "insufficient_reporting": 24}


def test_feasibility_counts(vetted_df):
    feas = apply_feasibility(vetted_df)
    counts = feas["worst_feasibility"].value_counts().to_dict()
    assert counts == {"major": 270, "medium": 58, "none": 2}


def test_sustainability_counts(vetted_df):
    sust = apply_sustainability(vetted_df)
    counts = sust["worst_sustainability"].value_counts().to_dict()
    assert counts == {"medium": 214, "none": 100, "major": 16}


def test_benchmark_intersection(vetting, vetted_df):
    """No-major-concerns set: vetting passed and worst_{feasibility,sustainability} != major."""
    feas = apply_feasibility(vetted_df)
    sust = apply_sustainability(vetted_df)
    combined = (
        vetting.merge(feas[["Model", "Scenario", "worst_feasibility"]],
                      on=["Model", "Scenario"], how="left")
               .merge(sust[["Model", "Scenario", "worst_sustainability"]],
                      on=["Model", "Scenario"], how="left")
    )
    benchmark = combined.loc[
        (combined["vetting_status"] == "passed")
        & (combined["worst_feasibility"] != "major")
        & (combined["worst_sustainability"] != "major")
    ]
    assert len(benchmark) == 55
