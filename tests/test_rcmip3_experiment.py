"""End-to-end smoke test for the RCMIP3 experiment.

Runs FaIR (the only adapter that ships with concentration-driven support
and doesn't need a separate worker pool) on a tiny abrupt-CO2 pair with
2 members and asserts the NetCDFs land, the per-scenario warming is in
the expected band, and abrupt-4x is warmer than abrupt-2x. Also asserts
the MAGICC-skip-with-NOTE behaviour: requesting MAGICC when it doesn't
support concentration-driven mode drops it cleanly rather than
crashing.
"""

from __future__ import annotations

import pytest

from ar7_ch5.experiments.rcmip3 import run_rcmip3
from ar7_ch5.runners import repo_root, resolve_fair_calibration

BUNDLE = repo_root() / "data" / "rcmip3_protocol"


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("rcmip3_run")


@pytest.fixture(scope="module")
def result(out_dir):
    if not BUNDLE.is_dir():
        pytest.skip(f"RCMIP3 bundle not staged at {BUNDLE}")
    try:
        resolve_fair_calibration()
    except FileNotFoundError as exc:
        pytest.skip(f"FaIR calibration not available: {exc}")
    return run_rcmip3(
        BUNDLE,
        models=["fair", "magicc"],   # MAGICC is dropped with a NOTE.
        scenarios=("abrupt-2xCO2", "abrupt-4xCO2"),
        n_members=2,
        output_dir=out_dir,
    )


def test_writes_per_scenario_netcdf(result, out_dir):
    """One NetCDF per (scenario, SCM)."""
    for sc in ("abrupt-2xCO2", "abrupt-4xCO2"):
        assert (out_dir / "fair" / f"rcmip3_{sc}.nc").is_file()
    # MAGICC dropped (no conc-driven support); no directory should appear.
    assert not (out_dir / "magicc").is_dir()


def test_ecs_pair_ordered(result):
    """4xCO2 warmer than 2xCO2 at 2100; both in physically sane bands."""
    gsat = result.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    )
    a2 = gsat.filter(scenario="abrupt-2xCO2").values.mean()
    a4 = gsat.filter(scenario="abrupt-4xCO2").values.mean()
    assert 1.5 < a2 < 5.0, f"abrupt-2xCO2 2100 GSAT={a2} outside physical band"
    assert 3.0 < a4 < 10.0, f"abrupt-4xCO2 2100 GSAT={a4} outside physical band"
    assert a4 > a2, f"expected 4xCO2 > 2xCO2; got a2={a2}, a4={a4}"


def test_no_supported_models_raises():
    """All-unsupported model list raises RuntimeError, not a silent no-op."""
    if not BUNDLE.is_dir():
        pytest.skip(f"RCMIP3 bundle not staged at {BUNDLE}")
    with pytest.raises(RuntimeError, match="No requested SCM declares"):
        run_rcmip3(BUNDLE, models=["magicc"], scenarios=("abrupt-2xCO2",), n_members=1)
