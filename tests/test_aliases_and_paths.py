"""Aliases (user-configured only) and profile-safe paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_credential_switcher.aliases import (
    AliasTarget,
    expand_alias,
    load_aliases,
    save_aliases,
)
from hermes_credential_switcher.paths import (
    aliases_path,
    auth_file_path,
    get_hermes_home,
    is_profile_home,
    plugin_state_dir,
)
from hermes_credential_switcher.service import CommandError, cmd_use
from tests.helpers import fake_entry, write_pool


def test_no_builtin_me_zuo_friend_aliases(hermes_home: Path):
    aliases = load_aliases(hermes_home)
    for banned in ("me", "zuo", "friend", "朋友", "原号"):
        assert banned not in aliases


def test_user_alias_expansion(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="primary", priority=0),
                fake_entry(entry_id="b", label="secondary", priority=1),
            ]
        },
    )
    save_aliases(
        {"work": AliasTarget(target="secondary", provider="demo-provider")},
        hermes_home=hermes_home,
    )
    target, provider, name = expand_alias("work", hermes_home=hermes_home)
    assert (target, provider, name) == ("secondary", "demo-provider", "work")
    out = cmd_use("work", hermes_home=hermes_home)
    assert "✓" in out
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "b"


def test_unknown_alias_falls_through_as_literal(hermes_home: Path):
    target, provider, name = expand_alias("not-an-alias", hermes_home=hermes_home)
    assert target == "not-an-alias"
    assert provider is None
    assert name is None


def test_hermes_home_env(hermes_home: Path, monkeypatch: pytest.MonkeyPatch):
    assert get_hermes_home() == hermes_home
    assert auth_file_path() == hermes_home / "auth.json"
    assert aliases_path().is_relative_to(hermes_home)
    assert plugin_state_dir() == hermes_home / "credential-switcher"


def test_profile_layout_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profile = tmp_path / "profiles" / "dev"
    profile.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    assert is_profile_home(profile) is True
    assert auth_file_path(profile) == profile / "auth.json"


def test_use_missing_target_errors(hermes_home: Path, two_entry_pool):
    with pytest.raises(CommandError, match="Missing target"):
        cmd_use("  ", provider="demo-provider", hermes_home=hermes_home)
