"""Health checks for env / reference-only credentials."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_credential_switcher.service import CommandError, cmd_status, cmd_use
from hermes_credential_switcher.store import entry_is_healthy
from tests.helpers import fake_entry, write_pool


def test_env_reference_without_token_is_healthy():
    entry = fake_entry(
        entry_id="env1",
        label="OPENROUTER_API_KEY",
        priority=0,
        source="env:OPENROUTER_API_KEY",
        omit_token=True,
    )
    healthy, reason = entry_is_healthy(entry)
    assert healthy is True, reason


def test_secret_fingerprint_without_token_is_healthy():
    entry = fake_entry(
        entry_id="bw1",
        label="vault-key",
        priority=0,
        source="manual",
        omit_token=True,
        secret_source="bitwarden",
        secret_fingerprint="sha256:deadbeefcafef00d",
    )
    # Has fingerprint + secret_source even if source says manual — treat as ref.
    healthy, reason = entry_is_healthy(entry)
    assert healthy is True, reason


def test_keyring_source_without_token_is_healthy():
    entry = fake_entry(
        entry_id="kr1",
        label="keyring-entry",
        priority=0,
        source="keyring:openrouter",
        omit_token=True,
    )
    healthy, reason = entry_is_healthy(entry)
    assert healthy is True, reason


def test_manual_missing_token_without_ref_is_unhealthy():
    entry = fake_entry(
        entry_id="m1",
        label="broken-manual",
        priority=0,
        source="manual",
        omit_token=True,
    )
    healthy, reason = entry_is_healthy(entry)
    assert healthy is False
    assert "missing runtime token" in reason


def test_exhausted_reference_entry_is_unhealthy():
    entry = fake_entry(
        entry_id="env2",
        label="tired-env",
        priority=0,
        source="env:OPENROUTER_API_KEY",
        omit_token=True,
        status="exhausted",
        last_error_reason="rate_limit",
    )
    healthy, reason = entry_is_healthy(entry)
    assert healthy is False
    assert "exhausted" in reason


def test_use_accepts_env_reference_only(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "openrouter": [
                fake_entry(
                    entry_id="a",
                    label="primary",
                    priority=0,
                    source="env:OPENROUTER_API_KEY",
                    omit_token=True,
                    secret_fingerprint="sha256:aaa",
                ),
                fake_entry(
                    entry_id="b",
                    label="backup",
                    priority=1,
                    source="env:OPENROUTER_API_KEY_BACKUP",
                    omit_token=True,
                    secret_source="vault",
                    secret_fingerprint="sha256:bbb",
                ),
            ]
        },
    )
    out = cmd_use("backup", provider="openrouter", hermes_home=hermes_home)
    assert "✓" in out
    entries = json.loads(auth_path.read_text())["credential_pool"]["openrouter"]
    assert entries[0]["id"] == "b"
    # Still no raw tokens
    assert "access_token" not in entries[0] or not entries[0].get("access_token")


def test_status_marks_env_refs_healthy(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "openrouter": [
                fake_entry(
                    entry_id="a",
                    label="primary",
                    priority=0,
                    source="env:OPENROUTER_API_KEY",
                    omit_token=True,
                    secret_fingerprint="sha256:aaa",
                ),
            ]
        },
    )
    out = cmd_status(provider="openrouter", hermes_home=hermes_home)
    assert "healthy" in out
    assert "UNHEALTHY" not in out
    assert "fake-token" not in out
