"""Vet, feasibility-check, and classify scenarios.

Canonical entry point for the M3 classification pipeline. Two orthogonal
axes select what to classify and how:

``--input-source`` (what to classify):

* ``sci`` (default) -- SCI 2025 ensemble (~1599 IAM pathways). The full
  M3 pipeline runs: vetting (Table SI.1), feasibility (Table SI.2),
  sustainability, plus GW0-GW8 warming classification (Table SI.3).
* ``scenariomip`` -- ScenarioMIP CMIP7 baselines (VL/L/LN/M/ML/H/HL).
  Classification only; vetting / feasibility / sustainability don't
  apply (these are not IAM pathways).
* ``ssp2com`` -- SSP2-COM world-total. Classification only.

``--source`` (how to derive warming):

* ``xlsx`` (default for ``--input-source sci``): classify off the MAGICC
  v7.5.3 percentile timeseries baked into the SCI xlsx. Regression path;
  matches scenariocompass exactly. Only valid with ``--input-source sci``.
* ``per_model`` -- classify off the chapter's 3-SCM ensemble NetCDFs
  with one row per (model, pathway, climate_model). The headline path
  for the chapter's emissions-based classification (per
  ``project_classification_warming_contract`` memory).
* ``pooled`` -- classify off the 3-SCM ensemble with quantiles taken
  across the union of all SCMs' members.

Output CSV is written to ``outputs/classification_<source>_<input>.csv``
when ``--input-source`` is non-SCI, and to
``outputs/classification_<source>.csv`` for SCI to preserve backward
compatibility with the existing fig01 cache key.
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
    load_gw_scheme,
)
from ar7_ch5.feasibility import apply_feasibility, apply_sustainability
from ar7_ch5.load import load_sci_iamc_global
from ar7_ch5.load_scenariomip import SCENARIOS as SCENARIOMIP_PATHWAYS
from ar7_ch5.load_ssp2com import SSP2COM_PATHWAY_ID
from ar7_ch5.metrics import warming_metrics_from_outputs
from ar7_ch5.runners import repo_root
from ar7_ch5.vetting import apply_vetting

DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)

SOURCES = ("xlsx", "per_model", "pooled")
INPUT_SOURCES = ("sci", "scenariomip", "ssp2com")
SCM_MODELS = ("fair", "ciceroscm", "magicc")

# Per-input-source defaults for `--outputs-dir` (the per-experiment
# NetCDF tree the runners write under).
DEFAULT_OUTPUTS_DIR = {
    "sci":         Path("outputs/sci"),
    "scenariomip": Path("outputs/scenariomip_cmip7"),
    "ssp2com":     Path("outputs/ssp2com"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SCI_XLSX,
        help=f"SCI ensemble xlsx (default: {DEFAULT_SCI_XLSX}). "
        "Only used when --input-source is sci (for vetting / feasibility / "
        "the MAGICC-percentiles regression path).",
    )
    parser.add_argument(
        "--input-source",
        choices=INPUT_SOURCES,
        default="sci",
        help="Which input set to classify: 'sci' (SCI ensemble; runs full "
        "vetting + feasibility + classification), 'scenariomip' (ScenarioMIP "
        "CMIP7 baselines; classification only), or 'ssp2com' (SSP2-COM "
        "world-total; classification only). Default: sci.",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="xlsx",
        help="Warming source for classification. 'xlsx' uses the MAGICC "
        "percentiles baked into the SCI xlsx (regression path; only valid "
        "with --input-source sci). 'per_model' / 'pooled' use the chapter's "
        "3-SCM ensemble NetCDFs.",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=None,
        help="Root of the per-SCM NetCDF tree (used when --source is "
        "per_model or pooled). Default picks the per-input-source path "
        "(outputs/sci for sci; outputs/scenariomip_cmip7 for scenariomip; "
        "outputs/ssp2com for ssp2com).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(SCM_MODELS),
        choices=SCM_MODELS,
        help=(
            "SCMs to combine when --source is per_model or pooled "
            "(default: all three)."
        ),
    )
    parser.add_argument(
        "--gw-scheme",
        default="si3",
        help="Warming-classification scheme: a bare name resolved under "
        "schemes/gw/ (e.g. 'si3', the canonical Table SI.3 taxonomy) or an "
        "explicit .json path. Lets alternative GW taxonomies be swapped in "
        "during writing.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path. Default: outputs/classification_<source>.csv "
        "(picked up by the figure layer via ar7_ch5.cache).",
    )
    return parser


def _classify_from_xlsx(df: pd.DataFrame, scheme=None) -> pd.DataFrame:
    """Vetting + feasibility + sustainability + classification (xlsx path)."""
    print(f"Loaded {len(df['Model'].unique())} IAMs across "
          f"{len(df[['Model','Scenario']].drop_duplicates())} scenarios.")

    print("Vetting...")
    vetting = apply_vetting(df)
    vc = vetting["vetting_status"].value_counts().to_dict()
    print(f"  {vc}")

    print("Classification (MAGICC percentiles in xlsx)...")
    warming = classify_warming(df, scheme=scheme)
    cc = (
        warming["category"].value_counts()
        .reindex(GW_ORDER).dropna().astype(int).to_dict()
    )
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


def _enumerate_pathways(input_source: str) -> list[tuple[str | None, str]]:
    """``(iam, pathway_id)`` pairs for non-SCI input sources.

    Vetting / feasibility / sustainability don't apply -- these aren't IAM
    pathways. For SCI the existing ``_classify_from_metrics`` enumerates
    from the IAMC frame directly.
    """
    if input_source == "scenariomip":
        return [(None, p) for p in SCENARIOMIP_PATHWAYS]
    if input_source == "ssp2com":
        return [(None, SSP2COM_PATHWAY_ID)]
    raise ValueError(
        f"unexpected non-SCI input_source={input_source!r}"
    )


def _classify_non_sci(args) -> pd.DataFrame:
    """Classification-only path for ScenarioMIP CMIP7 / SSP2-COM.

    No vetting / feasibility / sustainability columns because these
    aren't IAM scenarios. Output is a flat per-(pathway, climate_model)
    DataFrame with the warming metrics and GW0-GW8 category.
    """
    pathways = _enumerate_pathways(args.input_source)
    print(
        f"--input-source {args.input_source}: classifying "
        f"{len(pathways)} pathway(s) from {args.outputs_dir} "
        f"(models={args.models}, source={args.source})..."
    )
    metrics = warming_metrics_from_outputs(
        pathways,
        models=args.models,
        outputs_dir=args.outputs_dir,
        source=args.source,
        input_source=args.input_source,
    )
    warming = classify_from_metrics(metrics, scheme=getattr(args, "gw_scheme_obj", None)).reset_index()
    warming = warming.rename(columns={"model": "Model", "scenario": "Scenario"})
    # ``Model`` carries the input_source name on this path (see
    # ``metrics.load_pathway_outputs``); the real chapter identity is
    # ``pathway_id``. Surface ``pathway_id`` as ``Scenario`` so the
    # output schema matches the SCI CSV exactly.
    if "pathway_id" in warming.columns:
        warming["Scenario"] = warming["pathway_id"]
        warming = warming.drop(columns=["pathway_id"])
    cc = (
        warming["category"].value_counts()
        .reindex(GW_ORDER).dropna().astype(int).to_dict()
    )
    print(f"  classification ({args.source}, {args.input_source}): {cc}")
    if args.source == "per_model" and "climate_model" in warming.columns:
        for cm, sub in warming.groupby("climate_model", observed=True):
            sub_cc = (
                sub["category"].value_counts().reindex(GW_ORDER)
                .dropna().astype(int).to_dict()
            )
            print(f"    {cm}: {sub_cc}")
    return warming


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
        pairs,
        models=args.models,
        outputs_dir=args.outputs_dir,
        source=args.source,
        input_source=args.input_source,
    )
    warming = classify_from_metrics(metrics, scheme=getattr(args, "gw_scheme_obj", None)).reset_index()
    # Metrics index uses (model, pathway_id, [climate_model]); the rest of
    # the M3 pipeline expects (Model, Scenario) IAMC casing.
    warming = warming.rename(columns={"model": "Model", "pathway_id": "Scenario"})

    cc = (
        warming["category"].value_counts()
        .reindex(GW_ORDER).dropna().astype(int).to_dict()
    )
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
    args.gw_scheme_obj = load_gw_scheme(args.gw_scheme)
    print(f"GW scheme: {args.gw_scheme_obj.name} (--gw-scheme {args.gw_scheme})")
    if args.outputs_dir is None:
        args.outputs_dir = DEFAULT_OUTPUTS_DIR[args.input_source]
    if args.input_source != "sci" and args.source == "xlsx":
        raise SystemExit(
            f"--source xlsx is only valid with --input-source sci; "
            f"got --input-source {args.input_source}. Pass --source per_model "
            "(or --source pooled) to classify ScenarioMIP / SSP2-COM from "
            "the chapter ensemble NetCDFs."
        )
    if args.output is None:
        # SCI: keep the legacy ``classification_<source>.csv`` filename so
        # fig01 + cache keys don't have to change. Non-SCI: append the
        # input_source so the SCI and non-SCI outputs are distinct files.
        if args.input_source == "sci":
            args.output = Path(f"outputs/classification_{args.source}.csv")
        else:
            args.output = Path(
                f"outputs/classification_{args.source}_{args.input_source}.csv"
            )

    if args.input_source == "sci":
        print(f"Loading {args.input.name}...")
        df = load_sci_iamc_global(args.input)
        if args.source == "xlsx":
            combined = _classify_from_xlsx(df, scheme=args.gw_scheme_obj)
        else:
            combined = _classify_from_metrics(df, args)
    else:
        combined = _classify_non_sci(args)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(combined)} rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
