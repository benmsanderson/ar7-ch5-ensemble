"""Stage an augmented RCMIP3 bundle for chapter use.

The published RCMIP3 protocol bundle (Zenodo 20430630,
``data/rcmip3_protocol/``) does not include the seven CMIP7 ScenarioMIP
scenarios (``scen7-VL`` ... ``scen7-HL``) as natural-forcing rows in
``rcmip_phase3_forcing_v2.0.0.csv`` -- they are listed in the protocol
xlsx scenario sheet and shipped as per-category concentration / LU
files, but the wide forcing CSV the upstream openscm-runner reads is
keyed only on the SSP-RCP family + ``historical`` / ``historical-cmip6``.

The scenariomip-paper-plots companion (Zenodo 20329427, repository
``benmsanderson/scenariomip-paper-plots``) is the GMD paper's
single source of truth for the ScenarioMIP CMIP7 climate runs and
ships ``data/fair-inputs/volcanic_solar.csv``, a 1750-2501 Solar +
Volcanic ERF time series for each of the seven baselines (the
time series are identical across scenarios as expected; natural
forcings are externally prescribed in CMIP7).

This script stages an in-repo augmented bundle at
``data/rcmip3_protocol_augmented/`` that the chapter's bundle resolver
(:func:`ar7_ch5.runners.resolve_rcmip3_bundle`) prefers over the vanilla
bundle. The augmented tree is a symlink farm of the published bundle
with a single file replaced -- the augmented forcing CSV gains 14 new
rows (Solar + Volcanic for each of ``scen7-VL`` ... ``scen7-HL``). The
upstream openscm-runner then resolves ``scen7-*`` natural forcings from
the augmented row exactly as it does for any SSP-RCP scenario; no
chapter-side surrogate or runner monkey-patching is needed.

Usage
-----

    pixi run python scripts/build_rcmip3_bundle_augmented.py

The script is idempotent: re-running it rewrites the augmented forcing
CSV and refreshes the symlinks. Pass ``--clean`` to remove the
augmented tree first.

The augmented bundle is gitignored (it is a derivative of two Zenodo
records, both reproducible from this script).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VANILLA_BUNDLE = REPO_ROOT / "data" / "rcmip3_protocol"
DEFAULT_AUGMENTED_BUNDLE = REPO_ROOT / "data" / "rcmip3_protocol_augmented"
DEFAULT_GMD_VOLCANIC_SOLAR = Path(
    "/storage/no-backup-nac/users/bensan/scenariomip-paper-plots"
    "/data/fair-inputs/volcanic_solar.csv"
)

# Chapter short code -> RCMIP3 protocol name. Matches
# SCENARIOMIP_TO_CANONICAL in ar7_ch5._rcmip3_naming.
SCENARIOMIP_TO_CANONICAL = {
    "VL": "scen7-VL",
    "L":  "scen7-L",
    "LN": "scen7-LN",
    "M":  "scen7-M",
    "ML": "scen7-ML",
    "H":  "scen7-H",
    "HL": "scen7-HL",
}

# GMD CSV variable name -> RCMIP3 canonical variable name.
GMD_VARIABLE_TO_CANONICAL = {
    "Volcanic": "Effective Radiative Forcing|Natural|Volcanic",
    "Solar":    "Effective Radiative Forcing|Natural|Solar",
}

# scen7-{cat} -> SSP-RCP donor for the emissions baseline. The donor row
# supplies pre-2025 history (shared) plus a defensible 2025-2500 default
# for species the chapter does not actively vary; the chapter's user-
# supplied emissions overlay it for the species it carries. Mapping
# matches the upstream RCMIP3 generator's category -> SSP family
# defaults (``_RCMIP3_CMIP7_CATEGORY_TO_SSP``) refined to the
# SSP-RCP scenario whose emission intensity is closest to each
# category. Documented in docs/methods.md.
SCEN7_EMISSIONS_DONOR: dict[str, str] = {
    "scen7-VL": "ssp119",
    "scen7-L":  "ssp126",
    "scen7-LN": "ssp534-over",
    "scen7-M":  "ssp245",
    "scen7-ML": "ssp245",
    "scen7-H":  "ssp370",
    "scen7-HL": "ssp585",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vanilla-bundle",
        type=Path,
        default=DEFAULT_VANILLA_BUNDLE,
        help="Path to the published RCMIP3 bundle "
        "(default: data/rcmip3_protocol/).",
    )
    parser.add_argument(
        "--augmented-bundle",
        type=Path,
        default=DEFAULT_AUGMENTED_BUNDLE,
        help="Output path for the augmented bundle "
        "(default: data/rcmip3_protocol_augmented/).",
    )
    parser.add_argument(
        "--gmd-volcanic-solar",
        type=Path,
        default=DEFAULT_GMD_VOLCANIC_SOLAR,
        help="Path to scenariomip-paper-plots "
        "data/fair-inputs/volcanic_solar.csv.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the augmented bundle before rebuilding.",
    )
    return parser


def _augmented_forcing_rows(
    forcing_template: pd.DataFrame,
    gmd_volcanic_solar: pd.DataFrame,
    year_cols: list[str],
) -> pd.DataFrame:
    """Construct the seven scen7-{cat} Solar + Volcanic rows.

    Metadata is inherited from the ``historical`` solar / volcanic row
    in ``forcing_template`` (one row per variable). Year columns are
    filled from ``gmd_volcanic_solar`` 1750-2301 dense values plus the
    2501 extension. Years 2302-2500 (not represented in the GMD CSV) are
    filled by holding the last 2301 value -- the conventional steady-
    state extension for prescribed natural forcings.
    """
    rows = []
    gmd_years = [c for c in gmd_volcanic_solar.columns if c.isdigit() and len(c) == 4]
    gmd_dense_years = [y for y in gmd_years if 1750 <= int(y) <= 2301]
    gmd_has_2501 = "2501" in gmd_years

    for variable_gmd, variable_canonical in GMD_VARIABLE_TO_CANONICAL.items():
        template = forcing_template[
            (forcing_template["Scenario"] == "historical")
            & (forcing_template["Variable"] == variable_canonical)
        ]
        if template.empty:
            raise RuntimeError(
                f"vanilla bundle is missing the historical row for "
                f"{variable_canonical!r}; cannot build augmented rows."
            )
        template_row = template.iloc[0].to_dict()

        gmd_for_var = gmd_volcanic_solar[gmd_volcanic_solar["Variable"] == variable_gmd]
        if gmd_for_var.empty:
            raise RuntimeError(
                f"GMD volcanic_solar.csv has no rows for "
                f"variable={variable_gmd!r}."
            )

        for short_code, canonical_name in SCENARIOMIP_TO_CANONICAL.items():
            gmd_row = gmd_for_var[gmd_for_var["Scenario"] == short_code]
            if gmd_row.empty:
                raise RuntimeError(
                    f"GMD volcanic_solar.csv has no row for "
                    f"scenario={short_code!r}, variable={variable_gmd!r}."
                )
            gmd_row = gmd_row.iloc[0]

            new_row = dict(template_row)
            new_row["Model"] = "scenariomip-paper-plots (Zenodo 20329427)"
            new_row["Scenario"] = canonical_name
            new_row["Mip_Era"] = "CMIP7"

            last_dense_value = float(gmd_row[gmd_dense_years[-1]])
            for year in year_cols:
                yi = int(year)
                if 1750 <= yi <= 2301:
                    new_row[year] = float(gmd_row[year])
                elif yi == 2501 and gmd_has_2501:
                    new_row[year] = float(gmd_row["2501"])
                else:
                    new_row[year] = last_dense_value
            rows.append(new_row)

    return pd.DataFrame(rows, columns=forcing_template.columns.tolist())


def _augmented_emissions_rows(emissions: pd.DataFrame) -> pd.DataFrame:
    """Construct the scen7-{cat} emissions rows by copying SSP-RCP donors.

    For each ``scen7-{cat}`` in :data:`SCEN7_EMISSIONS_DONOR`, copy every
    ``(Variable, Region)`` row that the donor SSP-RCP scenario has and
    re-label ``Scenario`` to the scen7 name. The chapter's user
    emissions then overlay this baseline at run time -- species the
    chapter actively varies use the chapter's trajectory; species the
    chapter does not carry inherit the SSP donor's default. The donor
    row is also the source for pre-overlay historical years on every
    species.
    """
    rows = []
    for scen7_name, donor in SCEN7_EMISSIONS_DONOR.items():
        donor_rows = emissions[emissions["Scenario"] == donor]
        if donor_rows.empty:
            raise RuntimeError(
                f"Vanilla emissions CSV is missing donor scenario "
                f"{donor!r} required for {scen7_name!r}."
            )
        copy = donor_rows.copy()
        copy["Scenario"] = scen7_name
        copy["Model"] = (
            f"donor:{donor} (scenariomip-paper-plots overlay; "
            "see docs/methods.md)"
        )
        copy["Mip_Era"] = "CMIP7"
        rows.append(copy)
    return pd.concat(rows, ignore_index=True)


def _stage_symlink_farm(vanilla: Path, augmented: Path) -> None:
    """Mirror ``vanilla`` into ``augmented`` using directory-level symlinks.

    Top-level entries in the vanilla bundle become symlinks under
    ``augmented``; the single file we replace is broken out below.
    """
    augmented.mkdir(parents=True, exist_ok=True)
    for entry in vanilla.iterdir():
        target = augmented / entry.name
        if target.is_symlink() or target.exists():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        os.symlink(os.path.abspath(entry), target)


def _replace_forcing_csv(
    augmented: Path,
    forcing_csv: pd.DataFrame,
    *,
    relative_path: str,
) -> Path:
    """Write the augmented forcing CSV in place of the vanilla symlink."""
    target = augmented / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    # If target is a symlink (pointing into the vanilla input-datafiles dir),
    # replace it with a per-file symlink farm so we can write into this dir.
    if target.parent.is_symlink():
        vanilla_input = target.parent.resolve()
        target.parent.unlink()
        target.parent.mkdir(parents=True)
        for entry in vanilla_input.iterdir():
            os.symlink(os.path.abspath(entry), target.parent / entry.name)
    if target.is_symlink() or target.exists():
        target.unlink()
    forcing_csv.to_csv(target, index=False)
    return target


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    vanilla: Path = args.vanilla_bundle
    augmented: Path = args.augmented_bundle
    gmd_csv: Path = args.gmd_volcanic_solar

    if not vanilla.is_dir():
        print(f"error: vanilla RCMIP3 bundle not found at {vanilla}", file=sys.stderr)
        return 2
    if not gmd_csv.is_file():
        print(f"error: GMD volcanic_solar.csv not found at {gmd_csv}", file=sys.stderr)
        return 2

    if args.clean and augmented.exists():
        if augmented.is_symlink():
            augmented.unlink()
        else:
            shutil.rmtree(augmented)

    forcing_rel = "RCMIP3_input_datafiles/rcmip_phase3_forcing_v2.0.0.csv"
    emissions_rel = "RCMIP3_input_datafiles/rcmip_phase3_emissions_v2.0.0.csv"
    for rel in (forcing_rel, emissions_rel):
        src = vanilla / rel
        if not src.is_file():
            print(f"error: vanilla CSV not found at {src}", file=sys.stderr)
            return 2

    print(f"reading vanilla forcing CSV   {vanilla / forcing_rel}")
    forcing = pd.read_csv(vanilla / forcing_rel)
    year_cols = [
        c for c in forcing.columns
        if c.isdigit() and len(c) == 4
    ]

    print(f"reading vanilla emissions CSV {vanilla / emissions_rel}")
    emissions = pd.read_csv(vanilla / emissions_rel)

    print(f"reading GMD volcanic_solar    {gmd_csv}")
    gmd = pd.read_csv(gmd_csv)

    print("building scen7-{cat} Solar + Volcanic rows")
    extra_forcing = _augmented_forcing_rows(forcing, gmd, year_cols)
    print(f"  +{len(extra_forcing)} forcing rows: "
          f"{sorted(extra_forcing['Scenario'].unique().tolist())}")
    augmented_forcing = pd.concat([forcing, extra_forcing], ignore_index=True)

    print("building scen7-{cat} emissions rows (SSP-RCP donor copies)")
    extra_emissions = _augmented_emissions_rows(emissions)
    print(f"  +{len(extra_emissions)} emissions rows across "
          f"{extra_emissions['Scenario'].nunique()} scenarios; "
          f"donors: {SCEN7_EMISSIONS_DONOR}")
    augmented_emissions = pd.concat([emissions, extra_emissions], ignore_index=True)

    print(f"staging symlink farm at {augmented}")
    _stage_symlink_farm(vanilla, augmented)

    print(f"writing augmented forcing CSV   {augmented / forcing_rel}")
    _replace_forcing_csv(augmented, augmented_forcing, relative_path=forcing_rel)
    print(f"writing augmented emissions CSV {augmented / emissions_rel}")
    _replace_forcing_csv(augmented, augmented_emissions, relative_path=emissions_rel)

    print(f"done. augmented bundle ready at {augmented}")
    print("    resolve_rcmip3_bundle() will pick it up automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
