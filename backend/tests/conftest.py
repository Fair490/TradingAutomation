"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import config  # noqa: E402
from backend.loaders import store  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.duckdb")
    # Ensure the data directory exists
    tmp_path.mkdir(parents=True, exist_ok=True)
    # Reset the connection to ensure a fresh database
    store.reset_connection()
    # Force schema creation by getting a connection
    with store.session() as con:
        pass  # This will trigger schema creation
    yield tmp_path
    # Clean up after the test
    store.reset_connection()
