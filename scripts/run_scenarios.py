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

from ar7_ch5.experiments.sci_ensemble import run_sci_batch
from ar7_ch5.load import available_sci_scenarios, load_sci_infilled
from ar7_ch5.runners import DEFAULT_MAX_WORKERS, repo_root
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
        "--all",
        action="store_true",
        help="Run the full SCI ensemble (every pathway), writing one NetCDF "
        "per pathway. Resumable: re-running skips pathways already written. "
        "Default --n-members for this mode is 200.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="With --all, re-run and overwrite pathways already on disk.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="With --all, process at most this many pathways (partial pass).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Worker-process cap per model run (CICERO-SCM, MAGICC). Models run "
        f"one at a time, so this is the total concurrency. Default "
        f"{DEFAULT_MAX_WORKERS}.",
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

    if args.all:
        return _run_batch(args)

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

    result = run_models(
        scenarios,
        args.models,
        n_members=args.n_members,
        max_workers=args.max_workers,
    )

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sci_{iam}_{scenario}.csv".replace("/", "-").replace(
        " ", "-"
    )
    result.to_csv(out_path)
    print(f"Wrote {out_path}")

    _report_gsat(result)
    return 0


def _run_batch(args) -> int:
    """Run the full SCI ensemble, one NetCDF per pathway (milestone 4)."""
    n_members = 200 if args.n_members is None else args.n_members
    out_dir = Path(args.output) / "sci"
    print(
        f"Running SCI ensemble through {args.models} at n_members={n_members} "
        f"-> {out_dir} (one NetCDF per pathway, resumable)."
    )
    results = run_sci_batch(
        args.input,
        args.models,
        n_members=n_members,
        output_dir=out_dir,
        overwrite=args.overwrite,
        limit=args.limit,
        max_workers=args.max_workers,
    )
    written = sum(r.status == "written" for r in results)
    skipped = sum(r.status == "skipped" for r in results)
    failed = [r for r in results if r.status == "failed"]
    print(
        f"Done: {written} written, {skipped} skipped, {len(failed)} failed "
        f"({len(results)} pathways). Manifest: {out_dir / 'manifest.csv'}."
    )
    for r in failed:
        print(f"  FAILED {r.scm} {r.iam}/{r.scenario}: {r.error}")
    return 1 if failed else 0


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
