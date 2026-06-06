"""Scenario Compass Initiative 2025 ensemble experiment.

~1600 IAMC pathways (Huppmann et al. 2026, Zenodo 18598251). Lifts the shipped
`Climate Assessment|Infilled|Emissions|*` driving emissions and runs them
through all three SCMs. The novel contribution over SCI's own assessment is
adding FaIR and CICERO-SCM alongside MAGICC (SCI ships MAGICC-only). Milestone 4.

The full SCI x 3-SCM x N-member product is too large to hold in one ScmRun, so
this driver writes one NetCDF file per (pathway, model) as it goes (a chunked
writer): RAM stays bounded to a single pathway, and a re-run skips files already
on disk, so an interrupted batch resumes where it stopped.

One file per (pathway, model), rather than one per pathway, because the three
SCMs label their ensemble members differently (FaIR and MAGICC use integer
run ids, CICERO-SCM uses calibration strings like ``_95_8597``). Forcing them
into a shared ``run_id`` NetCDF dimension both fails to sort and bloats the file
with NaNs across the ragged member cross-product. Per-model files keep each
``run_id`` axis homogeneous and dense, and give per-model resume and error
isolation for free.
"""

from __future__ import annotations

import csv
import numbers
import threading
import time
import traceback
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

from ar7_ch5.load import available_sci_scenarios, iter_sci_infilled
from ar7_ch5.runners import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_OUTPUT_VARIABLES,
    MODEL_NAMES,
    PER_SCM_DEFAULT_WORKERS,
)
from ar7_ch5.runners.orchestrate import attach_pathway_id, run_models

# Meta columns promoted to NetCDF dimensions within a single-model file.
# ``run_id`` indexes the ensemble members and ``region`` keeps MAGICC's
# hemispheric boxes alongside FaIR/CICERO's World-only output. ``climate_model``
# is constant per file, so it stays scalar meta (a NetCDF attribute).
NC_DIMENSIONS = ("run_id", "region", "variable")

MANIFEST_NAME = "manifest.csv"
# ``pathway_id`` is the chapter pathway identifier (e.g. ``SSP1-19``);
# ``scenario`` is the canonical RCMIP3 name the runner spliced against
# (e.g. ``ssp119``). Both flow through to the manifest so the audit
# trail "which bundle row supplied the splice for this pathway?" is
# answerable from the manifest alone.
MANIFEST_FIELDS = (
    "scm",
    "iam",
    "pathway_id",
    "scenario",
    "filename",
    "status",
    "n_members",
    "n_rows",
    "seconds",
    "error",
)


def pathway_filename(iam: str, pathway_id: str) -> str:
    """Filesystem-safe per-pathway NetCDF name.

    Keys on the chapter ``pathway_id`` rather than the canonical
    ``scenario``, because multiple chapter pathways can share a
    canonical (e.g. SCI's ``SSP1-26`` and ``SSP1-34`` both map to
    ``ssp126``) -- a scenario-keyed filename would collide.
    """
    stem = f"sci_{iam}_{pathway_id}".replace("/", "-").replace(" ", "-")
    return f"{stem}.nc"


@dataclass
class PathwayResult:
    scm: str
    iam: str
    pathway_id: str
    scenario: str  # canonical RCMIP3 name
    filename: str
    status: str  # "written" | "skipped" | "failed"
    n_members: int | None
    n_rows: int
    seconds: float
    error: str


