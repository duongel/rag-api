"""Shared pytest fixtures for rag-api tests."""

import os
from pathlib import Path

import pytest

# Ensure safe defaults for all tests — must be set before any rag_api import
# so that config module picks them up regardless of test ordering.
os.environ.setdefault("CHROMA_PATH", "/tmp/test_chroma")
os.environ.setdefault("AUTH_REQUIRED", "false")
os.environ.setdefault("PAPERLESS_URL", "http://paperless:8000")
os.environ.setdefault("PAPERLESS_TOKEN", "test-token")

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

