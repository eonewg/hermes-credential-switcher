"""Multi-provider list/use inference."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_credential_switcher.service import CommandError, cmd_list, cmd_use


def test_list_all_providers(hermes_home: Path, multi_provider_pool):
    out = cmd_list(hermes_home=hermes_home)
    assert "provider-a" in out
    assert "provider-b" in out
    assert "alpha" in out
    assert "gamma" in out


def test_use_requires_provider_when_ambiguous(hermes_home: Path, multi_provider_pool):
    # target that doesn't uniquely identify a provider
    with pytest.raises(CommandError, match="Multiple providers|explicit provider"):
        cmd_use("1", hermes_home=hermes_home)


def test_use_with_explicit_provider(hermes_home: Path, auth_path: Path, multi_provider_pool):
    cmd_use("gamma", provider="provider-b", hermes_home=hermes_home)
    entries = json.loads(auth_path.read_text())["credential_pool"]["provider-b"]
    assert entries[0]["id"] == "b2"
    # other provider untouched
    other = json.loads(auth_path.read_text())["credential_pool"]["provider-a"]
    assert other[0]["id"] == "a1"


def test_unique_label_infers_provider(hermes_home: Path, auth_path: Path, multi_provider_pool):
    cmd_use("gamma", hermes_home=hermes_home)
    entries = json.loads(auth_path.read_text())["credential_pool"]["provider-b"]
    assert entries[0]["label"] == "gamma"