def run_sci_batch(
    xlsx: str | Path,
    models: Sequence[str] = MODEL_NAMES,
    *,
    n_members: int | None = 200,
    output_dir: str | Path = "outputs/sci",
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    region: str = "World",
    overwrite: bool = False,
    limit: int | None = None,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    pathways: Iterable[tuple[str, str]] | None = None,
) -> list[PathwayResult]:
    """Run every SCI pathway through ``models``, one NetCDF per (pathway, model).

    Parameters
    ----------
    xlsx
        Path to the SCI ensemble ``.xlsx`` (read once via the CSV cache).
    models
        Subset of :data:`MODEL_NAMES` to run.
    n_members
        Members per model. Default 200 (a fixed common subset for the first
        full-coverage pass); ``None`` runs each model's full native set.
    output_dir
        Root for the per-model subdirectories of ``.nc`` files and the manifest
        (gitignored; created if absent). Files land under
        ``<output_dir>/<scm>/``.
    output_variables
        Diagnostics each adapter extracts.
    region
        SCI region to drive (global file is ``World`` only).
    overwrite
        Re-run and overwrite files already on disk. Default ``False`` makes the
        batch resumable.
    limit
        Process at most this many pathways (for a quick partial pass).
    max_workers
        Worker-process cap per model run (see :data:`DEFAULT_MAX_WORKERS`).
    pathways
        If given, restrict the batch to these ``(iam, pathway_id)``
        pairs and skip every other pathway in the xlsx. Use this to
        run only the vetted subset (see
        :func:`ar7_ch5.load.vetted_sci_pathways`).

    Returns
    -------
    list[PathwayResult]
        One record per (pathway, model) attempted, mirroring the manifest rows.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    output_variables = tuple(output_variables)

    if pathways is not None:
        pathways = list(pathways)
        total = len(pathways)
    else:
        total = len(available_sci_scenarios(xlsx, sheet="data"))
    if limit is not None:
        total = min(total, limit)

    results: list[PathwayResult] = []
    manifest = out / MANIFEST_NAME
    manifest_lock = threading.Lock()
    pairs = iter_sci_infilled(xlsx, region=region, pathways=pathways)
    progress = tqdm(pairs, total=total, unit="pathway", desc="SCI batch")
    for i, (iam, pathway_id, run) in enumerate(progress):
        if limit is not None and i >= limit:
            break
        progress.set_postfix_str(f"{iam}/{pathway_id}")
        scenario = run.get_unique_meta("scenario")[0]
        # Dispatch all SCMs concurrently per pathway. Each SCM runs in
        # its own thread; FaIR is in-process (~no contention), CICERO
        # forks its own worker pool, MAGICC forks its own worker pool.
        # Per-SCM worker budgets come from PER_SCM_DEFAULT_WORKERS
        # (overridable via ``max_workers``). Wall-clock is dominated
        # by the slowest SCM rather than their sum.
        with ThreadPoolExecutor(max_workers=len(models)) as pool:
            futures = [
                pool.submit(
                    _run_one,
                    scm,
                    iam,
                    pathway_id,
                    scenario,
                    run,
                    n_members=n_members,
                    output_variables=output_variables,
                    out=out,
                    overwrite=overwrite,
                    max_workers=_workers_for(scm, max_workers),
                )
                for scm in models
            ]
            for fut in futures:
                result = fut.result()
                results.append(result)
                with manifest_lock:
                    _append_manifest(manifest, result)

    return results


def _workers_for(scm: str, override: int | None) -> int | None:
    """Pick the per-SCM worker budget.

    ``override`` (the caller-supplied ``max_workers``) wins when set.
    Otherwise look up the SCM's recommended concurrent-dispatch budget
    in :data:`PER_SCM_DEFAULT_WORKERS`; fall back to
    :data:`DEFAULT_MAX_WORKERS` for unknown SCMs.
    """
    if override is not None:
        return override
    return PER_SCM_DEFAULT_WORKERS.get(scm, DEFAULT_MAX_WORKERS)


def _run_one(
    scm: str,
    iam: str,
    pathway_id: str,
    scenario: str,
    run,
    *,
    n_members: int | None,
    output_variables: tuple[str, ...],
    out: Path,
    overwrite: bool,
    max_workers: int | None,
) -> PathwayResult:
    filename = pathway_filename(iam, pathway_id)
    target = out / scm / filename

    if target.is_file() and not overwrite:
        return PathwayResult(
            scm, iam, pathway_id, scenario, filename, "skipped",
            n_members, 0, 0.0, "",
        )

    start = time.perf_counter()
    try:
        result = run_models(
            run,
            [scm],
            n_members=n_members,
            output_variables=output_variables,
            max_workers=max_workers,
        )
        # Adapter dropped pathway_id (it's not a standard meta column);
        # restore from the iteration variable so the NetCDF carries both
        # pathway_id (chapter) and scenario (canonical RCMIP3).
        result = attach_pathway_id(result, pathway_id)
        _drop_unwritable_metadata(result)
        target.parent.mkdir(parents=True, exist_ok=True)
        result.to_nc(target, dimensions=list(NC_DIMENSIONS))
        elapsed = time.perf_counter() - start
        return PathwayResult(
            scm, iam, pathway_id, scenario, filename, "written",
            n_members, result.shape[0], elapsed, "",
        )
    except Exception as exc:  # noqa: BLE001 - record and continue the batch
        elapsed = time.perf_counter() - start
        # Drop a partial/corrupt file so a resume retries this cleanly.
        target.unlink(missing_ok=True)
        traceback.print_exc()
        return PathwayResult(
            scm, iam, pathway_id, scenario, filename, "failed",
            n_members, 0, elapsed, f"{type(exc).__name__}: {exc}",
        )


def _drop_unwritable_metadata(run) -> None:
    """Strip run-level metadata that NetCDF cannot store as an attribute.

    scmdata writes ``ScmRun.metadata`` as dataset attributes, but MAGICC stamps
    a nested ``parameters`` namelist dict there (and a long ``stderr``), which
    NetCDF attribute serialisation rejects. Drop anything that is not a simple
    scalar; the per-timeseries meta (the actual results) is untouched.
    """
    md = run.metadata
    scalar = (str, numbers.Number, bool)
    for key in [k for k, v in md.items() if not isinstance(v, scalar)]:
        md.pop(key)


def _append_manifest(path: Path, result: PathwayResult) -> None:
    """Append one record to the manifest CSV (header written once)."""
    new = not path.is_file()
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(
            {
                "scm": result.scm,
                "iam": result.iam,
                "pathway_id": result.pathway_id,
                "scenario": result.scenario,
                "filename": result.filename,
                "status": result.status,
                "n_members": "" if result.n_members is None else result.n_members,
                "n_rows": result.n_rows,
                "seconds": f"{result.seconds:.1f}",
                "error": result.error,
            }
        )
