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

from ar7_ch5.experiments.rcmip3 import run_rcmip3
from ar7_ch5.experiments.scenariomip_cmip7 import run_scenariomip
from ar7_ch5.experiments.sci_ensemble import run_sci_batch
from ar7_ch5.experiments.ssp2com import run_ssp2com
from ar7_ch5.harmonise import DEFAULT_ANCHOR_YEAR, DEFAULT_CONVERGENCE_YEAR
from ar7_ch5.load import available_sci_scenarios, load_sci_infilled
from ar7_ch5.load_rcmip3 import DEFAULT_DIAGNOSTICS as RCMIP3_DIAGNOSTICS
from ar7_ch5.load_scenariomip import SCENARIOS as SCENARIOMIP_SCENARIOS
from ar7_ch5.runners import DEFAULT_MAX_WORKERS, repo_root
from ar7_ch5.runners.orchestrate import run_models

EXPERIMENTS = ["sci", "scenariomip_cmip7", "ssp2com", "rcmip3"]
MODELS = ["fair", "ciceroscm", "magicc"]

DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)
DEFAULT_SSP2COM_XLSX = (
    repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"
)
DEFAULT_SCENARIOMIP_CSV = (
    repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
)
DEFAULT_RCMIP3_BUNDLE = repo_root() / "data" / "rcmip3_protocol"
# Where the global history anchor lives on NAC. Other machines should set
# AR7_HARMONISATION_HISTORY or pass --history explicitly.
DEFAULT_HARMONISATION_HISTORY = Path(
    "/storage/no-backup-nac/users/bensan/emissions_harmonization_historical/"
    "data/processed/history-for-harmonisation/zenodo_17845154/db"
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
        default=None,
        help="Path to the input file or directory. Defaults are experiment-"
        "specific: for 'sci' the SCI ensemble xlsx (data/SCI/...), for "
        "'ssp2com' the world-total xlsx (data/ssp2com/...), for "
        "'scenariomip_cmip7' the FaIR-inputs emissions CSV "
        "(data/scenariomip_cmip7/...), for 'rcmip3' the RCMIP3 protocol "
        "bundle directory (data/rcmip3_protocol/).",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=None,
        help="Path to the global history anchor (sharded feather dir from "
        "emissions-harmonisation-historical Zenodo 17845154). Only used by "
        "--experiment ssp2com. Default: AR7_HARMONISATION_HISTORY env var, "
        "else the NAC staged location.",
    )
    parser.add_argument(
        "--anchor-year",
        type=int,
        default=DEFAULT_ANCHOR_YEAR,
        help=(
            "Harmonisation anchor year (ssp2com only). "
            f"Default {DEFAULT_ANCHOR_YEAR}."
        ),
    )
    parser.add_argument(
        "--convergence-year",
        type=int,
        default=DEFAULT_CONVERGENCE_YEAR,
        help=f"Harmonisation correction tapers to zero by this year (ssp2com only). "
        f"Default {DEFAULT_CONVERGENCE_YEAR}.",
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
        "--end-year",
        type=int,
        default=None,
        help="Upper bound on the input emissions year axis. The "
        "scenariomip_cmip7 and ssp2com loaders default to 2100; pass "
        "2300 or 2500 here to feed the SCMs the full long-tail "
        "extension period (the GMD ScenarioMIP CMIP7 CSV carries data "
        "to 2500). Has no effect for the sci and rcmip3 experiments.",
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

    if args.experiment == "ssp2com":
        return _run_ssp2com(args)

    if args.experiment == "scenariomip_cmip7":
        return _run_scenariomip(args)

    if args.experiment == "rcmip3":
        return _run_rcmip3(args)

    if args.experiment != "sci":
        raise SystemExit(
            f"experiment={args.experiment!r} is not wired yet "
            "(see ar7-ch5-ensemble-brief.md)."
        )

    # Fall through to the SCI path.
    if args.input is None:
        args.input = DEFAULT_SCI_XLSX

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


def _run_rcmip3(args) -> int:
    """Run RCMIP3 concentration-driven scenarios through SCMs that support it."""
    bundle = args.input or DEFAULT_RCMIP3_BUNDLE
    out_dir = Path(args.output) / "rcmip3"
    n_members = 200 if args.n_members is None else args.n_members
    scenarios = (
        [args.scenario] if args.scenario is not None
        else list(RCMIP3_DIAGNOSTICS)
    )
    print(
        f"Running RCMIP3 ({scenarios}) through {args.models} (filtered to "
        f"concentration-driven-capable adapters) at n_members={n_members} "
        f"-> {out_dir}."
    )
    result = run_rcmip3(
        bundle,
        models=args.models,
        scenarios=scenarios,
        n_members=n_members,
        output_dir=out_dir,
        max_workers=args.max_workers,
    )
    _report_gsat(result)
    return 0


def _run_scenariomip(args) -> int:
    """Run the seven ScenarioMIP CMIP7 baseline scenarios through ``--models``."""
    csv = args.input or DEFAULT_SCENARIOMIP_CSV
    out_dir = Path(args.output) / "scenariomip_cmip7"
    n_members = 200 if args.n_members is None else args.n_members
    # --scenario can pin to a subset; reuses the existing SCI flag.
    scenarios = (
        [args.scenario] if args.scenario is not None
        else list(SCENARIOMIP_SCENARIOS)
    )
    print(
        f"Running ScenarioMIP CMIP7 ({scenarios}) through {args.models} at "
        f"n_members={n_members} -> {out_dir} (one NetCDF per (scenario, SCM))."
    )
    end_year = 2100 if args.end_year is None else args.end_year
    result = run_scenariomip(
        csv,
        models=args.models,
        scenarios=scenarios,
        n_members=n_members,
        output_dir=out_dir,
        max_workers=args.max_workers,
        end_year=end_year,
    )
    _report_gsat(result)
    return 0


def _run_ssp2com(args) -> int:
    """Run the SSP2-COM world-total pathway through the chosen models."""
    import os

    xlsx = args.input or DEFAULT_SSP2COM_XLSX
    history = args.history or Path(
        os.environ.get(
            "AR7_HARMONISATION_HISTORY", DEFAULT_HARMONISATION_HISTORY,
        )
    )

    out_dir = Path(args.output) / "ssp2com"
    n_members = 200 if args.n_members is None else args.n_members
    print(
        f"Running SSP2-COM through {args.models} at n_members={n_members} "
        f"-> {out_dir} (one NetCDF per SCM)."
    )

    result = run_ssp2com(
        xlsx, history,
        models=args.models,
        n_members=n_members,
        output_dir=out_dir,
        max_workers=args.max_workers,
        anchor_year=args.anchor_year,
        convergence_year=args.convergence_year,
    )
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
