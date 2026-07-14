"""Provider-normalization and OAuth compatibility gates for safe pool mutations.

Hermes may re-seed or re-rank credential pools on load. This plugin's direct
fallback only reorders ``credential_pool`` entries in ``auth.json``. That is
**not** a guarantee of any-provider runtime activation when Hermes applies
provider-specific singleton/seed normalization afterward.

0.1.0 mutation policy (fail closed):

* **Every OAuth credential entry** (any provider) — provider OAuth state may
  require singleton/token-source synchronization that raw pool reorder cannot
  guarantee.
* **Known normalized seeded sources** (Codex ``device_code`` singleton,
  Anthropic env/OAuth seed ranking, etc.) — Hermes re-ranks or re-syncs these
  on load.

List/status remain generic for every provider. Manual API-key entries under
``fill_first`` remain supported.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

# Anthropic sources that Hermes re-ranks relative to each other on load.
_ANTHROPIC_NORMALIZED_SOURCES = frozenset(
    {
        "env:ANTHROPIC_TOKEN",
        "env:CLAUDE_CODE_OAUTH_TOKEN",
        "hermes_pkce",
        "claude_code",
        "env:ANTHROPIC_API_KEY",
    }
)

# Codex OAuth singleton sources re-synced from providers.openai-codex.
_CODEX_OAUTH_SOURCES = frozenset(
    {
        "device_code",
        "manual:device_code",
    }
)

# auth_type values that indicate OAuth / device-code / PKCE flows.
_OAUTH_AUTH_TYPES = frozenset(
    {
        "oauth",
        "oauth2",
        "pkce",
        "device_code",
        "refresh_token",
    }
)

# Source markers that imply OAuth/singleton seeding even when auth_type is absent.
_OAUTH_SOURCE_MARKERS = frozenset(
    {
        "device_code",
        "manual:device_code",
        "hermes_pkce",
        "claude_code",
    }
)


class MutationCompatibilityError(Exception):
    """Mutation refused because Hermes may supersede the reordered order."""


def _source(entry: Mapping[str, Any]) -> str:
    return str(entry.get("source") or "").strip()


def _auth_type(entry: Mapping[str, Any]) -> str:
    return str(entry.get("auth_type") or "").strip().lower()


def _is_manual_source(source: str) -> bool:
    normalized = (source or "").strip().lower()
    # manual:device_code is OAuth-seeded, not a plain manual API-key entry.
    if normalized in _OAUTH_SOURCE_MARKERS or normalized.endswith(":device_code"):
        return False
    return normalized == "manual" or (
        normalized.startswith("manual:") and "device_code" not in normalized
    )


def _is_oauth_entry(entry: Mapping[str, Any]) -> bool:
    """True when the entry is OAuth (any provider) or an OAuth-seeded source."""
    auth_type = _auth_type(entry)
    if auth_type in _OAUTH_AUTH_TYPES or "oauth" in auth_type:
        return True
    source_l = _source(entry).lower()
    if not source_l:
        return False
    if source_l in _OAUTH_SOURCE_MARKERS or source_l.endswith(":device_code"):
        return True
    if "oauth" in source_l:
        return True
    return False


def _is_known_normalized_seeded(provider: str, entry: Mapping[str, Any]) -> Tuple[bool, str]:
    """Return (blocked, reason) for known Hermes-normalized seeded sources."""
    prov = (provider or "").strip()
    source = _source(entry)
    source_l = source.lower()

    if prov == "openai-codex":
        if source_l in _CODEX_OAUTH_SOURCES or source_l.endswith(":device_code"):
            return True, (
                "openai-codex OAuth/device_code entries are re-synced from the "
                "Hermes auth-store singleton; reordering auth.json does not "
                "guarantee runtime activation. Use Hermes native auth "
                "(`hermes auth` / re-login) for Codex OAuth, or target a "
                "manual API-key pool entry that is not singleton-seeded."
            )

    if prov == "anthropic":
        if source in _ANTHROPIC_NORMALIZED_SOURCES or (
            source_l.startswith("env:") and not _is_manual_source(source)
        ):
            return True, (
                "Anthropic seeded/env/OAuth pool entries are priority-normalized "
                "by Hermes on load; raw reorder may be superseded. Prefer a "
                "manual API-key entry (`source=manual`, auth_type=api_key) or "
                "manage via `hermes auth`."
            )
        if source_l in {"hermes_pkce", "claude_code"}:
            return True, (
                "Anthropic OAuth-seeded entries (hermes_pkce / claude_code) are "
                "re-ranked by Hermes; mutation refused. Use `hermes auth` or a "
                "manual API-key entry."
            )

    # Cross-provider device_code / env-seed markers that are not plain manual keys.
    if source_l in _CODEX_OAUTH_SOURCES or source_l.endswith(":device_code"):
        return True, (
            f"Source '{source}' is a known provider-normalized OAuth/singleton "
            "seed; raw pool reorder is not reliable in 0.1.0. Use Hermes native "
            "`hermes auth` or a manual API-key entry under fill_first."
        )

    return False, ""


def mutation_allowed(
    provider: str,
    entry: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Return ``(ok, reason)`` for whether ``use`` may reorder *entry*.

    List/status never call this. Only mutation paths do.
    """
    # 1) Every OAuth credential entry — any provider.
    if _is_oauth_entry(entry):
        return False, (
            "OAuth credential entries require provider singleton/token-source "
            "synchronization that raw pool reorder cannot guarantee. "
            "0.1.0 fails closed for every OAuth entry (all providers). "
            "Use Hermes native `hermes auth` for OAuth accounts, or target a "
            "manual API-key entry under fill_first."
        )

    # 2) Known normalized seeded sources (even when auth_type is api_key).
    blocked, reason = _is_known_normalized_seeded(provider, entry)
    if blocked:
        return False, reason

    return True, ""


def require_mutation_allowed(provider: str, entry: Mapping[str, Any]) -> None:
    ok, reason = mutation_allowed(provider, entry)
    if not ok:
        raise MutationCompatibilityError(reason)


def compatibility_caveat_lines() -> list[str]:
    """Prominent operator-facing caveats (status / help / README mirrors)."""
    return [
        "COMPATIBILITY: This plugin only reorders credential_pool in auth.json.",
        "0.1.0 fails closed on use for every OAuth credential entry (any provider) "
        "and for known normalized seeded sources (e.g. Codex device_code, "
        "Anthropic env/OAuth seeds). List/status remain generic.",
        "Manual API-key entries under fill_first remain supported. This is not "
        "any-provider runtime activation.",
    ]
