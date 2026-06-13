"""Tests for ``resolve_ciceroscm_distribution_json``.

The chapter offers three layers for choosing the CICERO-SCM parameter
posterior JSON: an env-var override, a chapter-staged file under
``data/calibration/``, and a ``None`` fallback that defers to the
adapter's built-in glob. These tests pin the precedence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ar7_ch5.runners import resolve_ciceroscm_distribution_json


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Clear AR7_CICEROSCM_DISTRIBUTION_JSON and stub data/calibration/."""
    monkeypatch.delenv("AR7_CICEROSCM_DISTRIBUTION_JSON", raising=False)
    fake_calib_dir = tmp_path / "calibration"
    fake_calib_dir.mkdir()
    monkeypatch.setattr(
        "ar7_ch5.runners._calibration_dir", lambda: fake_calib_dir
    )
    return fake_calib_dir


def test_env_var_takes_precedence(isolated_env, monkeypatch, tmp_path):
    """The env var beats the staged symlink."""
    env_target = tmp_path / "env.json"
    env_target.write_text("[]")
    staged = isolated_env / "ciceroscm_distribution.json"
    staged.write_text("[]")  # would be picked if env var were unset
    monkeypatch.setenv("AR7_CICEROSCM_DISTRIBUTION_JSON", str(env_target))

    assert resolve_ciceroscm_distribution_json() == Path(env_target)


def test_staged_symlink_used_when_env_unset(isolated_env):
    """With no env var, the staged file under data/calibration/ wins."""
    staged = isolated_env / "ciceroscm_distribution.json"
    staged.write_text("[]")

    assert resolve_ciceroscm_distribution_json() == staged


def test_returns_none_when_no_override(isolated_env):
    """With no env var and no staged file, returns None (adapter falls back)."""
    assert resolve_ciceroscm_distribution_json() is None
