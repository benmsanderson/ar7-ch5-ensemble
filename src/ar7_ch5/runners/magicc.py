"""MAGICC v7.5.3 run wrapper.

Builds a configured ``MAGICC7`` adapter from the AR6 probabilistic drawnset
(600 members). Each drawnset member supplies a full MAGICC namelist under
``nml_allcfgs``; we lift those into per-member cfg dicts (lower-cased namelist
keys, ``run_id`` from the member's ``paraset_id``). The licensed binary is
located via ``MAGICC_EXECUTABLE_7`` (see docs/data_setup.md); the returned
adapter is AdapterLike for ``orchestrate.run_models``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Sequence
from typing import Any

from openscm_runner import RunMode
from openscm_runner.adapters import MAGICC7

from . import DEFAULT_MAX_WORKERS, DEFAULT_OUTPUT_VARIABLES, resolve_magicc_drawnset


def _drawnset_cfgs(
    member_indices: Sequence[int] | None,
    end_year: int | None,
) -> list[dict[str, Any]]:
    drawnset = json.loads(resolve_magicc_drawnset().read_text())
    members = drawnset["configurations"]
    if member_indices is not None:
        members = [members[i] for i in member_indices]
    cfgs = [
        {
            "run_id": member["paraset_id"],
            **{k.lower(): v for k, v in member["nml_allcfgs"].items()},
        }
        for member in members
    ]
    if end_year is not None:
        # Pymagicc's default_config.nml sets endyear=2100. Override so
        # MAGICC integrates the same horizon as the input emissions
        # CSV; otherwise the run silently truncates at 2100 even when
        # the input goes further.
        for cfg in cfgs:
            cfg["endyear"] = end_year
    return cfgs


def build_magicc7(
    *,
    member_indices: Sequence[int] | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    mode: RunMode = RunMode.EMISSIONS_DRIVEN,
    end_year: int | None = None,
) -> MAGICC7:
    """Configure MAGICC v7.5.3 from the AR6 probabilistic drawnset.

    Parameters
    ----------
    member_indices
        Zero-based rows of the 600-member drawnset to run. ``None`` runs the
        full drawnset; the smoke test passes a short range.
    output_variables
        Diagnostics to extract.
    max_workers
        Cap on MAGICC worker processes. The adapter otherwise forks
        ``cpu_count()`` workers (read from ``MAGICC_WORKER_NUMBER`` via
        openscm-runner's settings), which exhausts NAC's fork commit headroom.
        ``None`` leaves the adapter default in place.
    mode
        Driving mode. MAGICC7's adapter currently declares only
        :attr:`~openscm_runner.RunMode.EMISSIONS_DRIVEN`; passed through for
        forward-compat with concentration-driven support once the adapter
        gains it. The orchestration layer rejects unsupported modes upstream.
    end_year
        Upper bound on the integration horizon, set per-cfg as ``endyear``
        (pymagicc's namelist key; default in ``pymagicc/default_config.nml``
        is 2100). Pass the experiment's emissions ``end_year`` here so
        MAGICC integrates the full input horizon; ``None`` leaves the
        pymagicc default in place.
    """
    if max_workers is not None:
        os.environ["MAGICC_WORKER_NUMBER"] = str(max_workers)
    return MAGICC7(
        cfgs=_drawnset_cfgs(member_indices, end_year),
        output_variables=tuple(output_variables),
        mode=mode,
    )
