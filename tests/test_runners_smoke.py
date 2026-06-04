"""Real-SCM smoke tests: one SCI pathway, two members, per model.

These hit the actual FaIR 2.x / CICERO-SCM 2.1.1 / MAGICC adapters (no mocking)
on a tiny ensemble and assert the 2100 GSAT lands in a physically sane band.
They are marked ``smoke`` and skip when the required assets are absent (the
calibration sets, the SCI xlsx, and for MAGICC the licensed binary), so a bare
checkout still collects and passes.

Run just these with::

    pixi run pytest -m smoke
"""

from __future__ import annotations

import os

import pytest
import scmdata

from ar7_ch5.experiments.sci_ensemble import run_sci_batch
from ar7_ch5.load import available_sci_scenarios, load_sci_infilled
from ar7_ch5.runners import (
    repo_root,
    resolve_ciceroscm_calibration,
    resolve_fair_calibration,
    resolve_magicc_drawnset,
)
from ar7_ch5.runners.orchestrate import run_models

SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)


def _have_magicc() -> bool:
    if not os.environ.get("MAGICC_EXECUTABLE_7"):
        return False
    try:
        return resolve_magicc_drawnset().is_file()
    except FileNotFoundError:
        return False


_MODEL_AVAILABLE = {
    "fair": lambda: resolve_fair_calibration().is_dir(),
    "ciceroscm": lambda: resolve_ciceroscm_calibration().is_dir(),
    "magicc": _have_magicc,
}


@pytest.fixture(scope="module")
def sci_scenario():
    """First SCI (model, scenario) pair as an annual canonical ScmRun.

    Loads from the local CSV cache when present (built by the loader or
    scripts/preprocess_sci.py), so this does not re-parse the xlsx every run.
    """
    if not SCI_XLSX.is_file():
        pytest.skip("SCI xlsx not available (see docs/data_setup.md)")
    iam, scenario = available_sci_scenarios(SCI_XLSX)[0]
    return load_sci_infilled(SCI_XLSX, scenario=scenario, model=iam)


@pytest.mark.smoke
@pytest.mark.parametrize("model", ["fair", "ciceroscm", "magicc"])
def test_single_model_gsat_sane(model, sci_scenario):
    if not _MODEL_AVAILABLE[model]():
        pytest.skip(f"{model} assets unavailable")

    result = run_models(sci_scenario, [model], n_members=2)

    gsat = result.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    )
    assert not gsat.empty, "no 2100 GSAT in output"
    values = gsat.values.ravel()
    assert values.size == 2, f"expected 2 World members, got {values.size}"
    assert ((values > 0.0) & (values < 7.0)).all(), (
        f"{model} 2100 GSAT out of sane band: {values}"
    )


@pytest.mark.smoke
def test_sci_batch_writes_resumable_netcdf(tmp_path):
    """The chunked batch writer lands one NetCDF per (pathway, model) and resumes.

    FaIR-only (no MAGICC binary needed) on two pathways, two members each.
    """
    if not SCI_XLSX.is_file():
        pytest.skip("SCI xlsx not available (see docs/data_setup.md)")
    if not _MODEL_AVAILABLE["fair"]():
        pytest.skip("fair assets unavailable")

    out_dir = tmp_path / "sci"
    first = run_sci_batch(
        SCI_XLSX,
        ["fair"],
        n_members=2,
        output_dir=out_dir,
        limit=2,
    )
    assert len(first) == 2
    assert all(r.status == "written" for r in first), first

    files = sorted((out_dir / "fair").glob("*.nc"))
    assert len(files) == 2, f"expected 2 NetCDF files, got {files}"
    assert (out_dir / "manifest.csv").is_file()

    reloaded = scmdata.ScmRun.from_nc(str(files[0]))
    gsat = reloaded.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    ).values.ravel()
    assert gsat.size == 2, f"expected 2 members, got {gsat.size}"
    assert ((gsat > 0.0) & (gsat < 7.0)).all(), f"GSAT out of band: {gsat}"

    # Re-running with the files in place skips them (resumable).
    second = run_sci_batch(
        SCI_XLSX,
        ["fair"],
        n_members=2,
        output_dir=out_dir,
        limit=2,
    )
    assert all(r.status == "skipped" for r in second), second
