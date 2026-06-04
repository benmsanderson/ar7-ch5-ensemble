"""Vet, feasibility-check, and classify SCI 2025 scenarios.

Canonical entry point for the M3 pipeline. Loads the SCI ensemble xlsx,
runs vetting (Table SI.1), feasibility (Table SI.2), sustainability, and
applies the GW0-GW8 warming classification (Riahi 2026 Table SI.3), then
writes a combined per-scenario CSV.

Two warming sources are supported:

* ``--source xlsx`` (default): classify off the MAGICC v7.5.3 percentile
  timeseries baked into the SCI xlsx. This is the regression path; matches
  scenariocompass exactly.
* ``--source per_model`` or ``--source pooled``: classify off our own
  3-SCM ensemble outputs (FaIR + CICERO + MAGICC), via
  :mod:`ar7_ch5.metrics`. Requires the per-pathway NetCDFs under
  ``--outputs-dir``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from ar7_ch5.classification import (
    GW_ORDER,
    classify_from_metrics,
    classify_warming,
)
from ar7_ch5.feasibility import apply_feasibility, apply_sustainability
from ar7_ch5.load import load_sci_iamc_global
from ar7_ch5.metrics import warming_metrics_from_outputs
from ar7_ch5.runners import repo_root
from ar7_ch5.vetting import apply_vetting

DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)

SOURCES = ("xlsx", "per_model", "pooled")
SCM_MODELS = ("fair", "ciceroscm", "magicc")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SCI_XLSX,
        help=f"SCI ensemble xlsx (default: {DEFAULT_SCI_XLSX}).",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="xlsx",
        help="Warming source for classification. 'xlsx' uses the MAGICC "
        "percentiles baked into the SCI xlsx (regression path). "
        "'per_model' / 'pooled' use our 3-SCM ensemble NetCDFs.",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path("outputs/sci"),
        help="Root of the per-SCM NetCDF tree (used when --source is "
        "per_model or pooled). Default: outputs/sci.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(SCM_MODELS),
        choices=SCM_MODELS,
        help="SCMs to combine when --source is per_model or pooled (default: all three).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/classification.csv"),
        help="Output CSV path.",
    )
    return parser


def _classify_from_xlsx(df: pd.DataFrame) -> pd.DataFrame:
    """Vetting + feasibility + sustainability + classification (xlsx path)."""
    print(f"Loaded {len(df['Model'].unique())} IAMs across "
          f"{len(df[['Model','Scenario']].drop_duplicates())} scenarios.")

    print("Vetting...")
    vetting = apply_vetting(df)
    vc = vetting["vetting_status"].value_counts().to_dict()
    print(f"  {vc}")

    print("Classification (MAGICC percentiles in xlsx)...")
    warming = classify_warming(df)
    cc = warming["category"].value_counts().reindex(GW_ORDER).dropna().astype(int).to_dict()
    print(f"  {cc}")

    vetted_pairs = vetting.loc[
        vetting["vetting_status"] == "passed", ["Model", "Scenario"]
    ]
    vetted_df = df.merge(vetted_pairs, on=["Model", "Scenario"])

    print(f"Feasibility on {len(vetted_pairs)} vetted scenarios...")
    feas = apply_feasibility(vetted_df)
    sust = apply_sustainability(vetted_df)
    print(f"  feasibility:    {feas['worst_feasibility'].value_counts().to_dict()}")
    print(f"  sustainability: {sust['worst_sustainability'].value_counts().to_dict()}")

    return (
        vetting.merge(warming, on=["Model", "Scenario"], how="left")
        .merge(
            feas[["Model", "Scenario", "worst_feasibility"]],
            on=["Model", "Scenario"], how="left",
        )
        .merge(
            sust[["Model", "Scenario", "worst_sustainability"]],
            on=["Model", "Scenario"], how="left",
        )
    )


def _classify_from_metrics(df: pd.DataFrame, args) -> pd.DataFrame:
    """Vetting + feasibility + sustainability + classification (NC path)."""
    pairs = list(
        df[["Model", "Scenario"]].drop_duplicates().itertuples(index=False, name=None)
    )
    print(f"Loaded {len(df['Model'].unique())} IAMs across {len(pairs)} scenarios.")

    print("Vetting...")
    vetting = apply_vetting(df)
    vc = vetting["vetting_status"].value_counts().to_dict()
    print(f"  {vc}")

    print(
        f"Computing warming metrics from {args.outputs_dir} "
        f"(models={args.models}, source={args.source})..."
    )
    metrics = warming_metrics_from_outputs(
        pairs, models=args.models, outputs_dir=args.outputs_dir, source=args.source
    )
    warming = classify_from_metrics(metrics).reset_index()
    warming = warming.rename(columns={"model": "Model", "scenario": "Scenario"})

    cc = warming["category"].value_counts().reindex(GW_ORDER).dropna().astype(int).to_dict()
    print(f"  classification ({args.source}): {cc}")
    # Per-SCM breakdown surfaces the cross-model spread that the emissions-based
    # path is meant to expose; the headline `source` choice is a CLI flag, not
    # a hidden default, so this is the validation-earlier check on it.
    if args.source == "per_model" and "climate_model" in warming.columns:
        for cm, sub in warming.groupby("climate_model", observed=True):
            sub_cc = (
                sub["category"].value_counts().reindex(GW_ORDER).dropna().astype(int).to_dict()
            )
            print(f"    {cm}: {sub_cc}")

    vetted_pairs = vetting.loc[
        vetting["vetting_status"] == "passed", ["Model", "Scenario"]
    ]
    vetted_df = df.merge(vetted_pairs, on=["Model", "Scenario"])

    print(f"Feasibility on {len(vetted_pairs)} vetted scenarios...")
    feas = apply_feasibility(vetted_df)
    sust = apply_sustainability(vetted_df)
    print(f"  feasibility:    {feas['worst_feasibility'].value_counts().to_dict()}")
    print(f"  sustainability: {sust['worst_sustainability'].value_counts().to_dict()}")

    return (
        vetting.merge(warming, on=["Model", "Scenario"], how="left")
        .merge(
            feas[["Model", "Scenario", "worst_feasibility"]],
            on=["Model", "Scenario"], how="left",
        )
        .merge(
            sust[["Model", "Scenario", "worst_sustainability"]],
            on=["Model", "Scenario"], how="left",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print(f"Loading {args.input.name}...")
    df = load_sci_iamc_global(args.input)

    if args.source == "xlsx":
        combined = _classify_from_xlsx(df)
    else:
        combined = _classify_from_metrics(df, args)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(combined)} rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
