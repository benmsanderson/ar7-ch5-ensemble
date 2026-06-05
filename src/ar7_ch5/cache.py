"""Cache status for the chapter's SCM ensemble outputs.

Walks the expected output set per experiment and reports what's on disk
vs missing. Read-only -- never re-runs anything. The figure layer
consumes :func:`status_for` to fail early with a clear message if a
required input is absent, and ``scripts/cache_status.py`` is the CLI
front-end for chapter authors.

Re-running missing pieces is :mod:`ar7_ch5.experiments.*` plus
``scripts/run_scenarios.py``; this module deliberately does no compute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .runners import MODEL_NAMES, repo_root

SCI_XLSX_DEFAULT = (
    repo_root() / "data" / "SCI" / "SCI-2025_v1.0_pathways_ensemble_global.xlsx"
)
SCENARIOMIP_CSV_DEFAULT = (
    repo_root() / "data" / "scenariomip_cmip7" / "emissions_1750-2500.csv"
)
DEFAULT_OUTPUTS = repo_root() / "outputs"


@dataclass(frozen=True)
class CacheEntry:
    experiment: str
    scm: str
    expected: int
    present: int
    note: str = ""
    rerun_cmd: str = ""
    examples_missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def missing(self) -> int:
        return max(self.expected - self.present, 0)

    @property
    def complete(self) -> bool:
        return self.expected > 0 and self.present >= self.expected


# ---------------------------------------------------------------------------
# Per-experiment enumerators. Each returns one CacheEntry per model.
# ---------------------------------------------------------------------------


def _sci_status(outputs_dir: Path, scm: str) -> CacheEntry:
    from .load import available_sci_scenarios

    if not SCI_XLSX_DEFAULT.is_file():
        return CacheEntry(
            experiment="sci", scm=scm, expected=0, present=0,
            note=f"SCI xlsx not staged at {SCI_XLSX_DEFAULT}",
        )
    pairs = list(available_sci_scenarios(SCI_XLSX_DEFAULT))
    expected = len(pairs)
    scm_dir = outputs_dir / "sci" / scm
    present_files = (
        sorted(p.name for p in scm_dir.glob("*.nc")) if scm_dir.is_dir() else []
    )
    present = len(present_files)
    # Pick a few missing pairs for the user, derived from naming convention.
    expected_names = {
        f"sci_{iam}_{scen}.nc".replace("/", "-").replace(" ", "-")
        for iam, scen in pairs
    }
    examples = tuple(sorted(expected_names - set(present_files))[:3])
    return CacheEntry(
        experiment="sci", scm=scm,
        expected=expected, present=present,
        rerun_cmd=(
            f"pixi run python scripts/run_scenarios.py --experiment sci "
            f"--all --models {scm}"
        ),
        examples_missing=examples,
    )


def _ssp2com_status(outputs_dir: Path, scm: str) -> CacheEntry:
    """One NetCDF per pathway under outputs/ssp2com/<scm>/."""
    from .load_ssp2com import SSP2COM_PATHWAY_ID

    expected_names = {f"ssp2com_{SSP2COM_PATHWAY_ID}.nc"}
    scm_dir = outputs_dir / "ssp2com" / scm
    present_files = (
        sorted(p.name for p in scm_dir.glob("*.nc")) if scm_dir.is_dir() else []
    )
    present = len(set(present_files) & expected_names)
    examples = tuple(sorted(expected_names - set(present_files))[:3])
    return CacheEntry(
        experiment="ssp2com", scm=scm,
        expected=len(expected_names), present=present,
        rerun_cmd=(
            f"pixi run python scripts/run_scenarios.py --experiment ssp2com "
            f"--models {scm}"
        ),
        examples_missing=examples,
    )


def _scenariomip_status(outputs_dir: Path, scm: str) -> CacheEntry:
    """Per-scenario NetCDFs under outputs/scenariomip_cmip7/<scm>/."""
    from .load_scenariomip import SCENARIOS

    expected_names = {f"scenariomip_{s}.nc" for s in SCENARIOS}
    scm_dir = outputs_dir / "scenariomip_cmip7" / scm
    present_files = (
        sorted(p.name for p in scm_dir.glob("*.nc")) if scm_dir.is_dir() else []
    )
    present = len(present_files)
    examples = tuple(sorted(expected_names - set(present_files))[:3])
    return CacheEntry(
        experiment="scenariomip_cmip7", scm=scm,
        expected=len(expected_names), present=present,
        rerun_cmd=(
            f"pixi run python scripts/run_scenarios.py "
            f"--experiment scenariomip_cmip7 --models {scm}"
        ),
        examples_missing=examples,
    )


_SCM_ENUMERATORS = {
    "sci": _sci_status,
    "ssp2com": _ssp2com_status,
    "scenariomip_cmip7": _scenariomip_status,
}


# ---------------------------------------------------------------------------
# Classification CSVs (M3 post-processing).
# ---------------------------------------------------------------------------


def _classification_csv_status(outputs_dir: Path, source: str) -> CacheEntry:
    target = outputs_dir / f"classification_{source}.csv"
    present = 1 if target.is_file() else 0
    return CacheEntry(
        experiment="classification", scm=source,
        expected=1, present=present,
        rerun_cmd=(
            f"pixi run python scripts/classify.py --source {source} "
            f"--output {target.relative_to(repo_root()) if target.is_absolute() and target.is_relative_to(repo_root()) else target}"
        ),
    )


# ---------------------------------------------------------------------------
# Public surface.
# ---------------------------------------------------------------------------


def status_for(
    experiment: str,
    scm: str,
    outputs_dir: str | Path = DEFAULT_OUTPUTS,
) -> CacheEntry:
    """Status for one (experiment, scm) pair."""
    out = Path(outputs_dir)
    if experiment == "classification":
        return _classification_csv_status(out, scm)
    if experiment not in _SCM_ENUMERATORS:
        raise ValueError(
            f"Unknown experiment={experiment!r}. Known: "
            f"{sorted(['classification', *_SCM_ENUMERATORS])}."
        )
    return _SCM_ENUMERATORS[experiment](out, scm)


def status(
    outputs_dir: str | Path = DEFAULT_OUTPUTS,
    *,
    experiments: tuple[str, ...] = ("sci", "ssp2com", "scenariomip_cmip7"),
    models: tuple[str, ...] = MODEL_NAMES,
    classification_sources: tuple[str, ...] = ("xlsx", "per_model", "pooled"),
) -> list[CacheEntry]:
    """Full cache report across experiments x models, plus classification CSVs."""
    out = Path(outputs_dir)
    entries: list[CacheEntry] = []
    for exp in experiments:
        for scm in models:
            entries.append(status_for(exp, scm, out))
    for src in classification_sources:
        entries.append(_classification_csv_status(out, src))
    return entries


def format_report(entries: list[CacheEntry]) -> str:
    """Plain-text one-line-per-entry report."""
    lines = []
    last_experiment = None
    for e in entries:
        if e.experiment != last_experiment:
            lines.append(f"\n[{e.experiment}]")
            last_experiment = e.experiment
        if e.note:
            lines.append(f"  {e.scm:11s} {e.note}")
            continue
        status_tag = "OK " if e.complete else "   "
        line = (
            f"  {e.scm:11s} {status_tag}  {e.present:>5} / {e.expected:>5}"
        )
        if e.missing:
            line += f"  ({e.missing} missing)"
            if e.examples_missing:
                line += f"  e.g. {', '.join(e.examples_missing)}"
        lines.append(line)
        if e.missing and e.rerun_cmd:
            lines.append(f"               -> {e.rerun_cmd}")
    return "\n".join(lines).lstrip()
