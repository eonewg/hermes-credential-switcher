"""Shared fixtures — all auth material is fake; HERMES_HOME is always tmp."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.helpers import fake_entry, write_pool


@pytest.fixture()
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated HERMES_HOME; never the real ~/.hermes."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "hermes_credential_switcher")
    return home


@pytest.fixture()
def auth_path(hermes_home: Path) -> Path:
    return hermes_home / "auth.json"


@pytest.fixture()
def two_entry_pool(auth_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    pool = {
        "demo-provider": [
            fake_entry(entry_id="aaa111", label="primary", priority=0),
            fake_entry(entry_id="bbb222", label="secondary", priority=1),
        ]
    }
    write_pool(auth_path, pool)
    return pool


@pytest.fixture()
def multi_provider_pool(auth_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    pool = {
        "provider-a": [
            fake_entry(entry_id="a1", label="alpha", priority=0),
        ],
        "provider-b": [
            fake_entry(entry_id="b1", label="beta", priority=0),
            fake_entry(entry_id="b2", label="gamma", priority=1),
        ],
    }
    write_pool(auth_path, pool)
    return pool
