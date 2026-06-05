"""Shared figure helpers.

Common plotting utilities for the Chapter 5 figures. Backs:

- the YAML config / style loaders that each ``notebooks/figXX_*.py`` calls,
- a small matplotlib bootstrap (font / DPI / output-dir),
- a ``save`` helper that writes every requested format atomically.

Convention: figure scripts are jupytext-paired ``.py`` / ``.ipynb`` files
under ``notebooks/`` (the ``.py`` is the tracked source; ``.ipynb`` is
generated on demand). They drive on cached outputs only -- never re-run
SCMs -- so the figure layer stays fast and idempotent. Re-running source
ensembles is :mod:`ar7_ch5.cache` plus ``scripts/run_scenarios.py``.

Colour / style palettes come from :data:`scenariomip-paper-plots` (GMD
paper) for the ScenarioMIP runs and from scenariocompass for the GW0-GW8
warming categories; both live in ``schemes/style.yaml`` and propagate
into figures via :func:`load_style`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .runners import repo_root

DEFAULT_FIGURES_YAML = "schemes/figures.yaml"
DEFAULT_STYLE_YAML = "schemes/style.yaml"
DEFAULT_OUTPUT_DIR = "outputs/figures"


@dataclass(frozen=True)
class Style:
    """Resolved style values from ``schemes/style.yaml``."""

    scenario_colors: dict[str, str]
    scm_colors: dict[str, str]
    gw_colors: dict[str, str]
    dpi: int
    default_format: str
    fig_size_inches: tuple[float, float]
    font_family: str
    font_size: int

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Style":
        data = yaml.safe_load(Path(path).read_text())
        return cls(
            scenario_colors=dict(data.get("scenario_colors", {})),
            scm_colors=dict(data.get("scm_colors", {})),
            gw_colors=dict(data.get("gw_colors", {})),
            dpi=int(data.get("dpi", 200)),
            default_format=str(data.get("default_format", "png")),
            fig_size_inches=tuple(data.get("fig_size_inches", (7.0, 4.5))),  # type: ignore[arg-type]
            font_family=str(data.get("font_family", "sans-serif")),
            font_size=int(data.get("font_size", 10)),
        )


def _resolve_yaml(path: str | Path, default: str) -> Path:
    """Treat ``path`` as relative to the repo root if it isn't absolute."""
    p = Path(path) if path is not None else Path(default)
    if not p.is_absolute():
        p = repo_root() / p
    if not p.is_file():
        raise FileNotFoundError(f"YAML config not found: {p}")
    return p


def load_style(path: str | Path = DEFAULT_STYLE_YAML) -> Style:
    """Load the shared style block from ``schemes/style.yaml``."""
    return Style.from_yaml(_resolve_yaml(path, DEFAULT_STYLE_YAML))


def load_figures(path: str | Path = DEFAULT_FIGURES_YAML) -> dict[str, dict[str, Any]]:
    """Return the full ``schemes/figures.yaml`` mapping."""
    return yaml.safe_load(_resolve_yaml(path, DEFAULT_FIGURES_YAML).read_text())


def load_config(
    figure_id: str, path: str | Path = DEFAULT_FIGURES_YAML
) -> dict[str, Any]:
    """Return the config slice for one figure, with a clear error if missing."""
    figures = load_figures(path)
    if figure_id not in figures:
        raise KeyError(
            f"figure {figure_id!r} not in {path} "
            f"(known: {sorted(figures)}). Add an entry under that key."
        )
    return figures[figure_id]


def apply_style(style: Style) -> None:
    """Apply font / DPI defaults globally for the current matplotlib session."""
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = style.font_family
    plt.rcParams["font.size"] = style.font_size
    plt.rcParams["savefig.dpi"] = style.dpi
    plt.rcParams["figure.figsize"] = list(style.fig_size_inches)


def output_dir(path: str | Path = DEFAULT_OUTPUT_DIR) -> Path:
    """Repo-relative output directory for figures (created if absent)."""
    p = Path(path)
    if not p.is_absolute():
        p = repo_root() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(
    fig,
    figure_id: str,
    cfg: dict[str, Any],
    style: Style,
    *,
    output_root: str | Path = DEFAULT_OUTPUT_DIR,
) -> list[Path]:
    """Write ``fig`` to every requested format under ``output_root``.

    Returns the list of paths written. Format set comes from
    ``cfg["output_formats"]`` if present, else ``[style.default_format]``.
    """
    out = output_dir(output_root)
    formats: Iterable[str] = cfg.get("output_formats") or [style.default_format]
    written = []
    for fmt in formats:
        target = out / f"{figure_id}.{fmt}"
        fig.savefig(target, dpi=style.dpi, bbox_inches="tight")
        written.append(target)
    return written
