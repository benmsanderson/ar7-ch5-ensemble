"""Run scenario sets through the simple climate models.

Single canonical entry point for SCM runs. Select an experiment and the models
to run, e.g.:

    pixi run python scripts/run_scenarios.py \
        --experiment sci --models fair ciceroscm magicc

Milestone 2 wires the ``sci`` experiment: one SCI pathway driven through the
chosen models on a small ensemble (``--n-members``). The other input sets and
the chunked full-product writer are later milestones (see
ar7-ch5-ensemble-brief.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ar7_ch5.load import available_sci_scenarios, load_sci_infilled
from ar7_ch5.runners import repo_root
from ar7_ch5.runners.orchestrate import run_models

EXPERIMENTS = ["sci", "scenariomip_cmip7", "ssp2com", "rcmip3"]
MODELS = ["fair", "ciceroscm", "magicc"]

DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment",
        required=True,
        choices=EXPERIMENTS,
        help="Which input set to run.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODELS,
        choices=MODELS,
        help="Which simple climate models to run (default: all three).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SCI_XLSX,
        help="Path to the SCI ensemble xlsx (default: data/SCI/...).",
    )
    parser.add_argument(
        "--iam",
        default=None,
        help="SCI model (IAM) name. Default: first available pair.",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="SCI scenario name. Default: first available pair.",
    )
    parser.add_argument(
        "--n-members",
        type=int,
        default=None,
        help="Ensemble members per model (smoke test: a small number). "
        "Default: full posterior/drawnset.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available (model, scenario) pairs and exit.",
    )
    parser.add_argument(
        "--output",
        default="outputs",
        help="Directory for run output (gitignored).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.experiment != "sci":
        raise SystemExit(
            f"experiment={args.experiment!r} is not wired yet; only 'sci' runs "
            "in milestone 2 (see ar7-ch5-ensemble-brief.md)."
        )

    if args.list:
        for iam, scenario in available_sci_scenarios(args.input):
            print(f"{iam}\t{scenario}")
        return 0

    iam, scenario = args.iam, args.scenario
    if iam is None or scenario is None:
        iam, scenario = available_sci_scenarios(args.input)[0]
        print(f"No scenario selected; using first pair: {iam!r} / {scenario!r}")

    scenarios = load_sci_infilled(args.input, scenario=scenario, model=iam)
    print(
        f"Loaded {iam!r} / {scenario!r}: "
        f"{len(scenarios.get_unique_meta('variable'))} species, "
        f"{scenarios['year'].min()}-{scenarios['year'].max()}."
    )

    result = run_models(scenarios, args.models, n_members=args.n_members)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sci_{iam}_{scenario}.csv".replace("/", "-").replace(
        " ", "-"
    )
    result.to_csv(out_path)
    print(f"Wrote {out_path}")

    _report_gsat(result)
    return 0


def _report_gsat(result) -> None:
    """Print 2100 GSAT spread across members per model, for a sanity check."""
    gsat = result.filter(
        variable="Surface Air Temperature Change", region="World", year=2100
    )
    if gsat.empty:
        print("No GSAT in output to summarise.")
        return
    for model in sorted(gsat.get_unique_meta("climate_model")):
        values = gsat.filter(climate_model=model).values.ravel()
        print(
            f"  {model}: GSAT_2100 = {values.mean():.3f} K "
            f"[{values.min():.3f}, {values.max():.3f}] (n={values.size})"
        )


if __name__ == "__main__":
    sys.exit(main())
