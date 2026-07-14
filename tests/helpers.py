"""Shared fake fixtures — never real credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def fake_entry(
    *,
    entry_id: str,
    label: str,
    priority: int,
    status: str | None = "ok",
    token: str | None = None,
    source: str = "manual",
    omit_token: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a fake pool entry. Tokens are obviously synthetic."""
    payload: Dict[str, Any] = {
        "id": entry_id,
        "label": label,
        "auth_type": extra.pop("auth_type", "api_key"),
        "source": source,
        "priority": priority,
        "last_status": status,
        "last_status_at": extra.pop("last_status_at", None),
        "last_error_code": extra.pop("last_error_code", None),
        "last_error_reason": extra.pop("last_error_reason", None),
        "last_error_message": extra.pop("last_error_message", None),
        "last_error_reset_at": extra.pop("last_error_reset_at", None),
    }
    if not omit_token:
        payload["access_token"] = (
            token if token is not None else f"fake-token-{entry_id}"
        )
    payload.update(extra)
    return payload


def write_pool(
    auth_path: Path,
    pool: Dict[str, List[Dict[str, Any]]],
    *,
    mode: int = 0o600,
) -> None:
    data = {
        "version": 1,
        "providers": {},
        "credential_pool": pool,
    }
    auth_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    auth_path.chmod(mode)
