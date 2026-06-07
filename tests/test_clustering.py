"""Unit tests for clustering.py (deterministic archetype labelling)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ar7_ch5.clustering import (
    CLUSTER_FEATURES,
    assign_ce_bin,
    fit_clusters,
    match_suffix,
)


# ---------------------------------------------------------------------------
# assign_ce_bin
# ---------------------------------------------------------------------------

def test_assign_ce_bin_basic():
    vals = np.array([500, 1200, 2000, 5000])
    labels = assign_ce_bin(vals, [1000, 1500, 3000], ["CC1000", "CC1500", "CC3000", "CC3000+"])
    assert list(labels) == ["CC1000", "CC1500", "CC3000", "CC3000+"]


def test_assign_ce_bin_boundary():
    # Value exactly on threshold goes into the higher bin
    vals = np.array([1000.0])
    labels = assign_ce_bin(vals, [1000, 1500, 3000], ["CC1000", "CC1500", "CC3000", "CC3000+"])
    assert labels[0] == "CC1500"


# ---------------------------------------------------------------------------
# match_suffix
# ---------------------------------------------------------------------------

_RULES = {
    "display_order": ["cdr", "deepcdr", "ch4"],
    "rules": {
        "cdr":     {"conditions": [
            {"feature": "cdr_fraction", "op": ">=", "threshold": 0.25},
            {"feature": "cdr_fraction", "op": "<",  "threshold": 0.55},
        ]},
        "deepcdr": {"conditions": [
            {"feature": "cdr_fraction", "op": ">=", "threshold": 0.55},
        ]},
        "ch4":     {"conditions": [
            {"feature": "ch4_reduction", "op": "<=", "threshold": 0.50},
        ]},
    },
}


def test_match_suffix_single():
    feats = {"cdr_fraction": 0.35, "ch4_reduction": 0.8}
    assert match_suffix(feats, _RULES) == "cdr"


def test_match_suffix_combination():
    feats = {"cdr_fraction": 0.35, "ch4_reduction": 0.3}
    assert match_suffix(feats, _RULES) == "cdr+ch4"


def test_match_suffix_base():
    feats = {"cdr_fraction": 0.1, "ch4_reduction": 0.9}
    assert match_suffix(feats, _RULES) == "base"


def test_match_suffix_priority_order():
    """deepcdr and cdr are mutually exclusive by threshold; deepcdr wins."""
    feats = {"cdr_fraction": 0.6, "ch4_reduction": 0.9}
    result = match_suffix(feats, _RULES)
    assert result == "deepcdr"
    assert "cdr" not in result.split("+")


# ---------------------------------------------------------------------------
# fit_clusters (deterministic, declarative)
# ---------------------------------------------------------------------------

def _make_features(n: int, source: str, ce: float = 500.0) -> pd.DataFrame:
    rng = np.random.default_rng(42 + n)
    data = {
        "Model": [f"m{source}{i}" for i in range(n)],
        "Scenario": [f"s{i}" for i in range(n)],
        "source": source,
        "cum_co2_eip": rng.uniform(1000, 5000, n),
        "cdr_fraction": rng.uniform(0, 0.4, n),
        "ch4_reduction": rng.uniform(0.3, 0.9, n),
        "so2_2050_rel": rng.uniform(0.1, 1.0, n),
        "eip_2050_rel": rng.uniform(0.2, 1.0, n),
        "eip_2100_rel": rng.uniform(0.0, 0.5, n),
        "cum_co2_afolu": rng.uniform(-200, 0, n),
        "cum_co2_net_to_nz": np.full(n, ce),
        "drawdown_band": np.where(rng.random(n) > 0.5, "nz", "pos"),
    }
    return pd.DataFrame(data)


def _minimal_scheme() -> dict:
    return {
        "ce_bins": {
            "metric": "cum_co2_net_to_nz",
            "thresholds": [1000, 1500, 3000],
            "labels": ["CC1000", "CC1500", "CC3000", "CC3000+"],
        },
        "drawdown_bands": {
            "metric": "drawdown_band",
            "thresholds": [200],
            "labels": ["pos", "nz", "over"],
        },
        "cluster_features": CLUSTER_FEATURES,
        "suffix_rules": _RULES,
    }


def test_fit_clusters_produces_labels():
    sci = _make_features(30, "sci", ce=500.0)
    smip = _make_features(3, "smip", ce=500.0)
    scheme = _minimal_scheme()
    out = fit_clusters(sci, smip, scheme)
    assert "cluster_label" in out.columns
    assert out["cluster_label"].notna().all()
    assert len(out) == len(sci) + len(smip)


def test_fit_clusters_label_is_deterministic():
    """Running twice yields identical labels (no random seed involved)."""
    sci = _make_features(30, "sci", ce=500.0)
    smip = _make_features(3, "smip", ce=500.0)
    scheme = _minimal_scheme()
    a = fit_clusters(sci.copy(), smip.copy(), scheme)
    b = fit_clusters(sci.copy(), smip.copy(), scheme)
    pd.testing.assert_series_equal(a["cluster_label"], b["cluster_label"])


def test_fit_clusters_label_matches_per_pathway_rules():
    """Each label is exactly ce_bin-drawdown-suffix from the pathway's features."""
    sci = _make_features(20, "sci", ce=500.0)
    smip = _make_features(2, "smip", ce=500.0)
    scheme = _minimal_scheme()
    out = fit_clusters(sci, smip, scheme)

    for _, row in out.iterrows():
        expected_suffix = match_suffix(
            {f: row[f] for f in CLUSTER_FEATURES}, _RULES
        )
        expected = f"CC1000-{row['drawdown_band']}-{expected_suffix}"
        assert row["cluster_label"] == expected


def test_fit_clusters_ce_bin_from_threshold():
    sci = _make_features(10, "sci", ce=2000.0)  # 1500 <= 2000 < 3000 → CC3000
    smip = _make_features(2, "smip", ce=2000.0)
    out = fit_clusters(sci, smip, _minimal_scheme())
    assert (out["ce_bin"] == "CC3000").all()
    assert out["cluster_label"].str.startswith("CC3000-").all()


def test_fit_clusters_centroid_is_group_mean():
    """centroid_* columns equal the mean over pathways sharing the label."""
    sci = _make_features(40, "sci", ce=500.0)
    smip = _make_features(4, "smip", ce=500.0)
    out = fit_clusters(sci, smip, _minimal_scheme())

    for label, grp in out.groupby("cluster_label"):
        for f in CLUSTER_FEATURES + ["cum_co2_afolu"]:
            expected = grp[f].mean()
            np.testing.assert_allclose(grp[f"centroid_{f}"].values, expected)
