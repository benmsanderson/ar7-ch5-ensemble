"""Generate the Chapter 5 figures from cached SCM ensemble outputs.

Reads cached outputs only -- never re-runs the SCMs. If a required input
is missing :mod:`ar7_ch5.cache` reports it and the figure script raises a
clear ``FileNotFoundError`` pointing at the ``run_scenarios.py``
invocation that would generate it.

Each figure is a jupytext-paired ``notebooks/figXX_*.py`` cell script.
This dispatcher locates the script by figure id, executes it as a
subprocess in the same env so cell-level state stays clean, and reports
the output files it wrote.

    pixi run python scripts/make_figures.py --list
    pixi run python scripts/make_figures.py --figure fig01_classification
    pixi run python scripts/make_figures.py --all
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ar7_ch5.figures import load_figures
from ar7_ch5.runners import repo_root

NOTEBOOK_DIR = repo_root() / "notebooks"


def _script_path(figure_id: str) -> Path:
    """Resolve ``figure_id`` to its paired ``.py`` source."""
    target = NOTEBOOK_DIR / f"{figure_id}.py"
    if not target.is_file():
        raise FileNotFoundError(
            f"No script for figure {figure_id!r} at {target}. Each "
            "entry in schemes/figures.yaml needs a matching "
            "notebooks/<figure_id>.py."
        )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List figures registered in schemes/figures.yaml and exit.",
    )
    parser.add_argument(
        "--figure", action="append", default=[],
        help="Figure id to build. May be repeated.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Build every figure registered in schemes/figures.yaml.",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Override schemes/figures.yaml location.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    figures = (
        load_figures(args.config) if args.config is not None
        else load_figures()
    )

    if args.list:
        for fid, cfg in figures.items():
            title = cfg.get("title", "(no title)")
            print(f"  {fid:35s} {title}")
        return 0

    targets: list[str] = []
    if args.all:
        targets = list(figures.keys())
    targets += args.figure
    if not targets:
        raise SystemExit("Pass --list, --all, or one or more --figure ids.")

    unknown = [t for t in targets if t not in figures]
    if unknown:
        raise SystemExit(
            f"Unknown figure id(s): {unknown}. Known: {sorted(figures)}."
        )

    rc = 0
    for fid in targets:
        script = _script_path(fid)
        print(f"=== {fid} -> {script.relative_to(repo_root())} ===")
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=repo_root(),
        )
        if result.returncode != 0:
            print(f"  FAILED ({fid}, rc={result.returncode})")
            rc = result.returncode or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
