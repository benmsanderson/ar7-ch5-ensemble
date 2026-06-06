"""Smoke test for the emissions-based classification path (metrics -> classify).

Runs the warming-metrics pipeline (load NetCDFs -> anchor to assessment ->
quantile aggregation) on one pathway whose three-SCM NetCDFs already live
under ``outputs/sci/``. Asserts the plumbing works and produces sensible
shapes / values; does NOT pin specific numbers (the absolute warming values
depend on the SCM calibration subsample and aren't a fixed regression target).

Skipped when the per-pathway NetCDFs are absent (e.g. fresh checkout).
"""

from __future__ import annotations

import pytest

from ar7_ch5.classification import GW_ORDER, classify_from_metrics
from ar7_ch5.metrics import pathway_nc_name, warming_metrics_from_outputs
from ar7_ch5.runners import repo_root

PATHWAY = ("AIM/CGE 2.0", "SSP1-19")
MODELS = ("fair", "ciceroscm", "magicc")
OUTPUTS_DIR = repo_root() / "outputs" / "sci"


pytestmark = pytest.mark.smoke


def _have_all_ncs() -> bool:
    iam, scenario = PATHWAY
    return all(
        (OUTPUTS_DIR / m / pathway_nc_name(iam, scenario)).is_file()
        for m in MODELS
    )


@pytest.fixture(scope="module")
def metrics_per_model():
    if not _have_all_ncs():
        pytest.skip(f"per-pathway NetCDFs missing for {PATHWAY} under {OUTPUTS_DIR}")
    return warming_metrics_from_outputs(
        [PATHWAY], models=MODELS, outputs_dir=OUTPUTS_DIR, source="per_model"
    )


@pytest.fixture(scope="module")
def metrics_pooled():
    if not _have_all_ncs():
        pytest.skip(f"per-pathway NetCDFs missing for {PATHWAY} under {OUTPUTS_DIR}")
    return warming_metrics_from_outputs(
        [PATHWAY], models=MODELS, outputs_dir=OUTPUTS_DIR, source="pooled"
    )


def test_per_model_shape(metrics_per_model):
    """One row per SCM, all required columns present."""
    assert len(metrics_per_model) == 3
    expected_columns = {
        "peak_warming_50", "peak_warming_67",
        "eoc_warming_50", "eoc_warming_67",
        "declining",
    }
    assert expected_columns.issubset(metrics_per_model.columns)
    # The pathway's three climate_models should all appear.
    climate_models = set(
        metrics_per_model.index.get_level_values("climate_model")
    )
    assert climate_models == {"FaIRv2.2.4", "CICERO-SCM-PY2.1.1", "MAGICCv7.5.3"}


def test_per_model_physical(metrics_per_model):
    """Quantile ordering and positivity sanity checks per SCM."""
    for _, row in metrics_per_model.iterrows():
        assert 0.0 < row["peak_warming_50"] < 6.0
        assert row["peak_warming_67"] >= row["peak_warming_50"]
        assert row["eoc_warming_67"] >= row["eoc_warming_50"]
        assert row["peak_warming_50"] >= row["eoc_warming_50"]


def test_pooled_shape(metrics_pooled):
    """Pooled mode collapses across climate_model: one row per pathway.

    Pathway identity is on ``pathway_id`` (the chapter id, e.g.
    ``SSP1-19``); ``scenario`` carries the canonical RCMIP3 name
    (``ssp119``).
    """
    assert len(metrics_pooled) == 1
    assert set(metrics_pooled.index.names) == {"model", "pathway_id"}


def test_pooled_between_per_model_extremes(metrics_per_model, metrics_pooled):
    """Pooled peak_50 sits between the min and max of per-model peak_50."""
    per_model_peaks = metrics_per_model["peak_warming_50"]
    pooled_peak = metrics_pooled["peak_warming_50"].iloc[0]
    assert per_model_peaks.min() <= pooled_peak <= per_model_peaks.max()


