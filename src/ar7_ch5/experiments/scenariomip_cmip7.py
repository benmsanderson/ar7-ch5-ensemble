"""ScenarioMIP CMIP7 baseline experiment.

Seven scenarios (VL, L, LN, M, ML, H, HL), three SCMs. Emissions arrive
already harmonised and infilled (scenariomip-paper-plots, Zenodo
20329427), so no harmonisation stage here -- straight from the loader to
:func:`ar7_ch5.runners.orchestrate.run_models`. SSP2-COM, the eighth
scenario the chapter reports alongside these seven, lives in M5
(:mod:`ar7_ch5.experiments.ssp2com`) since its emissions source and
harmonisation pathway are separate.

Writes one NetCDF per (scenario, SCM) under
``<output_dir>/<scm>/scenariomip_<scenario>.nc``, mirroring the SCI batch
layout so :mod:`ar7_ch5.metrics` consumes both with the same code path.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import scmdata

from ..load_scenariomip import SCENARIOS, load_scenariomip_emissions
from ..runners import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_VARIABLES,
    MODEL_NAMES,
)
from ..runners.orchestrate import run_models

NC_DIMENSIONS = ("run_id", "region", "variable")


def run_scenariomip(
    csv: str | Path,
    *,
    models: Sequence[str] = MODEL_NAMES,
    scenarios: Iterable[str] | None = None,
    n_members: int | None = 200,
    output_dir: str | Path = "outputs/scenariomip_cmip7",
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    end_year: int = 2100,
) -> scmdata.ScmRun:
    """Run the ScenarioMIP CMIP7 baselines through ``models``.

    Parameters
    ----------
    csv
        Path to ``emissions_1750-2500.csv`` from scenariomip-paper-plots.
    models
        SCMs to run.
    scenarios
        Subset of :data:`ar7_ch5.load_scenariomip.SCENARIOS` to run.
        ``None`` runs all seven.
    n_members
        Members per SCM. Default 200 matches SCI / SSP2-COM.
    output_dir
        Root for the per-SCM NetCDFs.
    output_variables
        Diagnostics each adapter extracts.
    max_workers
        Worker-process cap per model run.
    end_year
        Year axis clip. Default 2100.

    Returns
    -------
    Combined :class:`scmdata.ScmRun` across all SCMs and scenarios so the
    caller can do further analysis without re-reading the NetCDFs.
    """
    print(f"Loading ScenarioMIP from {csv}...")
    all_scens = load_scenariomip_emissions(csv, scenarios=scenarios, end_year=end_year)
    requested = sorted(all_scens.get_unique_meta("scenario"))
    print(
        f"  {len(requested)} scenarios ({requested}), "
        f"{len(all_scens.get_unique_meta('variable'))} species, "
        f"{all_scens['year'].min()}-{all_scens['year'].max()}."
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pieces: list[scmdata.ScmRun] = []
    for scm in models:
        print(f"Running {scm} on {len(requested)} scenarios at n_members={n_members}...")
        result = run_models(
            all_scens, [scm],
            n_members=n_members,
            output_variables=output_variables,
            max_workers=max_workers,
        )
        scm_dir = out / scm
        scm_dir.mkdir(parents=True, exist_ok=True)
        for sc in sorted(result.get_unique_meta("scenario")):
            sub = result.filter(scenario=sc)
            target = scm_dir / f"scenariomip_{sc}.nc"
            sub.to_nc(target, dimensions=list(NC_DIMENSIONS))
            print(f"  wrote {target} ({sub.shape[0]} rows)")
        pieces.append(result)

    return scmdata.run_append(pieces) if pieces else scmdata.ScmRun(all_scens.timeseries())


__all__ = ["SCENARIOS", "run_scenariomip"]
