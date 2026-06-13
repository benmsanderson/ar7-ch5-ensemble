"""Diagnostic: compare chapter harmonised+infilled SCI output vs SCI's
shipped ``Climate Assessment|Infilled|*`` namespace.

This is a regression *diagnostic*, not an assertion. The two outputs
embed different scientific choices (the chapter's history anchor, aneris
overrides and infilling DB vs the AR6 climate-assessment workflow SCI
itself runs), so the question is "how much do they disagree, and is the
disagreement intelligible?". The script writes a per-species delta CSV
and prints a top-level summary; the chapter reads both before merging.

Usage::

    pixi run python scripts/validate_sci_vs_shipped.py
    pixi run python scripts/validate_sci_vs_shipped.py \\
        --chapter data/SCI/cache/sci_harmonised_infilled.parquet \\
        --output outputs/sci_validation_vs_shipped.csv \\
        --limit 50

The first form re-runs the chapter pipeline on the SCI raw input; pass
``--chapter`` to point at an already-cached parquet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from gcages.renaming import SupportedNamingConventions, convert_variable_name

from ar7_ch5.harmonisation import HarmonisationConfig, harmonise_and_infill
from ar7_ch5.load import SCI_INFILLED_NAMESPACE, load_sci_data_sheet, load_sci_raw_iamc
from ar7_ch5.runners import repo_root

_DEFAULT_SCI_XLSX = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)
_DEFAULT_OUTPUT = repo_root() / "outputs" / "sci_validation_vs_shipped.csv"

_IDX_NAMES = ("model", "scenario", "region", "variable", "unit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sci-xlsx",
        type=Path,
        default=_DEFAULT_SCI_XLSX,
        help="Path to the SCI ensemble xlsx (default: data/SCI/...).",
    )
    parser.add_argument(
        "--chapter",
        type=Path,
        default=None,
        help=(
            "Path to a pre-computed chapter-pipeline parquet. When omitted, "
            "the script re-runs the pipeline on ``--sci-xlsx``."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Output CSV (default: outputs/sci_validation_vs_shipped.csv).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to the first N pathways when running the pipeline.",
    )
    args = parser.parse_args(argv)

    if not args.sci_xlsx.is_file():
        print(f"SCI xlsx not found: {args.sci_xlsx}", file=sys.stderr)
        return 2

    shipped = _load_shipped_infilled(args.sci_xlsx)
    print(
        f"[validate] shipped: {len(shipped):,} rows, "
        f"{shipped.index.get_level_values('variable').nunique()} species"
    )

    if args.chapter is not None:
        if not args.chapter.is_file():
            print(f"chapter parquet not found: {args.chapter}", file=sys.stderr)
            return 2
        chapter = pd.read_parquet(args.chapter)
    else:
        chapter = _run_chapter_pipeline(args.sci_xlsx, limit=args.limit)
    print(
        f"[validate] chapter: {len(chapter):,} rows, "
        f"{chapter.index.get_level_values('variable').nunique()} species"
    )

    summary = _compute_deltas(chapter=chapter, shipped=shipped)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)
    print(
        f"[validate] wrote {len(summary)} variable-summary rows to "
        f"{args.output}."
    )
    _print_top_level_summary(summary)
    return 0


def _load_shipped_infilled(xlsx: Path) -> pd.DataFrame:
    """Read SCI's ``Climate Assessment|Infilled|Emissions|*`` rows.

    Returns a (model, scenario, region, variable, unit) MultiIndex with
    integer year columns; variable names are in the GCAGES convention,
    so the row index lines up with the chapter pipeline output.
    """
    df = load_sci_data_sheet(xlsx)
    df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
    df = df[df["variable"].astype(str).str.startswith(SCI_INFILLED_NAMESPACE)]
    df = df[df["region"] == "World"].copy()
    df["variable"] = df["variable"].str.slice(len(SCI_INFILLED_NAMESPACE))
    df["variable"] = df["variable"].map(_shipped_to_gcages)
    df = df[df["variable"].notna()]
    df = df.set_index(list(_IDX_NAMES))
    year_cols = sorted(c for c in df.columns if isinstance(c, int))
    return df[year_cols]


def _shipped_to_gcages(full_name: str) -> str | None:
    """Translate a shipped ``Emissions|...`` variable to GCAGES naming.

    The shipped namespace uses an IAMC-flavoured form (``Emissions|CH4``,
    ``Emissions|CO2|AFOLU``, ``Emissions|HFC125``) that often coincides
    with OPENSCM_RUNNER. We try OPENSCM_RUNNER first and fall back to
    CMIP7_SCENARIOMIP. Returns ``None`` for species gcages cannot
    translate (drop the row -- those are usually Montreal gases SCI
    ships under a different convention).
    """
    for source in (
        SupportedNamingConventions.OPENSCM_RUNNER,
        SupportedNamingConventions.CMIP7_SCENARIOMIP,
    ):
        try:
            return convert_variable_name(
                full_name,
                from_convention=source,
                to_convention=SupportedNamingConventions.GCAGES,
            )
        except Exception:  # noqa: BLE001 - any conversion failure means "unknown"
            continue
    return None


def _run_chapter_pipeline(
    xlsx: Path, *, limit: int | None
) -> pd.DataFrame:
    """Re-run the chapter harmonise+infill pipeline on the SCI raw input."""
    raw = load_sci_raw_iamc(xlsx)
    if limit is not None:
        from pandas_openscm.indexing import multi_index_match

        ms_only = raw.index.droplevel(["region", "variable", "unit"])
        pairs = list(ms_only.unique())[:limit]
        raw = raw.loc[
            multi_index_match(
                raw.index,
                pd.MultiIndex.from_tuples(pairs, names=["model", "scenario"]),
            )
        ]
    cfg = HarmonisationConfig(progress=False)
    return harmonise_and_infill(raw, config=cfg)


def _compute_deltas(
    *, chapter: pd.DataFrame, shipped: pd.DataFrame
) -> pd.DataFrame:
    """Per-(variable, year-window) summary of chapter vs shipped deltas."""
    # Align on the (model, scenario, variable) intersection. Units are
    # carried through the index in both, so a strict join works.
    common = chapter.index.intersection(shipped.index)
    if common.empty:
        return pd.DataFrame(
            columns=[
                "variable",
                "n_pathways",
                "mean_chapter_2050",
                "mean_shipped_2050",
                "mean_abs_delta_2050",
                "max_abs_delta_2050",
                "mean_chapter_2100",
                "mean_shipped_2100",
                "mean_abs_delta_2100",
                "max_abs_delta_2100",
            ]
        )

    year_cols = [c for c in chapter.columns if c in shipped.columns]
    ch = chapter.loc[common, year_cols]
    sh = shipped.loc[common, year_cols]
    delta = ch - sh

    rows: list[dict] = []
    for variable, grp in delta.groupby(level="variable"):
        ch_grp = ch.loc[grp.index]
        sh_grp = sh.loc[grp.index]
        pathway_index = grp.index.droplevel(["region", "variable", "unit"])
        row = {
            "variable": variable,
            "n_pathways": len(pathway_index.unique()),
        }
        for y in (2050, 2100):
            if y in year_cols:
                row[f"mean_chapter_{y}"] = float(ch_grp[y].mean())
                row[f"mean_shipped_{y}"] = float(sh_grp[y].mean())
                row[f"mean_abs_delta_{y}"] = float(grp[y].abs().mean())
                row[f"max_abs_delta_{y}"] = float(grp[y].abs().max())
            else:
                for key in (
                    f"mean_chapter_{y}",
                    f"mean_shipped_{y}",
                    f"mean_abs_delta_{y}",
                    f"max_abs_delta_{y}",
                ):
                    row[key] = None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("variable").reset_index(drop=True)


def _print_top_level_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("[validate] no overlap between chapter and shipped indices.")
        return
    print("[validate] top-level summary (mean abs delta @ 2100):")
    cols = ["variable", "n_pathways", "mean_abs_delta_2100"]
    if "mean_abs_delta_2100" in summary.columns:
        ordered = summary.sort_values("mean_abs_delta_2100", ascending=False)
        print(ordered[cols].head(10).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
