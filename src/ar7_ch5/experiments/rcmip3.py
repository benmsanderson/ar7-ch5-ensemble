"""RCMIP3 idealised experiments (concentration-driven).

Selected concentration-driven scenarios from the RCMIP3 protocol bundle
(Zenodo 20430630). The v1 default diagnostics subset is the chapter's
ECS / TCR / TCRE family plus piControl and one example SSP:
``abrupt-2xCO2``, ``abrupt-4xCO2``, ``1pctCO2``, ``piControl``,
``ssp245``. Any subset of the 25 RCMIP3 concentration-driven scenarios
is selectable via ``--scenario`` / the ``scenarios=`` argument.

Currently runs through any SCM whose adapter declares
:attr:`openscm_runner.RunMode.CONCENTRATION_DRIVEN` support, which today
is **FaIR 2.x and CICERO-SCM**. MAGICC's adapter is emissions-driven
only as of writing; the experiment automatically picks it up once the
adapter gains concentration-driven support (no code change here is
required -- the model list is filtered via
:func:`ar7_ch5.runners.orchestrate.models_supporting`).

Writes one NetCDF per (pathway, SCM) under
``<output_dir>/<scm>/rcmip3_<pathway_id>.nc``, mirroring the SCI batch
layout. RCMIP3 scenarios are canonical by construction, so
``pathway_id == scenario`` here (e.g. ``abrupt-4xCO2``); the column is
emitted for cross-experiment uniformity with M4 / M5 / M6.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import scmdata
from openscm_runner import RunMode

from ..load_rcmip3 import DEFAULT_DIAGNOSTICS, load_rcmip3_concentrations
from ..runners import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_VARIABLES,
    MODEL_NAMES,
)
from ..runners.orchestrate import attach_pathway_id, models_supporting, run_models

NC_DIMENSIONS = ("run_id", "region", "variable")


def run_rcmip3(
    bundle_path: str | Path,
    *,
    models: Sequence[str] = MODEL_NAMES,
    scenarios: Iterable[str] | None = None,
    n_members: int | None = 200,
    output_dir: str | Path = "outputs/rcmip3",
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    end_year: int = 2100,
) -> scmdata.ScmRun:
    """Run RCMIP3 concentration-driven scenarios through supporting SCMs.

    Parameters
    ----------
    bundle_path
        Path to the published RCMIP3 protocol bundle (Zenodo 20430630).
    models
        SCMs to consider. Models whose adapter does not declare
        concentration-driven support are dropped from the run with a NOTE;
        if no models remain, ``RuntimeError`` is raised.
    scenarios
        Subset of RCMIP3 conc-driven scenarios to run.
        ``None`` uses :data:`ar7_ch5.load_rcmip3.DEFAULT_DIAGNOSTICS`.
    n_members
        Members per SCM. Default 200 matches SCI / SSP2-COM / ScenarioMIP.
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
    supported = models_supporting(RunMode.CONCENTRATION_DRIVEN, models)
    skipped = [m for m in models if m not in supported]
    if skipped:
        # Don't crash on the MAGICC-not-ready case; surface it loudly so the
        # user knows which SCMs they got. When MAGICC's adapter gains
        # concentration-driven support this NOTE goes away on its own.
        print(
            f"NOTE: {skipped} drop from RCMIP3 run -- adapter does not declare "
            "CONCENTRATION_DRIVEN support. Running with: " + str(supported) + "."
        )
    if not supported:
        raise RuntimeError(
            "No requested SCM declares CONCENTRATION_DRIVEN support; nothing "
            "to run. Requested models: " + str(list(models)) + "."
        )

    print(f"Loading RCMIP3 concentrations from {bundle_path}...")
    all_scens = load_rcmip3_concentrations(
        bundle_path, scenarios=scenarios, end_year=end_year,
    )
    requested = sorted(all_scens.get_unique_meta("pathway_id"))
    print(
        f"  {len(requested)} scenarios ({requested}), "
        f"{len(all_scens.get_unique_meta('variable'))} species, "
        f"{all_scens['year'].min()}-{all_scens['year'].max()}."
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pieces: list[scmdata.ScmRun] = []
    for scm in supported:
        scm_dir = out / scm
        scm_dir.mkdir(parents=True, exist_ok=True)
        for pid in requested:
            one_pathway = all_scens.filter(pathway_id=pid)
            print(f"Running {scm} on {pid} at n_members={n_members}...")
            result = run_models(
                one_pathway, [scm],
                n_members=n_members,
                output_variables=output_variables,
                max_workers=max_workers,
                mode=RunMode.CONCENTRATION_DRIVEN,
            )
            result = attach_pathway_id(result, pid)
            target = scm_dir / f"rcmip3_{pid}.nc"
            result.to_nc(target, dimensions=list(NC_DIMENSIONS))
            print(f"  wrote {target} ({result.shape[0]} rows)")
            pieces.append(result)

    return scmdata.run_append(pieces) if pieces else scmdata.ScmRun(
        all_scens.timeseries()
    )


__all__ = ["DEFAULT_DIAGNOSTICS", "run_rcmip3"]