def test_classify_from_metrics_per_model(metrics_per_model):
    """classify_from_metrics returns valid GW categories for each SCM."""
    classified = classify_from_metrics(metrics_per_model)
    assert "category" in classified.columns
    assert "subcategory" in classified.columns
    valid = set(GW_ORDER)
    assert set(classified["category"]).issubset(valid)


def test_classify_from_metrics_pooled(metrics_pooled):
    """classify_from_metrics works on the pooled frame too."""
    classified = classify_from_metrics(metrics_pooled)
    assert classified["category"].iloc[0] in GW_ORDER


# Non-SCI input sources --------------------------------------------------

SCENARIOMIP_OUTPUTS_DIR = repo_root() / "outputs" / "scenariomip_cmip7"
SSP2COM_OUTPUTS_DIR = repo_root() / "outputs" / "ssp2com"

SCENARIOMIP_PATHWAYS = [(None, p) for p in ("VL", "L", "LN", "M", "ML", "H", "HL")]
SSP2COM_PATHWAYS = [(None, "SSP2-com")]


def _have_all_nc_for(pathways, models, root, input_source):
    return all(
        (root / m / pathway_nc_name(iam, pid, input_source=input_source)).is_file()
        for m in models for iam, pid in pathways
    )


def test_scenariomip_per_model_classification():
    """End-to-end per-SCM classification on the 7 ScenarioMIP CMIP7 pathways."""
    if not _have_all_nc_for(
        SCENARIOMIP_PATHWAYS, MODELS, SCENARIOMIP_OUTPUTS_DIR, "scenariomip",
    ):
        pytest.skip(
            f"ScenarioMIP CMIP7 NetCDFs missing under {SCENARIOMIP_OUTPUTS_DIR}"
        )
    metrics = warming_metrics_from_outputs(
        SCENARIOMIP_PATHWAYS,
        models=MODELS,
        outputs_dir=SCENARIOMIP_OUTPUTS_DIR,
        source="per_model",
        input_source="scenariomip",
    )
    # 7 pathways x 3 SCMs = 21 rows
    assert len(metrics) == 21
    assert {"climate_model", "model", "pathway_id"}.issubset(
        set(metrics.index.names)
    )
    # Every row should have positive peak warming (anomaly above 1850-1900).
    assert (metrics["peak_warming_50"] > 0).all()
    # All 7 pathway ids appear.
    pathway_ids = set(metrics.index.get_level_values("pathway_id"))
    assert pathway_ids == {"VL", "L", "LN", "M", "ML", "H", "HL"}
    # Classification produces a valid GW category for every row.
    classified = classify_from_metrics(metrics)
    assert set(classified["category"]).issubset(GW_ORDER)


def test_ssp2com_per_model_classification():
    """End-to-end per-SCM classification on the SSP2-COM pathway."""
    if not _have_all_nc_for(
        SSP2COM_PATHWAYS, MODELS, SSP2COM_OUTPUTS_DIR, "ssp2com",
    ):
        pytest.skip(f"SSP2-COM NetCDFs missing under {SSP2COM_OUTPUTS_DIR}")
    metrics = warming_metrics_from_outputs(
        SSP2COM_PATHWAYS,
        models=MODELS,
        outputs_dir=SSP2COM_OUTPUTS_DIR,
        source="per_model",
        input_source="ssp2com",
    )
    # 1 pathway x 3 SCMs = 3 rows
    assert len(metrics) == 3
    # peak_year_end=2100 default keeps CICERO from getting contaminated by
    # the bundle-donor extension past 2100; sanity-check that CICERO's
    # SSP2-COM peak stays below the absurd ~10K we saw without the clip.
    cicero_peak = metrics.xs("CICERO-SCM-PY2.1.2", level="climate_model")[
        "peak_warming_50"
    ]
    assert (cicero_peak < 5.0).all(), (
        "CICERO SSP2-COM peak >= 5K suggests the year_end clip regressed; "
        f"got {cicero_peak.tolist()}"
    )
