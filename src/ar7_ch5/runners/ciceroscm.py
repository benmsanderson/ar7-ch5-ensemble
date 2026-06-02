"""CICERO-SCM 2.1.1 run wrapper.

Builds a configured ``CICEROSCMPY2`` adapter from the native CICERO calibration
distribution (Zenodo 20506399, Marit Sandstad's RCMIP-III 500-member set) via
``from_native_distribution``. The canonical gaspam / historical / natural-
emissions / forcing files resolve by filename inside the calibration directory;
the parameter posterior ``calibrated_ciceroscm_ensemble.json`` matches the
classmethod's ``calibrated_*ensemble*.json`` glob, so no path overrides are
needed. The returned adapter is AdapterLike for ``orchestrate.run_models``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from openscm_runner import RunMode
from openscm_runner.adapters import CICEROSCMPY2

from . import DEFAULT_OUTPUT_VARIABLES, resolve_ciceroscm_calibration


def build_ciceroscmpy2(
    *,
    member_indices: Sequence[int] | None = None,
    output_variables: Iterable[str] = DEFAULT_OUTPUT_VARIABLES,
    mode: RunMode = RunMode.EMISSIONS_DRIVEN,
    max_workers: int | None = None,
) -> CICEROSCMPY2:
    """Configure CICERO-SCM 2.1.1 from the native calibration distribution.

    Parameters
    ----------
    member_indices
        Zero-based rows of the 500-member posterior to run. ``None`` runs the
        full distribution; the smoke test passes a short range.
    output_variables
        Diagnostics to extract.
    mode
        Driving mode (default emissions-driven).
    max_workers
        Worker cap forwarded to ``DistributionRun.run_over_distribution``.
        ``None`` lets the adapter pick (capped at members x scenarios).
    """
    overrides = {} if max_workers is None else {"max_workers": max_workers}
    return CICEROSCMPY2.from_native_distribution(
        resolve_ciceroscm_calibration(),
        mode=mode,
        member_indices=member_indices,
        output_variables=tuple(output_variables),
        **overrides,
    )
