"""Unit tests for ar7_ch5.figures helpers.

Pure config / loader behaviour; no matplotlib rendering, no jupyter. The
end-to-end figure-generation path is covered by the smoke run, not here.
"""

from __future__ import annotations

import pytest

from ar7_ch5 import figures


def test_load_style_returns_populated_palettes():
    style = figures.load_style()
    assert style.scenario_colors, "scenario_colors empty"
    assert style.scm_colors, "scm_colors empty"
    assert style.gw_colors, "gw_colors empty"
    assert style.dpi >= 72
    assert style.default_format in {"png", "pdf", "svg"}
    # palette sanity
    assert "fair" in style.scm_colors
    assert "GW0" in style.gw_colors
    assert "VL" in style.scenario_colors


def test_load_config_returns_known_figure():
    cfg = figures.load_config("fig01_classification")
    assert cfg["experiment"] == "sci"
    assert cfg["source"] == "xlsx"
    # output_formats is optional but if set must be a list of valid extensions
    if "output_formats" in cfg:
        assert all(fmt in {"png", "pdf", "svg"} for fmt in cfg["output_formats"])


def test_load_config_unknown_id_raises_helpful_keyerror():
    with pytest.raises(KeyError, match="not in"):
        figures.load_config("not_a_real_figure_xyz")


def test_load_figures_returns_full_mapping():
    all_figs = figures.load_figures()
    assert "fig01_classification" in all_figs
    # Every entry should have a title for the make_figures --list display
    for fid, cfg in all_figs.items():
        assert "title" in cfg, f"{fid} missing title"
