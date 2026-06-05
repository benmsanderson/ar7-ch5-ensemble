"""End-to-end smoke test for the ScenarioMIP CMIP7 experiment.

Runs the full pipeline (load -> SCM run -> per-(scenario, SCM) NetCDF
write) on a tiny ensemble (2 FaIR members on VL and H) and asserts the
files land and 2100 GSAT is physically sane and well-ordered
(VL < H). Smoke-marked; skips when assets are missing.
"""

from __future__ import annotations

import pytest

from ar7_ch5.experiments.scenariomip_cmip7 import run_scenariomip
from ar7_ch5.runners import repo_root, resolve_fair_calibration

CSV = repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("scenariomip_run")


@pytest.fixture(scope="module")
def result(out_dir):
    if not CSV.is_file():
        pytest.skip(f"ScenarioMIP CSV not staged at {CSV}")
    try:
        resolve_fair_calibration()
    except FileNotFoundError as exc:
        pytest.skip(f"FaIR calibration not available: {exc}")
    return run_scenariomip(
        CSV, models=["fair"], scenarios=("VL", "H"),
        n_members=2, output_dir=out_dir,
    )


def test_writes_per_scenario_netcdf(result, out_dir):
    """One NetCDF per (scenario, SCM)."""
    for sc in ("VL", "H"):
        assert (out_dir / "fair" / f"scenariomip_{sc}.nc").is_file()


def test_2100_gsat_well_ordered(result):
    """VL < H at 2100 GSAT median: low-emissions pathway is cooler.

    Filters on ``pathway_id`` (the chapter identifier), not ``scenario``
    (the canonical RCMIP3 name -- ``ssp119`` for VL, ``ssp370`` for H).
    """
    gsat = result.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    )
    vl = gsat.filter(pathway_id="VL").values.mean()
    h = gsat.filter(pathway_id="H").values.mean()
    assert 0.5 < vl < 2.5, f"VL 2100 GSAT={vl} outside physical band"
    assert 2.0 < h < 6.0, f"H 2100 GSAT={h} outside physical band"
    assert vl < h, f"expected VL < H at 2100; got VL={vl}, H={h}"
