"""Report which SCM ensemble outputs are already cached on disk.

Read-only; never re-runs anything. Each missing entry includes the exact
``run_scenarios.py`` invocation that produces it -- chapter authors can
copy / paste rather than reconstruct.

    pixi run python scripts/cache_status.py
    pixi run python scripts/cache_status.py --output outputs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ar7_ch5.cache import format_report, status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs"),
        help="Root of the per-experiment SCM output tree (default: outputs/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entries = status(args.output)
    missing = sum(e.missing for e in entries)
    print(format_report(entries))
    print()
    if missing == 0:
        print("All expected ensemble outputs and classification CSVs are present.")
    else:
        print(f"Total missing: {missing} file(s) / CSV(s).")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
