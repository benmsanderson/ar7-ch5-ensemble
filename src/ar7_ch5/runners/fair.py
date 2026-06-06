"""FaIR 2.x run wrapper.

Builds a configured ``FAIR2`` adapter from the native FaIR calibration
distribution (Zenodo 18828694 v1.6.0) via ``from_native_distribution``. The
returned adapter is an AdapterLike object that ``orchestrate.run_models`` hands
to ``openscm_runner.run.run`` alongside the CICERO-SCM and MAGICC adapters.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from openscm_runner import RunMode
from openscm_runner.adapters import FAIR2

from . import (
    DEFAULT_OUTPUT_VARIABLES,
    resolve_fair_calibration,
    resolve_rcmip3_bundle,
)


def build_fair2(
    *,
    member_indices: Sequence[int] | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    mode: RunMode = RunMode.EMISSIONS_DRIVEN,
    end_year: int | None = None,  # noqa: ARG001 -- FaIR respects input axis
) -> FAIR2:
    """Configure FaIR 2.x from the native calibration distribution.

    Parameters
    ----------
    member_indices
        Zero-based rows of the calibration posterior to run. ``None`` (the
        default) runs the full posterior; the smoke test passes a short range.
    output_variables
        Diagnostics to extract.
    mode
        Driving mode (default emissions-driven).
    end_year
        Accepted for interface parity with :func:`build_magicc7`; FaIR
        runs the time axis carried by the input emissions ScmRun so no
        explicit horizon is needed.
    """
    return FAIR2.from_native_distribution(
        resolve_fair_calibration(),
        resolve_rcmip3_bundle(),
        mode=mode,
        member_indices=member_indices,
        output_variables=tuple(output_variables),
    )
