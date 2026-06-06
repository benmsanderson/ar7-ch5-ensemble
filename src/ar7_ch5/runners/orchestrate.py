"""Adapter assembly and dispatch.

``run_models`` builds the requested per-model AdapterLike objects (FaIR 2.x,
CICERO-SCM 2.1.2, MAGICC v7.5.3) and dispatches them through
``openscm_runner.run.run`` in a single call. The new engine API accepts a list
of pre-constructed adapters (each carrying its own cfgs and output_variables),
so all three models run against one scenarios ScmRun.

This is the milestone-2 smoke surface: a small, fixed member count per model on
one scenario. The chunked / streaming output writer for the full
SCI x 3-SCM x N-config product is a later milestone (see the brief).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import openscm_runner.run
import pandas as pd
import scmdata
from openscm_runner import RunMode
from openscm_runner.adapters import CICEROSCMPY2, FAIR2, MAGICC7

from . import DEFAULT_MAX_WORKERS, DEFAULT_OUTPUT_VARIABLES, MODEL_NAMES
from .ciceroscm import build_ciceroscmpy2
from .fair import build_fair2
from .magicc import build_magicc7

_BUILDERS = {
    "fair": build_fair2,
    "ciceroscm": build_ciceroscmpy2,
    "magicc": build_magicc7,
}

# Adapter classes per short name; used to query supported_modes without
# instantiating.
_ADAPTER_CLASSES = {
    "fair": FAIR2,
    "ciceroscm": CICEROSCMPY2,
    "magicc": MAGICC7,
}

# Builders that accept a ``max_workers`` cap (FaIR runs in-process, no pool).
_PARALLEL_BUILDERS = frozenset({"ciceroscm", "magicc"})


def models_supporting(
    mode: RunMode,
    candidates: Sequence[str] = MODEL_NAMES,
) -> list[str]:
    """Subset of ``candidates`` whose adapters declare ``mode`` support.

    Useful for the RCMIP3 experiment, which runs concentration-driven and
    automatically picks up new SCMs as their adapters gain
    :attr:`openscm_runner.RunMode.CONCENTRATION_DRIVEN` (e.g. MAGICC when
    its adapter is wired). Returns ``candidates`` order preserved.
    """
    return [
        m for m in candidates
        if m in _ADAPTER_CLASSES and mode in _ADAPTER_CLASSES[m].supported_modes
    ]


def build_adapters(
    models: Sequence[str] = MODEL_NAMES,
    *,
    n_members: int | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    mode: RunMode = RunMode.EMISSIONS_DRIVEN,
) -> list:
    """Construct the AdapterLike objects for ``models``.

    Parameters
    ----------
    models
        Subset of :data:`MODEL_NAMES` to build.
    n_members
        If given, run only the first ``n_members`` of each model's posterior /
        drawnset (the smoke-test ensemble size). ``None`` runs the full set.
    output_variables
        Diagnostics each adapter should extract.
    max_workers
        Worker-process cap for the parallel models (CICERO-SCM, MAGICC). FaIR
        runs in-process and ignores it. See :data:`DEFAULT_MAX_WORKERS`.
    mode
        Driving mode forwarded to each builder. Raises ``ValueError`` if any
        requested model's adapter does not declare support for ``mode``
        (use :func:`models_supporting` to pre-filter when running a
        concentration-driven experiment).
    """
    unknown = [m for m in models if m not in _BUILDERS]
    if unknown:
        raise ValueError(
            f"Unknown model(s): {unknown}. Known models: {sorted(_BUILDERS)}."
        )
    unsupported = [
        m for m in models
        if mode not in _ADAPTER_CLASSES[m].supported_modes
    ]
    if unsupported:
        supported_modes_summary = {
            m: sorted(
                x.value for x in _ADAPTER_CLASSES[m].supported_modes
            )
            for m in unsupported
        }
        raise ValueError(
            f"Model(s) {unsupported} do not declare {mode.value!r} support "
            f"(adapter supported_modes: {supported_modes_summary}). "
            "Filter the model list with ar7_ch5.runners.orchestrate."
            "models_supporting() before calling this."
        )
    member_indices = None if n_members is None else range(n_members)
    output_variables = tuple(output_variables)
    adapters = []
    for m in models:
        kwargs = {
            "member_indices": member_indices,
            "output_variables": output_variables,
            "mode": mode,
        }
        if m in _PARALLEL_BUILDERS:
            kwargs["max_workers"] = max_workers
        adapters.append(_BUILDERS[m](**kwargs))
    return adapters


def attach_pathway_id(result: scmdata.ScmRun, pathway_id: str) -> scmdata.ScmRun:
    """Stamp ``pathway_id`` as a constant meta column on every row of ``result``.

    Adapters often drop non-standard meta columns. Experiments that run one
    pathway at a time (the convention now that scenarios collide on
    canonical names, e.g. ``L`` / ``LN`` both -> ``ssp126``) can recover the
    chapter pathway id (the iteration variable) by calling this on the
    adapter's output before writing the NetCDF. Downstream consumers
    (:mod:`ar7_ch5.metrics`, :mod:`ar7_ch5.cache`, the figure layer) then
    read ``pathway_id`` for chapter identity. See
    ``docs/engine_upstream_switch.md``.
    """
    ts = result.timeseries()
    names = [n for n in ts.index.names if n != "pathway_id"]
    arrays = [ts.index.get_level_values(n) for n in names]
    arrays.append([pathway_id] * len(ts))
    ts.index = pd.MultiIndex.from_arrays(arrays, names=[*names, "pathway_id"])
    return scmdata.ScmRun(ts)


def run_models(
    scenarios: scmdata.ScmRun,
    models: Sequence[str] = MODEL_NAMES,
    *,
    n_members: int | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    mode: RunMode = RunMode.EMISSIONS_DRIVEN,
) -> scmdata.ScmRun:
    """Run ``models`` over ``scenarios`` and return the combined ScmRun.

    Builds one adapter per model and dispatches the list through
    ``openscm_runner.run.run``; results from all models are concatenated with a
    ``climate_model`` meta column distinguishing them. ``max_workers`` caps the
    per-model worker pool (see :data:`DEFAULT_MAX_WORKERS`). ``mode`` is
    forwarded to every adapter; see :func:`build_adapters`.
    """
    adapters = build_adapters(
        models,
        n_members=n_members,
        output_variables=output_variables,
        max_workers=max_workers,
        mode=mode,
    )
    return openscm_runner.run.run(adapters, scenarios=scenarios)
