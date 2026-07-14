"""Strategy fail-closed + OAuth / provider-normalization mutation gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_credential_switcher.compat import mutation_allowed
from hermes_credential_switcher.service import CommandError, cmd_status, cmd_use
from hermes_credential_switcher.strategy import get_pool_strategy, require_fill_first_for_use
from tests.helpers import fake_entry, write_pool


def _write_strategy(hermes_home: Path, provider: str, strategy: str) -> None:
    path = hermes_home / "config.yaml"
    path.write_text(
        f"credential_pool_strategies:\n  {provider}: {strategy}\n",
        encoding="utf-8",
    )


def test_default_strategy_is_fill_first(hermes_home: Path):
    assert get_pool_strategy("openrouter", hermes_home=hermes_home) == "fill_first"


def test_reads_strategy_from_config_yaml(hermes_home: Path):
    _write_strategy(hermes_home, "openrouter", "round_robin")
    assert get_pool_strategy("openrouter", hermes_home=hermes_home) == "round_robin"


def test_use_fails_closed_for_round_robin(hermes_home: Path, auth_path: Path):
    _write_strategy(hermes_home, "demo-provider", "round_robin")
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
            ]
        },
    )
    with pytest.raises(CommandError, match="round_robin|fill_first") as exc:
        cmd_use("two", provider="demo-provider", hermes_home=hermes_home)
    msg = str(exc.value)
    assert "fill_first" in msg
    assert "credential_pool_strategies" in msg or "hermes auth" in msg
    # Disk unchanged
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    assert entries[0]["id"] == "a"


def test_use_fails_closed_for_least_used(hermes_home: Path, auth_path: Path):
    _write_strategy(hermes_home, "demo-provider", "least_used")
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
            ]
        },
    )
    with pytest.raises(CommandError, match="least_used|fill_first"):
        cmd_use("two", provider="demo-provider", hermes_home=hermes_home)


def test_status_does_not_claim_selected_under_round_robin(
    hermes_home: Path, auth_path: Path
):
    _write_strategy(hermes_home, "demo-provider", "round_robin")
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
            ]
        },
    )
    out = cmd_status(provider="demo-provider", hermes_home=hermes_home)
    assert "round_robin" in out
    assert "selected" not in out.lower() or "NOT" in out
    # Explicit: the preference marker should be absent for non-fill_first
    assert "← selected" not in out


def test_codex_oauth_device_code_use_fails_closed(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "openai-codex": [
                fake_entry(
                    entry_id="c1",
                    label="codex-primary",
                    priority=0,
                    source="device_code",
                    auth_type="oauth",
                    token="fake-codex-token-c1",
                ),
                fake_entry(
                    entry_id="c2",
                    label="codex-secondary",
                    priority=1,
                    source="device_code",
                    auth_type="oauth",
                    token="fake-codex-token-c2",
                ),
            ]
        },
    )
    with pytest.raises(CommandError, match="OAuth|singleton|device_code"):
        cmd_use("codex-secondary", provider="openai-codex", hermes_home=hermes_home)


def test_any_provider_oauth_use_fails_closed(hermes_home: Path, auth_path: Path):
    """0.1.0 fails closed for every OAuth entry — not only Codex."""
    write_pool(
        auth_path,
        {
            "openrouter": [
                fake_entry(
                    entry_id="o1",
                    label="oauth-primary",
                    priority=0,
                    source="manual",
                    auth_type="oauth",
                    token="fake-or-oauth-1",
                ),
                fake_entry(
                    entry_id="o2",
                    label="oauth-backup",
                    priority=1,
                    source="manual",
                    auth_type="oauth",
                    token="fake-or-oauth-2",
                ),
            ]
        },
    )
    with pytest.raises(CommandError, match="OAuth"):
        cmd_use("oauth-backup", provider="openrouter", hermes_home=hermes_home)
    entries = json.loads(auth_path.read_text())["credential_pool"]["openrouter"]
    assert entries[0]["id"] == "o1"


def test_anthropic_seeded_use_fails_closed(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "anthropic": [
                fake_entry(
                    entry_id="a1",
                    label="claude-code",
                    priority=0,
                    source="claude_code",
                    auth_type="oauth",
                    token="fake-ant-a1",
                ),
                fake_entry(
                    entry_id="a2",
                    label="hermes-pkce",
                    priority=1,
                    source="hermes_pkce",
                    auth_type="oauth",
                    token="fake-ant-a2",
                ),
            ]
        },
    )
    with pytest.raises(CommandError, match="OAuth|Anthropic|normalized|seeded"):
        cmd_use("hermes-pkce", provider="anthropic", hermes_home=hermes_home)


def test_anthropic_env_seeded_api_key_fails_closed(hermes_home: Path, auth_path: Path):
    """Known normalized seeded sources fail closed even when auth_type is api_key."""
    write_pool(
        auth_path,
        {
            "anthropic": [
                fake_entry(
                    entry_id="e1",
                    label="env-primary",
                    priority=0,
                    source="env:ANTHROPIC_API_KEY",
                    auth_type="api_key",
                    token="fake-env-e1",
                ),
                fake_entry(
                    entry_id="e2",
                    label="env-backup",
                    priority=1,
                    source="env:ANTHROPIC_API_KEY",
                    auth_type="api_key",
                    token="fake-env-e2",
                ),
            ]
        },
    )
    with pytest.raises(CommandError, match="Anthropic|normalized|seeded|env"):
        cmd_use("env-backup", provider="anthropic", hermes_home=hermes_home)


def test_anthropic_manual_api_key_use_allowed(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "anthropic": [
                fake_entry(
                    entry_id="m1",
                    label="manual-primary",
                    priority=0,
                    source="manual",
                    auth_type="api_key",
                    token="fake-ant-m1",
                ),
                fake_entry(
                    entry_id="m2",
                    label="manual-backup",
                    priority=1,
                    source="manual",
                    auth_type="api_key",
                    token="fake-ant-m2",
                ),
            ]
        },
    )
    out = cmd_use("manual-backup", provider="anthropic", hermes_home=hermes_home)
    assert "✓" in out
    entries = json.loads(auth_path.read_text())["credential_pool"]["anthropic"]
    assert entries[0]["id"] == "m2"


def test_mutation_allowed_helpers():
    ok, reason = mutation_allowed(
        "openai-codex",
        {"source": "device_code", "auth_type": "oauth"},
    )
    assert ok is False
    assert "OAuth" in reason or "oauth" in reason.lower()

    # Any-provider OAuth
    ok, reason = mutation_allowed(
        "openrouter",
        {"source": "manual", "auth_type": "oauth"},
    )
    assert ok is False
    assert "OAuth" in reason

    ok, _ = mutation_allowed(
        "openrouter",
        {"source": "manual", "auth_type": "api_key"},
    )
    assert ok is True

    ok, _ = mutation_allowed(
        "anthropic",
        {"source": "env:ANTHROPIC_API_KEY", "auth_type": "api_key"},
    )
    assert ok is False

    ok, _ = mutation_allowed(
        "anthropic",
        {"source": "manual", "auth_type": "api_key"},
    )
    assert ok is True
