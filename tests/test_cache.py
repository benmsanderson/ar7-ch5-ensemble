"""Unit tests for ar7_ch5.cache.

Exercises the per-experiment enumerators against an empty / partial
output tree (tmp_path). No SCM runs, no disk-heavy enumeration.
"""

from __future__ import annotations

import pytest

from ar7_ch5 import cache


def test_status_for_classification_missing(tmp_path):
    entry = cache.status_for("classification", "xlsx", outputs_dir=tmp_path)
    assert entry.experiment == "classification"
    assert entry.scm == "xlsx"
    assert entry.expected == 1
    assert entry.present == 0
    assert entry.missing == 1
    assert not entry.complete
    assert "classify.py" in entry.rerun_cmd
    assert "--source xlsx" in entry.rerun_cmd


def test_status_for_classification_present(tmp_path):
    (tmp_path / "classification_per_model.csv").write_text("header\nrow")
    entry = cache.status_for("classification", "per_model", outputs_dir=tmp_path)
    assert entry.complete
    assert entry.present == 1


def test_status_for_scenariomip_missing(tmp_path):
    entry = cache.status_for("scenariomip_cmip7", "fair", outputs_dir=tmp_path)
    assert entry.experiment == "scenariomip_cmip7"
    assert entry.expected == 7
    assert entry.present == 0
    assert "--experiment scenariomip_cmip7" in entry.rerun_cmd
    assert "--models fair" in entry.rerun_cmd
    # Example missing filenames help the user understand the layout.
    assert entry.examples_missing
    assert all(name.startswith("scenariomip_") for name in entry.examples_missing)


def test_status_for_ssp2com_present_long_climate_model_name(tmp_path):
    """SSP2-COM writes one NC per climate_model (long name); ensure detection."""
    ssp2 = tmp_path / "ssp2com"
    ssp2.mkdir()
    (ssp2 / "FaIRv2.2.4.nc").write_bytes(b"")
    entry = cache.status_for("ssp2com", "fair", outputs_dir=tmp_path)
    assert entry.present == 1
    assert entry.complete


def test_status_for_unknown_experiment_raises():
    with pytest.raises(ValueError, match="Unknown experiment"):
        cache.status_for("not_an_experiment", "fair")


def test_status_default_returns_per_experiment_entries(tmp_path):
    entries = cache.status(outputs_dir=tmp_path)
    # 3 SCMs x 3 experiments (sci, ssp2com, scenariomip) + 3 classification sources
    assert len(entries) == 3 * 3 + 3
    seen = {(e.experiment, e.scm) for e in entries}
    assert ("classification", "xlsx") in seen
    assert ("scenariomip_cmip7", "fair") in seen
    assert ("ssp2com", "magicc") in seen


def test_format_report_includes_experiment_headers_and_rerun_cmds(tmp_path):
    entries = cache.status(outputs_dir=tmp_path)
    report = cache.format_report(entries)
    assert "[classification]" in report
    assert "[ssp2com]" in report
    # Each missing entry should suggest a rerun command.
    assert "classify.py" in report
    assert "run_scenarios.py" in report
