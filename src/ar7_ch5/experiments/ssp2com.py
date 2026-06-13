"""SSP2-COM (community SSP2) experiment.

One pathway, three SCMs. The SSP2-COM driving emissions are read from
the chapter harmonise+infill cache (``data/ssp2com/cache/...parquet``,
built via ``scripts/harmonise.py --ensemble ssp2com``) and handed to the
orchestrator (:func:`ar7_ch5.runners.orchestrate.run_models`). One
NetCDF per (pathway, SCM) is written under
``<output_dir>/<scm>/ssp2com_<pathway_id>.nc``, matching the SCI /
ScenarioMIP / RCMIP3 layout so the cache reporter and
:mod:`ar7_ch5.metrics` see one shape across experiments.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import scmdata

from ..load_ssp2com import load_ssp2com_world_total
from ..runners import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_VARIABLES,
    MODEL_NAMES,
)
from ..runners.orchestrate import attach_pathway_id, run_models

# Shape the per-SCM NetCDF the same way the SCI batch does so metrics.py
# can read both with the same code path.
NC_DIMENSIONS = ("run_id", "region", "variable")


def run_ssp2com(
    xlsx: str | Path | None = None,
    *,
    models: Sequence[str] = MODEL_NAMES,
    n_members: int | None = 200,
    output_dir: str | Path = "outputs/ssp2com",
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
) -> scmdata.ScmRun:
    """Load SSP2-COM from the chapter cache, run through ``models``, write NetCDFs.

    Parameters
    ----------
    xlsx
        Either the SSP2-COM xlsx (resolves to its sibling cache parquet)
        or the cache parquet directly. ``None`` resolves to the default
        cache location under ``data/ssp2com/cache/``.
    models
        SCMs to run.
    n_members
        Members per SCM. Default 200 (matches the SCI batch convention).
    output_dir
        Root for per-SCM NetCDFs (``<output_dir>/<scm>/<file>.nc``).
        Created if absent.
    output_variables
        Diagnostics each adapter extracts.
    max_workers
        Worker-process cap per model run (see
        :data:`ar7_ch5.runners.DEFAULT_MAX_WORKERS`).

    Returns
    -------
    The combined :class:`scmdata.ScmRun` (all SCMs, all members), so callers
    can do further analysis without re-reading the NetCDFs.
    """
    print(f"Loading SSP2-COM from {xlsx or 'default cache'}...")
    scenario = load_ssp2com_world_total(xlsx)
    print(
        f"  {len(scenario.get_unique_meta('variable'))} species, "
        f"{scenario['year'].min()}-{scenario['year'].max()}."
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pathway_ids = sorted(scenario.get_unique_meta("pathway_id"))
    pieces: list[scmdata.ScmRun] = []
    for scm in models:
        scm_dir = out / scm
        scm_dir.mkdir(parents=True, exist_ok=True)
        for pid in pathway_ids:
            one_pathway = scenario.filter(pathway_id=pid)
            print(f"Running {scm} on {pid} at n_members={n_members}...")
            result = run_models(
                one_pathway, [scm],
                n_members=n_members,
                output_variables=output_variables,
                max_workers=max_workers,
            )
            result = attach_pathway_id(result, pid)
            target = scm_dir / f"ssp2com_{pid}.nc"
            result.to_nc(target, dimensions=list(NC_DIMENSIONS))
            print(f"  wrote {target} ({result.shape[0]} rows)")
            pieces.append(result)

    return scmdata.run_append(pieces) if pieces else scmdata.ScmRun(
        scenario.timeseries()
    )
