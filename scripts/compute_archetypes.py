"""Compute emissions archetypes.

End-to-end pipeline: feature extraction → two-axis clustering →
archetype selection.  Produces three output CSVs:

  outputs/archetype_features.csv    one row per pathway with all nine features
  outputs/clusters.csv              as above plus cluster_label and centroid_*
  outputs/archetypes.csv            ~45 representative (strategy, GW) picks

Usage
-----
    pixi run python scripts/compute_archetypes.py
    pixi run python scripts/compute_archetypes.py \\
        --sci-xlsx data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx \\
        --smip-csv data/scenariomip_cmip7/emissions_1750-2500.csv \\
        --classification-sci outputs/classification_per_model.csv \\
        --classification-smip outputs/classification_per_model_scenariomip.csv \\
        --gw-source magicc \\
        --output-dir outputs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ar7_ch5.archetype_features import (
    load_and_compute_sci,
    load_and_compute_smip,
    load_and_compute_ssp2com,
)
from ar7_ch5.archetypes import select_archetypes
from ar7_ch5.clustering import fit_clusters
from ar7_ch5.runners import repo_root


def _default_path(rel: str) -> Path:
    return repo_root() / rel


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute emissions archetype features, clusters and representatives.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--sci-xlsx",
        type=Path,
        default=None,
        help="Path to SCI xlsx (default: auto-discovered under data/SCI/).",
    )
    p.add_argument(
        "--smip-csv",
        type=Path,
        default=None,
        help="Path to ScenarioMIP emissions CSV.",
    )
    p.add_argument(
        "--ssp2com-xlsx",
        type=Path,
        default=None,
        help="Path to SSP2-COM world-total xlsx (default: data/ssp2com/ssp2-com_world_total.xlsx).",
    )
    p.add_argument(
        "--classification-sci",
        type=Path,
        default=None,
        help="Per-model classification CSV for SCI (outputs/classification_per_model.csv).",
    )
    p.add_argument(
        "--classification-smip",
        type=Path,
        default=None,
        help="Per-model classification CSV for ScenarioMIP (outputs/classification_per_model_scenariomip.csv).",
    )
    p.add_argument(
        "--classification-ssp2com",
        type=Path,
        default=None,
        help="Per-model classification CSV for SSP2-COM (outputs/classification_per_model_ssp2com.csv).",
    )
    p.add_argument(
        "--gw-source",
        choices=["fair", "ciceroscm", "magicc"],
        default="magicc",
        help="Which SCM's GW labels to use for archetype selection.",
    )
    p.add_argument(
        "--scheme",
        type=Path,
        default=None,
        help="Path to clustered.json scheme (default: schemes/clustered.json).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output CSVs (default: outputs/).",
    )
    p.add_argument(
        "--vetted-only",
        action="store_true",
        default=True,
        help="Restrict SCI feature extraction to vetted pathways only (default: True).",
    )
    p.add_argument(
        "--all-sci",
        action="store_true",
        default=False,
        help="Include all SCI pathways (not just vetted).",
    )
    return p.parse_args()


def _resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    root = repo_root()

    sci_xlsx = args.sci_xlsx
    if sci_xlsx is None:
        candidates = sorted((root / "data" / "SCI").glob("*.xlsx"))
        if not candidates:
            print(
                "ERROR: no SCI xlsx found under data/SCI/. "
                "Pass --sci-xlsx explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
        sci_xlsx = candidates[0]

    smip_csv = args.smip_csv or root / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
    clf_sci = args.classification_sci or root / "outputs" / "classification_per_model.csv"
    clf_smip = args.classification_smip or root / "outputs" / "classification_per_model_scenariomip.csv"
    scheme_path = args.scheme or root / "schemes" / "clustered.json"
    output_dir = args.output_dir or root / "outputs"
    ssp2com_xlsx = args.ssp2com_xlsx or root / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"
    clf_ssp2com = (
        args.classification_ssp2com
        or root / "outputs" / "classification_per_model_ssp2com.csv"
    )

    for label, path in [
        ("--sci-xlsx", sci_xlsx),
        ("--smip-csv", smip_csv),
        ("--classification-sci", clf_sci),
        ("--classification-smip", clf_smip),
        ("--scheme", scheme_path),
    ]:
        if not path.exists():
            print(f"ERROR: {label} path not found: {path}", file=sys.stderr)
            sys.exit(1)

    return {
        "sci_xlsx": sci_xlsx,
        "smip_csv": smip_csv,
        "clf_sci": clf_sci,
        "clf_smip": clf_smip,
        "scheme": scheme_path,
        "output_dir": output_dir,
        "ssp2com_xlsx": ssp2com_xlsx,
        "clf_ssp2com": clf_ssp2com,
    }


def main() -> None:
    args = _parse_args()
    paths = _resolve_paths(args)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    vetted_only = not args.all_sci

    # ---- 1. Feature extraction ----
    print("Computing SCI features ...", flush=True)
    clf_sci_for_vetted = paths["clf_sci"] if vetted_only else None
    sci_features = load_and_compute_sci(
        paths["sci_xlsx"],
        vetted_only=vetted_only,
        classification_csv=clf_sci_for_vetted,
    )
    print(f"  SCI: {len(sci_features)} pathways", flush=True)

    print("Computing ScenarioMIP features ...", flush=True)
    smip_features = load_and_compute_smip(paths["smip_csv"])
    print(f"  ScenarioMIP: {len(smip_features)} pathways", flush=True)

    import pandas as pd

    # SSP2-COM is a single reference pathway; include it when the xlsx is present.
    ssp2com_xlsx = paths.get("ssp2com_xlsx")
    if ssp2com_xlsx is not None and ssp2com_xlsx.exists():
        print("Computing SSP2-COM features ...", flush=True)
        ssp2com_features = load_and_compute_ssp2com(ssp2com_xlsx)
        print(f"  SSP2-COM: {len(ssp2com_features)} pathway(s)", flush=True)
        reference_features = pd.concat(
            [smip_features, ssp2com_features], ignore_index=True
        )
    else:
        print("  (SSP2-COM xlsx not found; skipping)", flush=True)
        reference_features = smip_features

    # Save feature CSV
    features_path = paths["output_dir"] / "archetype_features.csv"
    pd.concat([sci_features, reference_features], ignore_index=True).to_csv(
        features_path, index=False
    )
    print(f"  → {features_path}", flush=True)

    # ---- 2. Clustering ----
    scheme = json.loads(paths["scheme"].read_text())
    print("Clustering ...", flush=True)
    clustered = fit_clusters(sci_features, reference_features, scheme)
    print(f"  {clustered['cluster_label'].nunique()} strategy clusters found", flush=True)

    clusters_path = paths["output_dir"] / "clusters.csv"
    clustered.to_csv(clusters_path, index=False)
    print(f"  → {clusters_path}", flush=True)

    # ---- 3. Archetype selection ----
    print(f"Selecting archetypes (gw-source={args.gw_source}) ...", flush=True)
    reference_clf = {"smip": paths["clf_smip"]}
    if paths.get("clf_ssp2com") and paths["clf_ssp2com"].exists():
        reference_clf["ssp2com"] = paths["clf_ssp2com"]
    archetypes = select_archetypes(
        clustered,
        classification_csv=paths["clf_sci"],
        gw_source=args.gw_source,
        reference_classification_csvs=reference_clf,
    )
    print(f"  {len(archetypes)} archetype cells populated", flush=True)

    archetypes_path = paths["output_dir"] / "archetypes.csv"
    archetypes.to_csv(archetypes_path, index=False)
    print(f"  → {archetypes_path}", flush=True)

    # Summary
    n_ref = archetypes["source"].isin(["smip", "ssp2com"]).sum()
    n_sci = (archetypes["source"] == "sci").sum()
    print(f"\nDone.  {n_ref} reference + {n_sci} SCI archetypes selected.")


if __name__ == "__main__":
    main()
