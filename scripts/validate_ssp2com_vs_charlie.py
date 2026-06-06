"""Validate our harmonised SSP2-COM emissions against Charlie Koven's.

Loads both pipelines' SSP2-COM emissions and reports per-species relative
differences at 2025/2050/2075/2100, after explicitly separating species
where Charlie's pipeline falls back to the L scenario (his SSP2-COM CSV
doesn't carry every species; ours does, from the scenariocompass xlsx).
For "true overlap" species - where both pipelines genuinely used
SSP2-COM data - the residual differences reflect the harmonisation
method choice: he anchors pre-2023 to L scenario; we anchor at 2023 to
the published global history endpoint (Zenodo 17845154) with a linear
taper to 2050.

Writes ``outputs/ssp2com/validation_vs_charlie.csv`` (the full per-
(species, year) comparison) and prints a textual summary.

Usage::

    pixi run python scripts/validate_ssp2com_vs_charlie.py \\
        [--charlie-csv PATH] \\
        [--output PATH]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from ar7_ch5.harmonise import harmonise, load_history_anchor
from ar7_ch5.load_ssp2com import load_ssp2com_world_total
from ar7_ch5.runners import repo_root

# Default external paths. Both are on NAC; other machines override.
DEFAULT_SSP2COM_XLSX = (
    repo_root() / "data" / "ssp2com" / "ssp2-com_world_total.xlsx"
)
DEFAULT_HARMONISATION_HISTORY = Path(
    "/storage/no-backup-nac/users/bensan/emissions_harmonization_historical/"
    "data/processed/history-for-harmonisation/zenodo_17845154/db"
)
DEFAULT_CHARLIE_CSV = Path(
    "/storage/no-backup-nac/users/bensan/ar7_wg1_ch5/data/fair-inputs/"
    "emissions_1750-2500_with_ssp2com.csv"
)

# Map Charlie's FaIR variable names to our adapter-canonical IAMC names.
CHARLIE_TO_CANONICAL: dict[str, str] = {
    "CH4": "Emissions|CH4",
    "N2O": "Emissions|N2O",
    "CO": "Emissions|CO",
    "BC": "Emissions|BC",
    "OC": "Emissions|OC",
    "NH3": "Emissions|NH3",
    "NOx": "Emissions|NOx",
    "VOC": "Emissions|VOC",
    "Sulfur": "Emissions|Sulfur",
    "CO2 FFI": "Emissions|CO2|MAGICC Fossil and Industrial",
    "CO2 AFOLU": "Emissions|CO2|MAGICC AFOLU",
    "HFC-125": "Emissions|HFC125",
    "HFC-134a": "Emissions|HFC134a",
    "HFC-143a": "Emissions|HFC143a",
    "HFC-227ea": "Emissions|HFC227ea",
    "HFC-23": "Emissions|HFC23",
    "HFC-245fa": "Emissions|HFC245fa",
    "HFC-32": "Emissions|HFC32",
    "HFC-4310mee": "Emissions|HFC4310mee",
    "SF6": "Emissions|SF6",
    "C2F6": "Emissions|C2F6",
    "C6F14": "Emissions|C6F14",
    "CF4": "Emissions|CF4",
}

COMPARISON_YEARS = (2025, 2050, 2075, 2100)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ssp2com-xlsx",
        type=Path,
        default=DEFAULT_SSP2COM_XLSX,
        help=f"SSP2-COM world-total xlsx (default: {DEFAULT_SSP2COM_XLSX}).",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path(
            os.environ.get(
                "AR7_HARMONISATION_HISTORY", DEFAULT_HARMONISATION_HISTORY
            )
        ),
        help="Global history anchor directory (sharded feather store).",
    )
    parser.add_argument(
        "--charlie-csv",
        type=Path,
        default=DEFAULT_CHARLIE_CSV,
        help=f"Charlie's harmonised SSP2-COM CSV (default: {DEFAULT_CHARLIE_CSV}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/ssp2com/validation_vs_charlie.csv"),
        help="Output CSV path for the full comparison.",
    )
    return parser


def _load_ours(xlsx: Path, history_dir: Path) -> pd.DataFrame:
    scenario = load_ssp2com_world_total(xlsx)
    history = load_history_anchor(history_dir)
    harmonised = harmonise(scenario, history)
    ts = harmonised.timeseries()
    ts.columns = [c.year for c in ts.columns]
    return ts.droplevel(
        [n for n in ts.index.names if n != "variable"]
    )


def _load_charlie(csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(ssp2com_rows, l_rows)`` indexed by variable, float year cols."""
    df = pd.read_csv(csv)
    year_cols = [
        c for c in df.columns
        if c.replace(".", "").replace("-", "").isdigit()
    ]
    ssp2 = df.loc[df["scenario"] == "SSP2COM"].set_index("variable")[year_cols]
    l_rows = df.loc[df["scenario"] == "L"].set_index("variable")[year_cols]
    ssp2.columns = [float(c) for c in ssp2.columns]
    l_rows.columns = [float(c) for c in l_rows.columns]
    return ssp2, l_rows


