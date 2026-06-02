"""Archive the SCI 2025 ensemble xlsx to a fast local CSV cache.

The published SCI input is a ~120 MB xlsx that openpyxl takes minutes to parse.
This command parses it once and writes a CSV cache (under data/SCI/cache/,
gitignored) that the loaders reuse on every subsequent run. The loaders also
build this cache lazily on first read; run this to refresh it explicitly after
dropping in a new SCI version. See docs/data_setup.md for how to obtain the xlsx.

    pixi run python scripts/preprocess_sci.py            # default SCI path
    pixi run python scripts/preprocess_sci.py --input <path> --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ar7_ch5.load import load_sci_data_sheet
from ar7_ch5.runners import repo_root

DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SCI_XLSX,
        help="Path to the SCI ensemble xlsx (default: data/SCI/...).",
    )
    parser.add_argument(
        "--sheet",
        default="data",
        help="Worksheet to archive (default: data).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-parse the xlsx even if an up-to-date cache exists.",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        raise SystemExit(
            f"SCI xlsx not found: {args.input}. See docs/data_setup.md for how "
            "to obtain it."
        )

    df = load_sci_data_sheet(args.input, sheet=args.sheet, refresh=args.refresh)
    cache = args.input.parent / "cache" / f"{args.input.stem}.{args.sheet}.csv"
    size_mb = cache.stat().st_size / 1e6 if cache.is_file() else 0.0
    print(
        f"Cached {len(df):,} rows x {len(df.columns)} cols -> {cache} "
        f"({size_mb:.1f} MB)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
