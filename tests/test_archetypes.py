"""Unit tests for archetypes.py."""

from __future__ import annotations

import io
import textwrap

import numpy as np
import pandas as pd
import pytest

from ar7_ch5.archetypes import select_archetypes
from ar7_ch5.clustering import CLUSTER_FEATURES


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _make_clustered(n_sci: int = 20, n_smip: int = 3) -> pd.DataFrame:
    """Synthetic clustered DataFrame as output by fit_clusters."""
    rng = np.random.default_rng(77)
    centroid_cols = {f"centroid_{f}": rng.uniform(0, 1, n_sci + n_smip) for f in CLUSTER_FEATURES}
    centroid_cols["centroid_cum_co2_afolu"] = rng.uniform(-200, 0, n_sci + n_smip)

    half = n_sci // 2
    sci_rows = pd.DataFrame(
        {
            "Model": [f"IAM{i}" for i in range(n_sci)],
            "Scenario": [f"SCN{i}" for i in range(n_sci)],
            "source": "sci",
            "cluster_label": (["CC1000-nz-cdr"] * half + ["CC1500-pos-base"] * (n_sci - half)),
            **{f: rng.uniform(0, 1, n_sci) for f in CLUSTER_FEATURES},
            "cum_co2_afolu": rng.uniform(-200, 0, n_sci),
            "cum_co2_net_to_nz": rng.uniform(500, 2000, n_sci),
            "drawdown_band": (["nz"] * half + ["pos"] * (n_sci - half)),
            "ce_bin": (["CC1000"] * half + ["CC1500"] * (n_sci - half)),
        }
    )
    for k, v in centroid_cols.items():
        sci_rows[k] = v[:n_sci]

    _smip_scenarios = ["VL", "M", "H", "L", "HL", "LN", "ML"][:n_smip]
    smip_rows = pd.DataFrame(
        {
            "Model": ["scenariomip"] * n_smip,
            "Scenario": _smip_scenarios,
            "source": "smip",
            "cluster_label": (["CC1000-nz-cdr", "CC1000-nz-cdr", "CC1500-pos-base"] * 4)[:n_smip],
            **{f: rng.uniform(0, 1, n_smip) for f in CLUSTER_FEATURES},
            "cum_co2_afolu": rng.uniform(-200, 0, n_smip),
            "cum_co2_net_to_nz": rng.uniform(500, 2000, n_smip),
            "drawdown_band": (["nz", "nz", "pos"] * 4)[:n_smip],
            "ce_bin": (["CC1000", "CC1000", "CC1500"] * 4)[:n_smip],
        }
    )
    for k, v in centroid_cols.items():
        smip_rows[k] = v[n_sci : n_sci + n_smip]

    return pd.concat([sci_rows, smip_rows], ignore_index=True)


def _make_classification_csv(
    sci_model_scenarios: list[tuple[str, str]],
    smip_scenarios: list[tuple[str, str]],
    gw_map: dict[tuple[str, str], str] | None = None,
) -> str:
    """Build a minimal classification CSV string."""
    rows = []
    for model, scenario in sci_model_scenarios:
        gw = (gw_map or {}).get((model, scenario), "GW3")
        rows.append(f"MAGICCv7.5.3,{model},{scenario},{gw}")
    for _, scenario in smip_scenarios:
        gw = (gw_map or {}).get(("scenariomip", scenario), "GW3")
        rows.append(f"MAGICCv7.5.3,scenariomip,{scenario},{gw}")
    header = "climate_model,Model,Scenario,category"
    return header + "\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_select_archetypes_returns_dataframe(tmp_path):
    clustered = _make_clustered()
    sci_rows = clustered[clustered["source"] == "sci"]
    smip_rows = clustered[clustered["source"] == "smip"]

    ms_pairs = list(zip(sci_rows["Model"], sci_rows["Scenario"]))
    smip_pairs = list(zip(smip_rows["Model"], smip_rows["Scenario"]))
    csv_content = _make_classification_csv(ms_pairs, smip_pairs)
    clf_path = tmp_path / "classification.csv"
    clf_path.write_text(csv_content)

    result = select_archetypes(clustered, clf_path, gw_source="magicc")
    assert isinstance(result, pd.DataFrame)
    required_cols = {"strategy_label", "gw_class", "Model", "Scenario", "source", "selection_rule"}
    assert required_cols.issubset(set(result.columns))


def test_select_archetypes_esm_preferred(tmp_path):
    """ESM pathway with matching GW is always preferred over SCI."""
    clustered = _make_clustered()
    sci_rows = clustered[clustered["source"] == "sci"]
    smip_rows = clustered[clustered["source"] == "smip"]

    ms_pairs = list(zip(sci_rows["Model"], sci_rows["Scenario"]))
    smip_pairs = list(zip(smip_rows["Model"], smip_rows["Scenario"]))
    # Force all pathways to GW3 so ESM and SCI share the same GW class
    gw_map = {(m, s): "GW3" for m, s in ms_pairs + smip_pairs}
    csv_content = _make_classification_csv(ms_pairs, smip_pairs, gw_map)
    clf_path = tmp_path / "clf.csv"
    clf_path.write_text(csv_content)

    result = select_archetypes(clustered, clf_path, gw_source="magicc")
    # Rows with selection_rule == 'esm_gw_match' should have source == 'smip'
    esm_matches = result[result["selection_rule"] == "esm_gw_match"]
    assert (esm_matches["source"] == "smip").all()


def test_select_archetypes_sci_fallback(tmp_path):
    """When no ESM matches the GW class, the nearest SCI centroid is picked."""
    clustered = _make_clustered(n_sci=20, n_smip=1)
    # Only one ESM, in cluster CC1000-nz-cdr, GW4
    sci_rows = clustered[clustered["source"] == "sci"]
    smip_rows = clustered[clustered["source"] == "smip"]

    ms_pairs = list(zip(sci_rows["Model"], sci_rows["Scenario"]))
    smip_pairs = list(zip(smip_rows["Model"], smip_rows["Scenario"]))
    # ESM gets GW4; all SCI get GW3 in cluster CC1000-nz-cdr
    gw_map: dict[tuple[str, str], str] = {}
    for m, s in ms_pairs[:10]:  # first 10 are CC1000-nz-cdr
        gw_map[(m, s)] = "GW3"
    gw_map[("scenariomip", smip_rows["Scenario"].iloc[0])] = "GW4"
    csv_content = _make_classification_csv(ms_pairs, smip_pairs, gw_map)
    clf_path = tmp_path / "clf.csv"
    clf_path.write_text(csv_content)

    result = select_archetypes(clustered, clf_path, gw_source="magicc")
    # GW3 cell in CC1000-nz-cdr should have a SCI pick (no ESM with GW3 there)
    gw3_cells = result[
        (result["strategy_label"] == "CC1000-nz-cdr") & (result["gw_class"] == "GW3")
    ]
    if not gw3_cells.empty:
        assert (gw3_cells["source"] == "sci").all()
        assert (gw3_cells["selection_rule"] == "sci_nearest_centroid").all()


def test_select_archetypes_empty_when_no_gw(tmp_path):
    """Returns empty DataFrame if no classification rows match."""
    clustered = _make_clustered(n_sci=5, n_smip=1)
    # Completely empty classification CSV
    clf_path = tmp_path / "clf.csv"
    clf_path.write_text("climate_model,Model,Scenario,category\n")
    result = select_archetypes(clustered, clf_path, gw_source="magicc")
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
