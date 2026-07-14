"""Secret-safe formatting for command output and logs.

Never echo access tokens, refresh tokens, agent keys, or other secret
payload fields. Labels, ids, status, and priority are safe to display.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# Field names that must never appear in operator-facing output.
SECRET_FIELD_NAMES = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "agent_key",
        "api_key",
        "apikey",
        "client_secret",
        "password",
        "private_key",
        "authorization",
        "token",
        "secret",
    }
)

# Substring patterns that look like live secrets if they leak into free text.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}"),
    re.compile(r"(?i)(access_token|refresh_token|api_key|agent_key|token)\s*[:=]\s*\S+"),
]

REDACTED = "***REDACTED***"


def is_secret_field(name: str) -> bool:
    key = (name or "").strip().lower()
    if key in SECRET_FIELD_NAMES:
        return True
    # Catch nested names like "oauth.access_token"
    return any(part in SECRET_FIELD_NAMES for part in key.replace("-", "_").split("."))


def redact_text(text: str) -> str:
    """Mask known secret-shaped substrings in free-form text."""
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def public_entry_view(entry: Mapping[str, Any], *, index: int | None = None) -> dict[str, Any]:
    """Return a secret-free summary of a pool entry for display/logging."""
    view: dict[str, Any] = {}
    if index is not None:
        view["index"] = index
    view["id"] = entry.get("id")
    view["label"] = entry.get("label")
    view["priority"] = entry.get("priority")
    view["auth_type"] = entry.get("auth_type")
    view["source"] = entry.get("source")
    status = entry.get("last_status")
    view["status"] = status if status not in (None, "") else "ok"
    if entry.get("last_error_code") is not None:
        view["last_error_code"] = entry.get("last_error_code")
    if entry.get("last_error_reason"):
        view["last_error_reason"] = entry.get("last_error_reason")
    if entry.get("last_error_reset_at") is not None:
        view["last_error_reset_at"] = entry.get("last_error_reset_at")
    # Never copy secret fields even if callers pass a full entry.
    for key in list(view):
        if is_secret_field(str(key)):
            view.pop(key, None)
    return view


def format_entry_line(
    entry: Mapping[str, Any],
    *,
    index: int,
    selected: bool = False,
) -> str:
    """One human-readable line for list/status output."""
    view = public_entry_view(entry, index=index)
    label = view.get("label") or view.get("id") or f"#{index}"
    entry_id = view.get("id") or "-"
    status = view.get("status") or "ok"
    priority = view.get("priority")
    marker = " ← selected" if selected else ""
    extra = ""
    if status not in {"ok", None, ""}:
        reason = view.get("last_error_reason")
        code = view.get("last_error_code")
        bits = [str(status)]
        if code is not None:
            bits.append(f"code={code}")
        if reason:
            bits.append(str(reason))
        extra = " · " + ", ".join(bits)
    else:
        extra = " · ok"
    return (
        f"#{index} {label} (id={entry_id}, priority={priority}){extra}{marker}"
    )


def strip_secrets_from_mapping(data: Any) -> Any:
    """Recursively drop secret fields from a nested structure (for logs)."""
    if isinstance(data, Mapping):
        out = {}
        for k, v in data.items():
            if is_secret_field(str(k)):
                out[str(k)] = REDACTED
            else:
                out[str(k)] = strip_secrets_from_mapping(v)
        return out
    if isinstance(data, list):
        return [strip_secrets_from_mapping(item) for item in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


def assert_no_secrets(text: str, forbidden_values: Iterable[str] = ()) -> None:
    """Raise if *text* still contains known secret values (test helper)."""
    for value in forbidden_values:
        if value and value in text:
            raise AssertionError("Secret value leaked into output")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            # Allow our own redaction marker to pass
            if REDACTED in text and not any(
                p.search(text.replace(REDACTED, "")) for p in _SECRET_PATTERNS
            ):
                continue
            raise AssertionError(f"Secret-shaped content leaked into output: {pattern.pattern}")
