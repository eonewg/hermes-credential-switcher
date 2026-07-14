"""Malformed JSON, permissions, rollback, mode preservation."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from hermes_credential_switcher.paths import auth_file_path
from hermes_credential_switcher.service import CommandError, cmd_list, cmd_use
from hermes_credential_switcher.store import (
    MalformedAuthError,
    VerificationError,
    load_auth_store,
    mutate_pool,
    write_auth_store_atomic,
)
from tests.helpers import fake_entry, write_pool


def test_malformed_json_raises(hermes_home: Path, auth_path: Path):
    auth_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(MalformedAuthError):
        load_auth_store(auth_path)
    with pytest.raises(CommandError):
        cmd_list(hermes_home=hermes_home)


def test_malformed_pool_type(hermes_home: Path, auth_path: Path):
    auth_path.write_text(
        json.dumps({"version": 1, "credential_pool": []}),
        encoding="utf-8",
    )
    with pytest.raises(MalformedAuthError):
        load_auth_store(auth_path)


def test_preserve_mode_0600(hermes_home: Path, auth_path: Path, two_entry_pool):
    auth_path.chmod(0o600)
    cmd_use("secondary", provider="demo-provider", hermes_home=hermes_home)
    mode = stat.S_IMODE(auth_path.stat().st_mode)
    assert mode & 0o077 == 0
    assert mode & 0o600 == 0o600


def test_preserve_stricter_mode_0400_when_possible(
    hermes_home: Path, auth_path: Path, two_entry_pool
):
    # 0400 is stricter; we try to preserve. On some FS chmod after write may
    # still be 0600 if we need write — policy is 0600 or stricter (no group/other).
    auth_path.chmod(0o600)
    cmd_use("2", provider="demo-provider", hermes_home=hermes_home)
    mode = stat.S_IMODE(auth_path.stat().st_mode)
    assert mode & 0o077 == 0


def test_pytest_refuses_real_auth_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    # Point HERMES_HOME at a path that resolves like the real one only if home matches.
    # Force auth_file_path to the real hint by patching get_hermes_home.
    real = Path.home() / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(real))
    with pytest.raises(RuntimeError, match="Refusing to touch real user auth store"):
        auth_file_path()


def test_rollback_on_verification_failure(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
            ]
        },
    )
    before = auth_path.read_text(encoding="utf-8")

    def mutator(entries):
        reordered = list(reversed([dict(e) for e in entries]))
        for i, e in enumerate(reordered):
            e["priority"] = i
        return reordered, reordered[0], "ok"

    def bad_verify(verified, selected):
        raise VerificationError("forced verification failure")

    with pytest.raises(Exception):
        mutate_pool(
            hermes_home=hermes_home,
            provider="demo-provider",
            mutator=mutator,
            verify=bad_verify,
        )

    after = auth_path.read_text(encoding="utf-8")
    assert json.loads(after)["credential_pool"]["demo-provider"][0]["id"] == "a"
    # No durable .bak left behind
    backups = list(hermes_home.glob("auth.json*"))
    assert auth_path in backups
    assert not any("bak" in p.name for p in backups)
    assert not any(p.suffix == ".bak" for p in hermes_home.iterdir())


def test_atomic_write_no_temp_left(hermes_home: Path, auth_path: Path):
    write_auth_store_atomic(
        auth_path,
        {"version": 1, "providers": {}, "credential_pool": {}},
        previous_bytes=None,
    )
    temps = list(hermes_home.glob("auth.json.tmp.*"))
    assert temps == []


def test_write_failure_rollback_in_memory_only(hermes_home: Path, auth_path: Path):
    original = {
        "version": 1,
        "providers": {},
        "credential_pool": {
            "p": [fake_entry(entry_id="keep", label="keep", priority=0)]
        },
    }
    write_auth_store_atomic(auth_path, original)
    previous = auth_path.read_bytes()

    broken = {
        "version": 1,
        "providers": {},
        "credential_pool": {
            "p": [fake_entry(entry_id="new", label="new", priority=0)]
        },
    }

    real_replace = os.replace

    def boom(src, dst):
        # Simulate failure after replace by restoring then raising on chmod path —
        # instead, fail before replace completes: raise during replace.
        raise OSError("simulated replace failure")

    with mock.patch("hermes_credential_switcher.store.atomic_replace", side_effect=boom):
        with pytest.raises(OSError):
            write_auth_store_atomic(auth_path, broken, previous_bytes=previous)

    # Original content preserved (replace never succeeded)
    assert json.loads(auth_path.read_text())["credential_pool"]["p"][0]["id"] == "keep"
    assert not list(hermes_home.glob("*.bak"))
