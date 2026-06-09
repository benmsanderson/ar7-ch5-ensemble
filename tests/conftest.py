"""Session-wide pytest hooks for the ar7-ch5 suite.

Tests downstream of the chapter harmonisation pipeline read from the
per-ensemble cache parquets that ``scripts/harmonise.py`` writes
(``data/<ensemble>/cache/<ensemble>_harmonised_infilled.parquet``).
For the test suite to be runnable on a bare checkout without first
running the (slow) full-ensemble harmonisation, this conftest copies
the small fixture parquets shipped under ``tests/fixtures/`` to those
cache locations at session start. The originals are restored (deleted)
at session teardown so a follow-up production run isn't surprised by a
tiny cache.

Any fixture parquet whose corresponding production cache already exists
is left alone (so a developer who has built the real cache locally
still tests against it).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from ar7_ch5.runners import repo_root

_FIXTURE_TO_CACHE: dict[str, tuple[str, str]] = {
    "sci": (
        "sci_harmonised_infilled_tiny.parquet",
        "data/SCI/cache/sci_harmonised_infilled.parquet",
    ),
    "ssp2com": (
        "ssp2com_harmonised_infilled_tiny.parquet",
        "data/ssp2com/cache/ssp2com_harmonised_infilled.parquet",
    ),
    "scenariomip_cmip7": (
        "scenariomip_cmip7_harmonised_infilled_tiny.parquet",
        "data/scenariomip_cmip7/cache/scenariomip_cmip7_harmonised_infilled.parquet",
    ),
}


@pytest.fixture(scope="session", autouse=True)
def _stage_harmonised_caches() -> Iterator[None]:
    root = repo_root()
    fixtures_dir = root / "tests" / "fixtures"
    staged: list[Path] = []
    for fixture_name, cache_rel in _FIXTURE_TO_CACHE.values():
        src = fixtures_dir / fixture_name
        dst = root / cache_rel
        if not src.is_file():
            continue
        if dst.is_file():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
        staged.append(dst)
    try:
        yield
    finally:
        for dst in staged:
            try:
                dst.unlink()
            except FileNotFoundError:
                pass
