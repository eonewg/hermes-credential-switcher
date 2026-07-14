"""use / --reset semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_credential_switcher.service import CommandError, cmd_use
from tests.helpers import fake_entry, write_pool


def test_plain_use_reorders_priority(hermes_home: Path, auth_path: Path, two_entry_pool):
    out = cmd_use("secondary", provider="demo-provider", hermes_home=hermes_home)
    assert "✓" in out
    data = json.loads(auth_path.read_text())
    entries = data["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "bbb222"
    assert entries[0]["priority"] == 0
    assert entries[1]["id"] == "aaa111"
    assert entries[1]["priority"] == 1
    # Plain use does not invent status resets on already-ok entries
    assert entries[0]["last_status"] == "ok"


def test_plain_use_fails_when_unhealthy(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="ok1", label="good", priority=0),
                fake_entry(
                    entry_id="bad1",
                    label="tired",
                    priority=1,
                    status="exhausted",
                    last_error_reason="rate_limit",
                    last_error_reset_at=9999999999,
                ),
            ]
        },
    )
    with pytest.raises(CommandError, match="unhealthy"):
        cmd_use("tired", provider="demo-provider", hermes_home=hermes_home)
    # Unchanged on disk
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "ok1"
    assert entries[1]["last_status"] == "exhausted"


def test_use_reset_clears_only_target_cooldown(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(
                    entry_id="a",
                    label="first",
                    priority=0,
                    status="exhausted",
                    last_error_code=429,
                    last_error_reason="other",
                    last_status_at=1.0,
                    last_error_message="stay",
                    last_error_reset_at=99,
                ),
                fake_entry(
                    entry_id="b",
                    label="second",
                    priority=1,
                    status="exhausted",
                    last_error_code=429,
                    last_error_reason="quota",
                    last_status_at=2.0,
                    last_error_message="clear-me",
                    last_error_reset_at=88,
                ),
            ]
        },
    )
    out = cmd_use(
        "second",
        provider="demo-provider",
        reset=True,
        hermes_home=hermes_home,
    )
    assert "✓" in out
    assert "Cooldown" in out or "cleared" in out.lower()
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "b"
    for key in (
        "last_status",
        "last_status_at",
        "last_error_code",
        "last_error_reason",
        "last_error_message",
        "last_error_reset_at",
    ):
        assert entries[0][key] is None
    # Other entry's exhaustion fields preserved
    other = entries[1]
    assert other["id"] == "a"
    assert other["last_status"] == "exhausted"
    assert other["last_error_reason"] == "other"
    assert other["last_error_reset_at"] == 99


def test_use_by_index(hermes_home: Path, auth_path: Path, two_entry_pool):
    cmd_use("2", provider="demo-provider", hermes_home=hermes_home)
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "bbb222"


def test_use_by_id(hermes_home: Path, auth_path: Path, two_entry_pool):
    cmd_use("bbb222", provider="demo-provider", hermes_home=hermes_home)
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "bbb222"


def test_dead_is_unhealthy(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="x", label="alive", priority=0),
                fake_entry(entry_id="y", label="gone", priority=1, status="dead"),
            ]
        },
    )
    with pytest.raises(CommandError, match="unhealthy"):
        cmd_use("gone", provider="demo-provider", hermes_home=hermes_home)
