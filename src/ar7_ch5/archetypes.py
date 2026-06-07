"""Archetype scenario selection.

Ported from scenariocompass notebook 05_archetypes.

For each (strategy_label, GW_class) cell, selects the representative
archetype pathway using the following preference order:

1. A ScenarioMIP/SSP2-COM (ESM) pathway whose strategy cluster matches
   **and** whose GW class (from the per-model classification CSV) matches.
2. The SCI pathway closest to the cluster centroid in standardised
   feature space.
3. Cell is left empty if neither condition is satisfied.

Output columns
--------------
strategy_label  Full composite cluster label (e.g. ``CC1000-nz-cdr+ch4``).
gw_class        GW category (``GW0`` … ``GW8``).
Model           IAM model name or ``'scenariomip'``.
Scenario        Scenario / pathway identifier.
source          ``'sci'`` or ``'smip'``.
selection_rule  ``'esm_gw_match'`` or ``'sci_nearest_centroid'``.
dist_to_centroid  Euclidean distance in standardised space (NaN for ESM picks).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from .clustering import CLUSTER_FEATURES

GW_SOURCE = Literal["fair", "ciceroscm", "magicc"]

_SCM_NAMES: dict[str, str] = {
    "fair": "FaIRv2.2.4",
    "ciceroscm": "CICERO-SCM-PY2.1.2",
    "magicc": "MAGICCv7.5.3",
}


def _canonicalise_scm_name(gw_source: str) -> str:
    """Map short SCM name to the exact ``climate_model`` label used in CSVs."""
    return _SCM_NAMES.get(gw_source, gw_source)


def _load_classification(
    classification_csv: str | Path, gw_source: str
) -> pd.DataFrame:
    """Load classification CSV and filter to the requested SCM.

    Returns a DataFrame with columns ``[Model, Scenario, category]``
    where ``category`` is the GW class (``GW0``…``GW8``).
    """
    df = pd.read_csv(Path(classification_csv))
    # SCI per-model CSV has 'climate_model' column; xlsx CSV does not.
    if "climate_model" in df.columns:
        scm = _canonicalise_scm_name(gw_source)
        df = df[df["climate_model"] == scm]
    # Normalise column names
    col_map = {}
    for c in df.columns:
        if c.lower() in ("model", "iam"):
            col_map[c] = "Model"
        elif c.lower() == "scenario":
            col_map[c] = "Scenario"
        elif c.lower() == "category":
            col_map[c] = "category"
    df = df.rename(columns=col_map)
    required = {"Model", "Scenario", "category"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{classification_csv}: missing columns {sorted(missing)} "
            f"(available: {sorted(df.columns)})."
        )
    return df[["Model", "Scenario", "category"]].copy()


def select_archetypes(
    clustered: pd.DataFrame,
    classification_csv: str | Path,
    *,
    gw_source: GW_SOURCE = "magicc",
) -> pd.DataFrame:
    """Select one representative archetype per (strategy_label, GW_class) cell.

    Parameters
    ----------
    clustered
        Output of :func:`ar7_ch5.clustering.fit_clusters`; must have
        ``cluster_label``, ``source``, ``Model``, ``Scenario``, and
        ``centroid_*`` columns for each of :data:`CLUSTER_FEATURES`.
    classification_csv
        Path to a per-model classification CSV produced by
        ``scripts/classify.py``.  The ``gw_source`` SCM's rows are used.
    gw_source
        Which SCM's GW labels to use for GW-class matching and
        representative selection.

    Returns
    -------
    DataFrame with one row per populated (strategy_label, GW_class) cell
    and columns described in the module docstring.
    """
    gw_df = _load_classification(classification_csv, gw_source)

    # Attach GW class to the clustered frame
    merged = clustered.merge(
        gw_df.rename(columns={"category": "gw_class"}),
        on=["Model", "Scenario"],
        how="left",
    )

    # Z-score normalisation parameters from the full SCI set, used for
    # centroid-distance calculations (numpy replacement for StandardScaler).
    sci_rows = merged[merged["source"] == "sci"].copy()
    feature_matrix = sci_rows[CLUSTER_FEATURES].fillna(sci_rows[CLUSTER_FEATURES].median())
    feat_mean = feature_matrix.mean().values.astype(float)
    feat_std = feature_matrix.std(ddof=0).values.astype(float)
    feat_std = np.where(feat_std == 0.0, 1.0, feat_std)

    def _standardise(values: np.ndarray) -> np.ndarray:
        return (np.asarray(values, dtype=float) - feat_mean) / feat_std

    records: list[dict] = []

    strategy_labels = merged["cluster_label"].dropna().unique()

    for strategy in sorted(strategy_labels):
        cell_rows = merged[merged["cluster_label"] == strategy]
        gw_classes = cell_rows["gw_class"].dropna().unique()

        for gw in sorted(gw_classes):
            matching = cell_rows[cell_rows["gw_class"] == gw]
            if matching.empty:
                continue

            # Preference 1: ESM with matching GW class
            esm_match = matching[matching["source"] == "smip"]
            if not esm_match.empty:
                row = esm_match.iloc[0]
                records.append(
                    {
                        "strategy_label": strategy,
                        "gw_class": gw,
                        "Model": row["Model"],
                        "Scenario": row["Scenario"],
                        "source": "smip",
                        "selection_rule": "esm_gw_match",
                        "dist_to_centroid": float("nan"),
                    }
                )
                continue

            # Preference 2: SCI pathway nearest to cluster centroid
            sci_match = matching[matching["source"] == "sci"].copy()
            if sci_match.empty:
                continue

            # Centroid position in standardised space
            centroid_cols = [f"centroid_{f}" for f in CLUSTER_FEATURES]
            centroid_vec = sci_match[centroid_cols].iloc[0].values.astype(float)
            centroid_std = _standardise(centroid_vec)

            feat_vals = sci_match[CLUSTER_FEATURES].fillna(sci_match[CLUSTER_FEATURES].median())
            X_candidates = _standardise(feat_vals.values)
            dists = np.linalg.norm(X_candidates - centroid_std, axis=1)
            best_row = sci_match.iloc[int(np.argmin(dists))]
            records.append(
                {
                    "strategy_label": strategy,
                    "gw_class": gw,
                    "Model": best_row["Model"],
                    "Scenario": best_row["Scenario"],
                    "source": "sci",
                    "selection_rule": "sci_nearest_centroid",
                    "dist_to_centroid": float(np.min(dists)),
                }
            )

    if not records:
        return pd.DataFrame(
            columns=[
                "strategy_label",
                "gw_class",
                "Model",
                "Scenario",
                "source",
                "selection_rule",
                "dist_to_centroid",
            ]
        )
    return pd.DataFrame(records).sort_values(
        ["strategy_label", "gw_class"]
    ).reset_index(drop=True)

