"""Adapter assembly and dispatch.

``run_models`` builds the requested per-model AdapterLike objects (FaIR 2.x,
CICERO-SCM 2.1.1, MAGICC v7.5.3) and dispatches them through
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
import scmdata

from . import DEFAULT_OUTPUT_VARIABLES, MODEL_NAMES
from .ciceroscm import build_ciceroscmpy2
from .fair import build_fair2
from .magicc import build_magicc7

_BUILDERS = {
    "fair": build_fair2,
    "ciceroscm": build_ciceroscmpy2,
    "magicc": build_magicc7,
}


def build_adapters(
    models: Sequence[str] = MODEL_NAMES,
    *,
    n_members: int | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
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
    """
    unknown = [m for m in models if m not in _BUILDERS]
    if unknown:
        raise ValueError(
            f"Unknown model(s): {unknown}. Known models: {sorted(_BUILDERS)}."
        )
    member_indices = None if n_members is None else range(n_members)
    output_variables = tuple(output_variables)
    return [
        _BUILDERS[m](
            member_indices=member_indices,
            output_variables=output_variables,
        )
        for m in models
    ]


def run_models(
    scenarios: scmdata.ScmRun,
    models: Sequence[str] = MODEL_NAMES,
    *,
    n_members: int | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
) -> scmdata.ScmRun:
    """Run ``models`` over ``scenarios`` and return the combined ScmRun.

    Builds one adapter per model and dispatches the list through
    ``openscm_runner.run.run``; results from all models are concatenated with a
    ``climate_model`` meta column distinguishing them.
    """
    adapters = build_adapters(
        models, n_members=n_members, output_variables=output_variables
    )
    return openscm_runner.run.run(adapters, scenarios=scenarios)
