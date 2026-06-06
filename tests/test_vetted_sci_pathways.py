"""Unit tests for the vetted-SCI-pathways helper.

Covers the small CSV-reader contract (must come from classify.py output,
must error on missing columns). The integration with iter_sci_infilled
and run_sci_batch is exercised by the SCI smoke tests when the SCI xlsx
is staged.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ar7_ch5.load import vetted_sci_pathways


def _write_classification_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_returns_only_passed_pathways(tmp_path):
    csv = tmp_path / "classification.csv"
    _write_classification_csv(csv, [
        {"Model": "AIM/CGE 2.0", "Scenario": "SSP1-19",
         "vetting_status": "passed"},
        {"Model": "AIM/CGE 2.0", "Scenario": "SSP1-26",
         "vetting_status": "failed"},
        {"Model": "REMIND 1.6",  "Scenario": "SSP2-19",
         "vetting_status": "passed"},
        {"Model": "REMIND 1.6",  "Scenario": "SSP2-26",
         "vetting_status": "insufficient_reporting"},
    ])
    result = vetted_sci_pathways(csv)
    assert result == [
        ("AIM/CGE 2.0", "SSP1-19"),
        ("REMIND 1.6",  "SSP2-19"),
    ]


def test_sorted_order(tmp_path):
    """Result is sorted by (model, pathway) for stable batch iteration."""
    csv = tmp_path / "classification.csv"
    _write_classification_csv(csv, [
        {"Model": "Z-MODEL", "Scenario": "SSP3-70",
         "vetting_status": "passed"},
        {"Model": "A-MODEL", "Scenario": "SSP1-19",
         "vetting_status": "passed"},
        {"Model": "A-MODEL", "Scenario": "SSP1-26",
         "vetting_status": "passed"},
    ])
    result = vetted_sci_pathways(csv)
    assert result == [
        ("A-MODEL", "SSP1-19"),
        ("A-MODEL", "SSP1-26"),
        ("Z-MODEL", "SSP3-70"),
    ]


def test_missing_columns_raises(tmp_path):
    csv = tmp_path / "broken.csv"
    _write_classification_csv(csv, [
        {"Model": "AIM/CGE 2.0", "Scenario": "SSP1-19"},
    ])
    with pytest.raises(ValueError, match="missing classification columns"):
        vetted_sci_pathways(csv)


def test_empty_passed_returns_empty(tmp_path):
    csv = tmp_path / "all_failed.csv"
    _write_classification_csv(csv, [
        {"Model": "AIM/CGE 2.0", "Scenario": "SSP1-19",
         "vetting_status": "failed"},
        {"Model": "AIM/CGE 2.0", "Scenario": "SSP1-26",
         "vetting_status": "failed"},
    ])
    assert vetted_sci_pathways(csv) == []
