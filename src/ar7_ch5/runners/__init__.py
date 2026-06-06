"""SCM run wrappers and orchestration.

Thin, per-model builders around the openscm-runner engine (FaIR 2.x,
CICERO-SCM 2.1.2, MAGICC v7.5.3). Each ``build_*`` returns a configured,
AdapterLike object; ``orchestrate.run_models`` dispatches a list of them through
``openscm_runner.run.run``. No mocking of the SCMs: tests hit the real adapters
on small inputs.

FaIR and CICERO-SCM are driven from external native calibration distributions
(see resolve_fair_calibration / resolve_ciceroscm_calibration); MAGICC uses its
licensed binary plus the AR6 probabilistic drawnset.
"""

from __future__ import annotations

import os
from pathlib import Path

# GSAT plus top-level forcing is enough to prove the engine integration in the
# smoke test; the full diagnostic set is requested by later milestones.
DEFAULT_OUTPUT_VARIABLES: tuple[str, ...] = (
    "Surface Air Temperature Change",
    "Effective Radiative Forcing",
)

MODEL_NAMES: tuple[str, ...] = ("fair", "ciceroscm", "magicc")

# Cap on worker processes per model run. CICERO-SCM and MAGICC each fork a
# ProcessPoolExecutor that otherwise defaults to ``cpu_count()`` (256 logical
# cores on NAC). Models run one at a time, so this is also the total concurrent
# worker count. Kept modest because NAC enforces strict memory overcommit
# (``vm.overcommit_memory=2``): every fork must reserve commit equal to the
# parent's virtual size, and hundreds of workers exhaust the commit headroom.
DEFAULT_MAX_WORKERS: int = 12


def repo_root() -> Path:
    """Repository root (three levels up from this file: runners/ar7_ch5/src)."""
    return Path(__file__).resolve().parents[3]


def _calibration_dir() -> Path:
    return repo_root() / "data" / "calibration"


def resolve_fair_calibration() -> Path:
    """Path to the FaIR native calibration bundle (Zenodo 18828694 v1.6.0).

    Override with ``AR7_FAIR_CALIBRATION``.
    """
    env = os.environ.get("AR7_FAIR_CALIBRATION")
    if env:
        return Path(env)
    return _calibration_dir() / "fair-1.6.0"


def resolve_ciceroscm_calibration() -> Path:
    """Path to the CICERO-SCM native calibration directory (Zenodo 20506399).

    Override with ``AR7_CICEROSCM_CALIBRATION``.
    """
    env = os.environ.get("AR7_CICEROSCM_CALIBRATION")
    if env:
        return Path(env)
    return _calibration_dir() / "ciceroscm-rcmip3-v1.0.0"


def resolve_rcmip3_bundle() -> Path:
    """Path to the RCMIP Phase 3 protocol bundle (Zenodo 20430630).

    The upstream FaIR2 and CICEROSCMPY2 adapters require this bundle for
    the historical splice, the natural forcings (solar + volcanic), and
    the land-use forcing trajectory for every scenario. Our loaders
    rewrite ``scenario`` to a canonical RCMIP3 name (see
    :mod:`ar7_ch5._rcmip3_naming`) so the bundle's matching row supplies
    those inputs; ``pathway_id`` preserves the chapter identity. See
    ``docs/engine_upstream_switch.md``.

    Resolution order:

    1. ``AR7_RCMIP3_BUNDLE`` env override (caller knows the path).
    2. In-repo augmented bundle ``data/rcmip3_protocol_augmented/`` --
       produced by ``scripts/build_rcmip3_bundle_augmented.py``, which
       splices the seven CMIP7 ScenarioMIP ``scen7-*`` natural-forcing
       rows from scenariomip-paper-plots (Zenodo 20329427) into the
       canonical forcing CSV. Preferred when present.
    3. In-repo vanilla bundle ``data/rcmip3_protocol/`` (Zenodo
       20430630 as published).
    4. NAC staged location.
    """
    env = os.environ.get("AR7_RCMIP3_BUNDLE")
    if env:
        return Path(env)
    augmented = repo_root() / "data" / "rcmip3_protocol_augmented"
    if augmented.is_dir():
        return augmented
    in_repo = repo_root() / "data" / "rcmip3_protocol"
    if in_repo.is_dir():
        return in_repo
    return Path("/storage/no-backup-nac/users/bensan/rcmip3_protocol")


def resolve_magicc_drawnset() -> Path:
    """Path to the MAGICC AR6 probabilistic drawnset JSON.

    Override with ``MAGICC_PROBABILISTIC_FILE``; otherwise look under the
    staged ``magicc-dist/ar6_prob`` directory (see docs/data_setup.md).
    """
    env = os.environ.get("MAGICC_PROBABILISTIC_FILE")
    if env:
        return Path(env)
    base = Path("/storage/no-backup-nac/users/bensan/magicc-dist/ar6_prob")
    matches = sorted(base.glob("*drawnset.json"))
    if not matches:
        raise FileNotFoundError(
            "No MAGICC drawnset found. Set MAGICC_PROBABILISTIC_FILE to the "
            "AR6 probabilistic drawnset JSON (see docs/data_setup.md)."
        )
    return matches[0]
