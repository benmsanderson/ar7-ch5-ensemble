"""SSP2-COM (community SSP2) experiment.

One pathway, three SCMs. The world-total SSP2-COM xlsx is loaded
(:mod:`ar7_ch5.load_ssp2com`), harmonised to the CMIP7 2023 anchor
(:mod:`ar7_ch5.harmonise`), then handed to the orchestrator
(:func:`ar7_ch5.runners.orchestrate.run_models`). One NetCDF per
(pathway, SCM) is written under ``<output_dir>/<scm>/ssp2com_<pathway_id>.nc``,
matching the SCI / ScenarioMIP / RCMIP3 layout so the cache reporter
and :mod:`ar7_ch5.metrics` see one shape across experiments.

Validation against Charlie Koven's FaIR-only SSP2-COM output lives in a
follow-up commit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import scmdata

from ..harmonise import (
    DEFAULT_ANCHOR_YEAR,
    DEFAULT_CONVERGENCE_YEAR,
    harmonise,
    load_history_anchor,
)
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
    xlsx: str | Path,
    history_dir: str | Path,
    *,
    models: Sequence[str] = MODEL_NAMES,
    n_members: int | None = 200,
    output_dir: str | Path = "outputs/ssp2com",
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    anchor_year: int = DEFAULT_ANCHOR_YEAR,
    convergence_year: int = DEFAULT_CONVERGENCE_YEAR,
) -> scmdata.ScmRun:
    """Load SSP2-COM, harmonise, run through ``models``, write per-SCM NetCDFs.

    Parameters
    ----------
    xlsx
        Path to ``ssp2-com_world_total.xlsx``.
    history_dir
        Directory of the published global history anchor (Zenodo 17845154,
        sharded feather store).
    models
        SCMs to run.
    n_members
        Members per SCM. Default 200 (matches the SCI batch convention).
    output_dir
        Root for per-SCM NetCDFs (``<output_dir>/<scm>.nc``). Created if
        absent.
    output_variables
        Diagnostics each adapter extracts.
    max_workers
        Worker-process cap per model run (see
        :data:`ar7_ch5.runners.DEFAULT_MAX_WORKERS`).
    anchor_year, convergence_year
        See :func:`ar7_ch5.harmonise.harmonise`.

    Returns
    -------
    The combined :class:`scmdata.ScmRun` (all SCMs, all members), so callers
    can do further analysis without re-reading the NetCDFs.
    """
    print(f"Loading SSP2-COM from {xlsx}...")
    scenario = load_ssp2com_world_total(xlsx)
    print(
        f"  {len(scenario.get_unique_meta('variable'))} species, "
        f"{scenario['year'].min()}-{scenario['year'].max()}."
    )

    print(f"Loading history anchor from {history_dir}...")
    history = load_history_anchor(history_dir)

    print(
        f"Harmonising at {anchor_year} -> convergence at {convergence_year}..."
    )
    harmonised = harmonise(
        scenario, history,
        anchor_year=anchor_year, convergence_year=convergence_year,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pathway_ids = sorted(harmonised.get_unique_meta("pathway_id"))
    pieces: list[scmdata.ScmRun] = []
    for scm in models:
        scm_dir = out / scm
        scm_dir.mkdir(parents=True, exist_ok=True)
        for pid in pathway_ids:
            one_pathway = harmonised.filter(pathway_id=pid)
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
        harmonised.timeseries()
    )
