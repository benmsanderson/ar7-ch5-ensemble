"""Harmonise + infill an ensemble of raw IAM emissions and cache the result.

Drives the chapter-owned harmonise+infill pipeline
(:mod:`ar7_ch5.harmonisation`) on a chosen scenario set, writing the result
to a parquet cache the runners read at scenario load time.

Usage
-----

    pixi run python scripts/harmonise.py --ensemble sci
    pixi run python scripts/harmonise.py --ensemble sci --limit 5  # quick run
    pixi run python scripts/harmonise.py --ensemble sci \
        --input data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx \
        --output data/SCI/cache/sci_harmonised_infilled.parquet

Only ``--ensemble sci`` is wired today; ``scenariomip-cmip7`` and
``ssp2com`` are added in the next commit (raw IAMC loaders for those two
sources are still to come).

The script never overwrites an existing cache silently. Pass
``--refresh`` to re-run when the source has changed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from ar7_ch5.cmip7_inputs import (
    DEFAULT_GHG_INVERSIONS_FILE,
    DEFAULT_HISTORY_FILE,
    DEFAULT_INFILLING_DB_FILE,
    DEFAULT_OVERRIDES_FILE,
)
from ar7_ch5.harmonisation import (
    DEFAULT_ANNUAL_END_YEAR,
    DEFAULT_ANNUAL_START_YEAR,
    DEFAULT_HARMONISATION_YEAR,
    DEFAULT_PRE_INDUSTRIAL_YEAR,
    HarmonisationConfig,
    harmonise_and_infill,
)
from ar7_ch5.load import load_sci_raw_iamc
from ar7_ch5.load_scenariomip import load_scenariomip_cmip7_raw_iamc
from ar7_ch5.load_ssp2com import load_ssp2com_raw_iamc
from ar7_ch5.runners import repo_root

SUPPORTED_ENSEMBLES = ("sci", "scenariomip-cmip7", "ssp2com")

_REPO = repo_root()
_DEFAULT_INPUTS: dict[str, Path] = {
    "sci": _REPO / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx",
    "scenariomip-cmip7": (
        _REPO / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
    ),
    "ssp2com": _REPO / "data" / "ssp2com" / "ssp2-com_world_total.xlsx",
}
_DEFAULT_OUTPUTS: dict[str, Path] = {
    "sci": _REPO / "data" / "SCI" / "cache" / "sci_harmonised_infilled.parquet",
    "scenariomip-cmip7": (
        _REPO
        / "data"
        / "scenariomip_cmip7"
        / "cache"
        / "scenariomip_cmip7_harmonised_infilled.parquet"
    ),
    "ssp2com": (
        _REPO / "data" / "ssp2com" / "cache" / "ssp2com_harmonised_infilled.parquet"
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ensemble",
        choices=SUPPORTED_ENSEMBLES,
        required=True,
        help="Which ensemble to harmonise.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Source emissions file (default: per-ensemble published source).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output parquet cache path (default: data/<ensemble>/cache/...).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N pathways (smoke / debug runs).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run even if the output cache exists.",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY_FILE,
        help="CMIP7 ScenarioMIP history CSV.",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DEFAULT_OVERRIDES_FILE,
        help="Aneris global overrides CSV.",
    )
    parser.add_argument(
        "--infilling-db",
        type=Path,
        default=DEFAULT_INFILLING_DB_FILE,
        help="CMIP7 ScenarioMIP infilling database CSV (Zenodo 20566343).",
    )
    parser.add_argument(
        "--ghg-inversions",
        type=Path,
        default=DEFAULT_GHG_INVERSIONS_FILE,
        help="Secondary minor-GHG inversion CSV.",
    )
    parser.add_argument(
        "--harmonisation-year",
        type=int,
        default=DEFAULT_HARMONISATION_YEAR,
        help="Anchor year for harmonisation (chapter default: 2023).",
    )
    parser.add_argument(
        "--pre-industrial-year",
        type=int,
        default=DEFAULT_PRE_INDUSTRIAL_YEAR,
        help="Pre-industrial reference year for the infiller (default: 1750).",
    )
    parser.add_argument(
        "--annual-start-year",
        type=int,
        default=DEFAULT_ANNUAL_START_YEAR,
        help="First year for the annual interpolation grid (default: 2010).",
    )
    parser.add_argument(
        "--annual-end-year",
        type=int,
        default=DEFAULT_ANNUAL_END_YEAR,
        help="Last year for the annual interpolation grid (default: 2100).",
    )
    parser.add_argument(
        "--n-processes",
        type=int,
        default=None,
        help="Worker processes for the Aneris harmoniser (default: capped autoselect).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Suppress harmoniser / infiller progress bars.",
    )
    parser.add_argument(
        "--no-checks",
        action="store_true",
        help="Skip the gcages input / output sanity checks (faster, less safe).",
    )
    parser.add_argument(
        "--check-hash",
        action="store_true",
        help=(
            "Enforce gcages's hash check on the chapter history file. "
            "Disabled by default because the history file is fetched / "
            "updated between FOD and SOD and the gcages hash registry "
            "lags upstream."
        ),
    )
    args = parser.parse_args(argv)

    input_path = args.input or _default_input_for(args.ensemble)
    output_path = args.output or _default_output_for(args.ensemble)

    if output_path.is_file() and not args.refresh:
        size_mb = output_path.stat().st_size / 1e6
        print(
            f"Output cache exists: {output_path} ({size_mb:.1f} MB). "
            "Pass --refresh to regenerate.",
            file=sys.stderr,
        )
        return 0

    if not input_path.is_file():
        print(
            f"Input emissions file not found: {input_path}. "
            "See docs/data_setup.md.",
            file=sys.stderr,
        )
        return 2

    print(f"[harmonise] ensemble={args.ensemble} input={input_path}")
    raw = _load_raw(args.ensemble, input_path)

    if args.limit is not None:
        raw = _slice_first_n_pathways(raw, args.limit)
        print(f"[harmonise] limit={args.limit} -> {len(raw):,} rows")

    drops_sidecar_path = output_path.with_name(
        output_path.stem + ".dropped.csv"
    )
    cfg = HarmonisationConfig(
        history_path=args.history,
        overrides_path=args.overrides,
        infilling_db_path=args.infilling_db,
        ghg_inversions_path=args.ghg_inversions,
        harmonisation_year=args.harmonisation_year,
        pre_industrial_year=args.pre_industrial_year,
        annual_start_year=args.annual_start_year,
        annual_end_year=args.annual_end_year,
        progress=not args.no_progress,
        run_checks=not args.no_checks,
        check_hash=args.check_hash,
        n_processes=args.n_processes,
        drops_sidecar_path=drops_sidecar_path,
    )
    t0 = time.perf_counter()
    out = harmonise_and_infill(raw, config=cfg)
    elapsed = time.perf_counter() - t0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, compression="gzip")
    size_mb = output_path.stat().st_size / 1e6
    pathways = out.index.droplevel(["region", "variable", "unit"]).nunique()
    print(
        f"[harmonise] wrote {len(out):,} rows x {len(out.columns)} cols "
        f"({pathways:,} pathways, {size_mb:.1f} MB) to {output_path} "
        f"in {elapsed:.1f}s."
    )
    if drops_sidecar_path.is_file():
        with drops_sidecar_path.open() as fh:
            drop_lines = max(sum(1 for _ in fh) - 1, 0)
        print(
            f"[harmonise] drops sidecar: {drops_sidecar_path} "
            f"({drop_lines:,} drop entries)."
        )
    return 0


def _default_input_for(ensemble: str) -> Path:
    return _DEFAULT_INPUTS[ensemble]


def _default_output_for(ensemble: str) -> Path:
    return _DEFAULT_OUTPUTS[ensemble]


def _load_raw(ensemble: str, path: Path) -> pd.DataFrame:
    if ensemble == "sci":
        return load_sci_raw_iamc(path)
    if ensemble == "scenariomip-cmip7":
        return load_scenariomip_cmip7_raw_iamc(path)
    if ensemble == "ssp2com":
        return load_ssp2com_raw_iamc(path)
    raise ValueError(f"Unsupported ensemble: {ensemble}")


def _slice_first_n_pathways(raw: pd.DataFrame, n: int) -> pd.DataFrame:
    """Return rows belonging to the first ``n`` ``(model, scenario)`` pairs."""
    from pandas_openscm.indexing import multi_index_match

    pairs = list(raw.index.droplevel(["region", "variable", "unit"]).unique())[:n]
    return raw.loc[
        multi_index_match(
            raw.index,
            pd.MultiIndex.from_tuples(pairs, names=["model", "scenario"]),
        )
    ]


if __name__ == "__main__":
    sys.exit(main())
