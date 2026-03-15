"""Shared pytest fixtures for rag-api tests."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the absolute path to the ``tests/fixtures/`` directory."""
    return FIXTURES_DIR


@pytest.fixture
def erfolgsjournal_path(fixtures_dir: Path) -> str:
    """Return the relative path to the test Erfolgsjournal inside fixtures."""
    return "Erfolgsjournal.md"


@pytest.fixture
def fixtures_vault(fixtures_dir: Path) -> str:
    """Return the fixtures dir as a vault path string (for ``parse_markdown``)."""
    return str(fixtures_dir)

