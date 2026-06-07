"""Unit tests for the declarative GW warming scheme (schemes/gw/si3.json)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ar7_ch5.classification import (
    GW_COLORS,
    GW_ORDER,
    classify_from_metrics,
    classify_single,
    load_gw_scheme,
)


# ---------------------------------------------------------------------------
# Scheme loading + self-containment
# ---------------------------------------------------------------------------

def test_load_default_scheme():
    scheme = load_gw_scheme("si3")
    assert scheme.name
    assert scheme.default_category == "unclassified"
    assert scheme.category_order[0] == "GW0"
    assert "GW8" in scheme.category_order
    assert scheme.colors["GW0"]


def test_module_constants_derive_from_scheme():
    scheme = load_gw_scheme("si3")
    assert GW_ORDER == list(scheme.category_order)
    assert GW_COLORS == dict(scheme.colors)


def test_unknown_scheme_raises():
    with pytest.raises(FileNotFoundError):
        load_gw_scheme("does-not-exist")


# ---------------------------------------------------------------------------
# Cascade reproduces the canonical SI.3 hand-written logic on every branch
# ---------------------------------------------------------------------------

# (pw50, eocw50, pw67, eocw67, declining) -> (category, subcategory)
_CASES = [
    # Missing PW50 → unclassified
    ((np.nan, 1.0, 1.5, 1.5, None), ("unclassified", "unclassified")),
    # GW0 / GW1
    ((1.4, 1.3, 1.5, 1.4, None), ("GW0", "GW0")),
    ((1.55, 1.5, 1.6, 1.5, None), ("GW1", "GW1")),
    # GW2 sub-split on EoCW50 < 1.5
    ((1.65, 1.4, 1.7, 1.6, None), ("GW2", "GW2a")),
    ((1.65, 1.6, 1.7, 1.6, None), ("GW2", "GW2b")),
    ((1.65, np.nan, 1.7, 1.6, None), ("GW2", "GW2b")),
    # GW3 ("likely below 2C": PW67 < 2.0), sub-split on EoCW50 < 1.5
    ((1.8, 1.4, 1.9, 1.7, None), ("GW3", "GW3a")),
    ((1.8, 1.6, 1.9, 1.7, None), ("GW3", "GW3b")),
    # GW4 when PW67 >= 2.0; sub-split on EoCW50 < 1.7
    ((1.8, 1.6, 2.5, 2.0, None), ("GW4", "GW4-I")),
    ((1.8, 1.8, 2.5, 2.0, None), ("GW4", "GW4-II")),
    # NaN PW67 must not trigger GW3 (mirrors pd.notna guard) → GW4
    ((1.8, 1.6, np.nan, 2.0, None), ("GW4", "GW4-I")),
    # GW5 declining split
    ((2.3, 2.0, 2.4, 2.2, True), ("GW5", "GW5-DEC")),
    ((2.3, 2.0, 2.4, 2.2, False), ("GW5", "GW5-Non-DEC")),
    ((2.3, 2.0, 2.4, 2.2, None), ("GW5", "GW5-Non-DEC")),
    # GW6 / GW7 / GW8
    ((2.7, 2.5, 2.8, 2.7, None), ("GW6", "GW6")),
    ((3.2, 3.0, 3.3, 3.2, None), ("GW7", "GW7")),
    ((3.5, 3.4, 3.6, 3.5, None), ("GW8", "GW8")),
    ((4.0, 3.9, 4.2, 4.1, None), ("GW8", "GW8")),
]


@pytest.mark.parametrize("inputs,expected", _CASES)
def test_classify_single_branches(inputs, expected):
    pw50, eocw50, pw67, eocw67, declining = inputs
    assert classify_single(pw50, eocw50, pw67, eocw67, declining) == expected


def test_classify_from_metrics_frame():
    metrics = pd.DataFrame(
        [
            {"peak_warming_50": 1.4, "eoc_warming_50": 1.3,
             "peak_warming_67": 1.5, "eoc_warming_67": 1.4, "declining": False},
            {"peak_warming_50": 2.3, "eoc_warming_50": 2.0,
             "peak_warming_67": 2.4, "eoc_warming_67": 2.2, "declining": True},
            {"peak_warming_50": np.nan, "eoc_warming_50": np.nan,
             "peak_warming_67": np.nan, "eoc_warming_67": np.nan, "declining": None},
        ]
    )
    out = classify_from_metrics(metrics)
    assert list(out["category"]) == ["GW0", "GW5", "unclassified"]
    assert list(out["subcategory"]) == ["GW0", "GW5-DEC", "unclassified"]
