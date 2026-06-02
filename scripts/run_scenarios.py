"""Run scenario sets through the simple climate models.

Single canonical entry point for SCM runs. Select an experiment and the models
to run, e.g.:

    pixi run python scripts/run_scenarios.py \
        --experiment sci --models fair ciceroscm magicc

The run logic is implemented across milestones (smoke test, then SCI batch,
then the other input sets). This skeleton defines the intended interface.
"""

from __future__ import annotations

import argparse
import sys

EXPERIMENTS = ["sci", "scenariomip_cmip7", "ssp2com", "rcmip3"]
MODELS = ["fair", "ciceroscm", "magicc"]


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
        "--output",
        default="outputs",
        help="Directory for chunked run output (gitignored).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raise SystemExit(
        f"run_scenarios is not implemented yet (experiment={args.experiment}, "
        f"models={args.models}). The run pipeline is built in milestones 2-7; "
        f"see ar7-ch5-ensemble-brief.md."
    )


if __name__ == "__main__":
    sys.exit(main())