def _is_l_fallback(
    species_charlie: str,
    ssp2: pd.DataFrame,
    l_rows: pd.DataFrame,
    anchor_year: float = 2023.5,
) -> bool:
    """True if Charlie's SSP2COM equals his L scenario at the anchor year."""
    if species_charlie not in ssp2.index or species_charlie not in l_rows.index:
        return False
    return abs(
        ssp2.at[species_charlie, anchor_year]
        - l_rows.at[species_charlie, anchor_year]
    ) < 1e-6


def compare(
    ours: pd.DataFrame,
    charlie_ssp2: pd.DataFrame,
    charlie_l: pd.DataFrame,
) -> pd.DataFrame:
    """Per-(species, year) comparison frame."""
    rows = []
    for charlie_var, canonical in CHARLIE_TO_CANONICAL.items():
        if charlie_var not in charlie_ssp2.index or canonical not in ours.index:
            continue
        l_fallback = _is_l_fallback(charlie_var, charlie_ssp2, charlie_l)
        for y in COMPARISON_YEARS:
            c_val = charlie_ssp2.at[charlie_var, y + 0.5]
            o_val = ours.at[canonical, y]
            diff = o_val - c_val
            pct = 100 * diff / c_val if c_val != 0 else float("nan")
            rows.append({
                "charlie_variable": charlie_var,
                "canonical_variable": canonical,
                "year": y,
                "charlie": c_val,
                "ours": o_val,
                "absolute_difference": diff,
                "relative_difference_pct": pct,
                "charlie_used_l_fallback": l_fallback,
            })
    return pd.DataFrame(rows)


def summarise(comparison: pd.DataFrame) -> None:
    """Print a textual summary distinguishing fallback from true-overlap species."""
    overlap = comparison.loc[~comparison["charlie_used_l_fallback"]]
    fallback = comparison.loc[comparison["charlie_used_l_fallback"]]

    print()
    print("=" * 78)
    print("Comparison summary: ours (light global harmoniser, 2023 anchor) vs")
    print(
        "                    Charlie's (SSP2-COM input + L-scenario "
        "anchored history)"
    )
    print("=" * 78)

    fallback_species = sorted(set(fallback["charlie_variable"]))
    overlap_species = sorted(set(overlap["charlie_variable"]))

    print(
        f"\n{len(overlap_species)} species both pipelines source from SSP2-COM:"
    )
    print(f"  {overlap_species}")
    if not overlap.empty:
        max_abs = (
            overlap.groupby("charlie_variable")["relative_difference_pct"]
            .apply(lambda s: s.abs().max())
            .sort_values(ascending=False)
        )
        print("\n  Worst relative differences across 2025-2100:")
        for sp, m in max_abs.head(10).items():
            print(f"    {sp:15s}  max |diff|: {m:6.1f}%")

    print(
        f"\n{len(fallback_species)} species where Charlie's pipeline falls back to L "
        f"(his SSP2-COM CSV doesn't carry these):"
    )
    print(f"  {fallback_species}")
    print(
        "\n  These divergences are NOT a harmonisation disagreement: the "
        "scenariocompass\n"
        "  xlsx we use carries these species' SSP2-COM trajectories "
        "explicitly, while\n"
        "  Charlie's CSV does not. Our values reflect what SSP2-COM "
        "actually projects;\n"
        "  Charlie's reflect his L-scenario default. Both are defensible "
        "given their\n"
        "  inputs."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print(f"Loading our pipeline: {args.ssp2com_xlsx}")
    ours = _load_ours(args.ssp2com_xlsx, args.history)

    print(f"Loading Charlie's CSV: {args.charlie_csv}")
    charlie_ssp2, charlie_l = _load_charlie(args.charlie_csv)

    comparison = compare(ours, charlie_ssp2, charlie_l)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(args.output, index=False)
    print(f"Wrote full comparison: {args.output} ({len(comparison)} rows)")

    summarise(comparison)
    return 0


if __name__ == "__main__":
    sys.exit(main())
