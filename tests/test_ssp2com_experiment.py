"""End-to-end smoke test for the SSP2-COM experiment.

Runs the full SSP2-COM pipeline (load -> harmonise -> SCM run -> NetCDF
write) on a tiny ensemble (2 members of FaIR only) and asserts the result
is physically sane. Marked smoke; skips when assets are absent (SSP2-COM
xlsx, history anchor, FaIR calibration).
"""

from __future__ import annotations

import pytest

from ar7_ch5.experiments.ssp2com import run_ssp2com
from ar7_ch5.runners import repo_root, resolve_fair_calibration

SSP2COM_XLSX = repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"


pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("ssp2com_run")


@pytest.fixture(scope="module")
def result(out_dir):
    if not SSP2COM_XLSX.is_file():
        pytest.skip(f"SSP2-COM xlsx not staged at {SSP2COM_XLSX}")
    try:
        resolve_fair_calibration()
    except FileNotFoundError as exc:
        pytest.skip(f"FaIR calibration not available: {exc}")

    return run_ssp2com(
        SSP2COM_XLSX,
        models=["fair"], n_members=2, output_dir=out_dir,
    )


def test_run_succeeds_and_writes_netcdf(result, out_dir):
    """One NetCDF per (pathway, SCM) lands under <output_dir>/<scm>/."""
    from ar7_ch5.load_ssp2com import SSP2COM_PATHWAY_ID
    nc = out_dir / "fair" / f"ssp2com_{SSP2COM_PATHWAY_ID}.nc"
    assert nc.is_file(), f"expected {nc} to exist"


def test_gsat_2100_is_physical(result):
    """SSP2-COM 2100 GSAT (FaIR median) lands in a sane band."""
    gsat = result.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    )
    values = gsat.values.ravel()
    assert values.size == 2
    # SSP2-COM is roughly 2C-ish at 2100; allow a wide physically-reasonable
    # band rather than a narrow regression target (n=2 is too few for tight pins).
    for v in values:
        assert 1.0 < v < 4.0, f"GSAT_2100={v} K outside [1.0, 4.0]"
