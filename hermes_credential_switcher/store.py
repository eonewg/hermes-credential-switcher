"""Safe auth.json credential-pool mutations.

Design constraints (see SECURITY.md / README):

* HERMES_HOME / profile-safe paths only
* Interprocess file lock around read-modify-write
* Atomic replace of the final file
* Preserve mode 0600 or stricter on the auth store
* Rollback uses in-memory previous bytes only — never durable plaintext
  token backups on disk
* Re-read verification after every successful write
"""

from __future__ import annotations

import json
import logging
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .locking import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    atomic_replace,
    interprocess_file_lock,
)
from .paths import auth_file_path, auth_lock_path, get_hermes_home

logger = logging.getLogger(__name__)

# Cooldown / exhaustion fields cleared by ``use --reset`` (target only).
RESET_STATUS_FIELDS = (
    "last_status",
    "last_status_at",
    "last_error_code",
    "last_error_reason",
    "last_error_message",
    "last_error_reset_at",
)

UNHEALTHY_STATUSES = frozenset({"exhausted", "dead"})

AUTH_STORE_VERSION = 1
OWNER_RW = stat.S_IRUSR | stat.S_IWUSR  # 0o600


class StoreError(Exception):
    """Base error for store operations."""


class MalformedAuthError(StoreError):
    """auth.json is not a usable object."""


class PermissionError_(StoreError):
    """Insufficient permissions to read/write the auth store."""


class VerificationError(StoreError):
    """Post-write re-read did not match the intended mutation."""


class UnhealthyCredentialError(StoreError):
    """Target credential is exhausted/dead and --reset was not requested."""


class NotFoundError(StoreError):
    """Provider or target not found / ambiguous."""


@dataclass
class MutateResult:
    provider: str
    entries: List[Dict[str, Any]]
    selected: Optional[Dict[str, Any]]
    auth_path: Path
    message: str


def _secure_parent(path: Path) -> None:
    """Best-effort owner-only directory mode (no-op on unsupported FS)."""
    parent = path.parent
    try:
        if parent.exists():
            mode = parent.stat().st_mode & 0o777
            # Never widen; only tighten when group/other bits are set.
            if mode & 0o077:
                parent.chmod(0o700)
    except OSError:
        pass


def _desired_file_mode(existing: Optional[Path]) -> int:
    """Preserve existing mode when already 0600 or stricter; else 0600."""
    if existing is not None and existing.exists():
        try:
            current = stat.S_IMODE(existing.stat().st_mode)
            # Stricter or equal to 0600 means no group/other bits.
            if current & 0o077 == 0 and current & OWNER_RW:
                return current
        except OSError:
            pass
    return OWNER_RW


def load_auth_store(auth_path: Path) -> Dict[str, Any]:
    """Load and validate auth.json. Raises on malformed content."""
    if not auth_path.exists():
        return {"version": AUTH_STORE_VERSION, "providers": {}, "credential_pool": {}}
    try:
        raw_text = auth_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PermissionError_(f"Cannot read auth store: {auth_path}: {exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise MalformedAuthError(
            f"Malformed auth.json (invalid JSON) at {auth_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise MalformedAuthError(
            f"Malformed auth.json: expected object at root, got {type(raw).__name__}"
        )
    raw.setdefault("providers", {})
    if "credential_pool" in raw and raw["credential_pool"] is not None:
        if not isinstance(raw["credential_pool"], dict):
            raise MalformedAuthError(
                "Malformed auth.json: credential_pool must be an object"
            )
    else:
        raw.setdefault("credential_pool", {})
    return raw


def get_pool(
    store: Dict[str, Any],
    provider: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return credential_pool slices as provider → list[entry]."""
    pool = store.get("credential_pool") or {}
    if not isinstance(pool, dict):
        return {}
    result: Dict[str, List[Dict[str, Any]]] = {}
    for key, entries in pool.items():
        if provider is not None and key != provider:
            continue
        if isinstance(entries, list):
            result[str(key)] = [e for e in entries if isinstance(e, dict)]
        else:
            # Skip malformed provider slices rather than crash list.
            continue
    return result


def write_auth_store_atomic(
    auth_path: Path,
    store: Dict[str, Any],
    *,
    previous_bytes: Optional[bytes] = None,
) -> None:
    """Write *store* atomically with 0600-or-stricter mode.

    On failure after a partial replace, attempts in-memory rollback using
    *previous_bytes* only (no durable plaintext backup file is created).
    """
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    _secure_parent(auth_path)

    store = dict(store)
    store["version"] = store.get("version") or AUTH_STORE_VERSION
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(store, indent=2, ensure_ascii=False) + "\n"
    mode = _desired_file_mode(auth_path)

    tmp_path = auth_path.with_name(
        f"{auth_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    )
    wrote_final = False
    try:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            OWNER_RW,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        atomic_replace(tmp_path, auth_path)
        wrote_final = True
        try:
            auth_path.chmod(mode)
        except OSError:
            pass
        # Best-effort directory fsync for durability on crash.
        try:
            dir_fd = os.open(str(auth_path.parent), os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        # In-memory rollback only — never write a durable *.bak of tokens.
        if wrote_final and previous_bytes is not None:
            try:
                _restore_bytes(auth_path, previous_bytes, mode=mode)
            except Exception as restore_exc:
                logger.error(
                    "auth store write failed and in-memory rollback failed: %s",
                    restore_exc,
                )
        raise
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _restore_bytes(auth_path: Path, data: bytes, *, mode: int) -> None:
    """Restore previous content via a fresh temp file (still no durable backup)."""
    tmp_path = auth_path.with_name(
        f"{auth_path.name}.rollback.{os.getpid()}.{uuid.uuid4().hex}"
    )
    try:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            OWNER_RW,
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        atomic_replace(tmp_path, auth_path)
        try:
            auth_path.chmod(mode)
        except OSError:
            pass
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def _has_external_reference(entry: Dict[str, Any]) -> bool:
    """True when the entry is a reference-only / externally resolved secret.

    Hermes persists borrowed secrets (env, keyring, Vault/Bitwarden, config
    refs) as metadata + fingerprint without a durable raw token. Those must
    not be treated as unhealthy merely because ``access_token`` is empty.
    """
    if entry.get("secret_source") not in (None, ""):
        return True
    if entry.get("secret_fingerprint") not in (None, ""):
        return True
    source = str(entry.get("source") or "").strip()
    if not source:
        return False
    lowered = source.lower()
    if lowered.startswith("env:"):
        return True
    if lowered.startswith("config:"):
        return True
    # Common external-manager prefixes Hermes may surface on source labels.
    for prefix in (
        "keyring:",
        "vault:",
        "bitwarden:",
        "op:",
        "1password:",
        "systemd:",
        "secret:",
    ):
        if lowered.startswith(prefix):
            return True
    return False


def _is_manual_secret_entry(entry: Dict[str, Any]) -> bool:
    """True when the entry is intended to store a durable manual secret."""
    source = str(entry.get("source") or "manual").strip().lower()
    return source == "manual" or source.startswith("manual:")


def entry_is_healthy(entry: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (healthy, reason). Does not implement OAuth validation.

    Rules:
    * Explicit ``exhausted`` / ``dead`` → unhealthy.
    * Reference-only / env / keyring / Vault entries (external ref or
      fingerprint present) → healthy even without a persisted raw token.
    * Missing runtime material is unhealthy **only** when the entry is a
      manual secret store and has no recognized external reference.
    """
    status = entry.get("last_status")
    normalized = (str(status).strip().lower() if status not in (None, "") else "ok")
    if normalized in UNHEALTHY_STATUSES:
        reason = entry.get("last_error_reason") or normalized
        return False, f"status={normalized} ({reason})"

    token = entry.get("access_token") or entry.get("agent_key") or ""
    has_token = isinstance(token, str) and bool(token.strip())
    if has_token:
        return True, "ok"
    if _has_external_reference(entry):
        return True, "ok"
    if _is_manual_secret_entry(entry):
        return False, "missing runtime token (manual entry has no external reference)"
    # Non-manual, no token, no recognized ref — do not invent unhealthiness.
    return True, "ok"


def clear_target_cooldown(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Clear only cooldown/exhaustion fields on a shallow copy of *entry*."""
    updated = dict(entry)
    for key in RESET_STATUS_FIELDS:
        if key in updated:
            updated[key] = None
    return updated


def reorder_priority(
    entries: List[Dict[str, Any]],
    target_index: int,
) -> List[Dict[str, Any]]:
    """Move *target_index* to front and renumber priority 0..n-1."""
    if target_index < 0 or target_index >= len(entries):
        raise NotFoundError(f"Target index out of range: {target_index}")
    reordered = [dict(e) for e in entries]
    selected = reordered.pop(target_index)
    reordered.insert(0, selected)
    for i, entry in enumerate(reordered):
        entry["priority"] = i
    return reordered


def mutate_pool(
    *,
    hermes_home: Optional[Path] = None,
    provider: str,
    mutator: Callable[[List[Dict[str, Any]]], Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], str]],
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    verify: Optional[Callable[[List[Dict[str, Any]], Optional[Dict[str, Any]]], None]] = None,
) -> MutateResult:
    """Locked read-modify-write of one provider pool with re-read verification.

    *mutator* receives a deep-ish list of entry dicts and returns
    ``(new_entries, selected_entry_or_None, message)``.
    """
    home = hermes_home or get_hermes_home()
    auth_path = auth_file_path(home)
    lock_path = auth_lock_path(home)

    with interprocess_file_lock(lock_path, timeout_seconds=timeout_seconds):
        previous_bytes: Optional[bytes] = None
        if auth_path.exists():
            try:
                previous_bytes = auth_path.read_bytes()
            except OSError as exc:
                raise PermissionError_(f"Cannot read auth store: {exc}") from exc

        store = load_auth_store(auth_path)
        pool = store.setdefault("credential_pool", {})
        if not isinstance(pool, dict):
            raise MalformedAuthError("credential_pool must be an object")
        raw_entries = pool.get(provider)
        if not isinstance(raw_entries, list) or not raw_entries:
            raise NotFoundError(f"No credential pool entries for provider '{provider}'.")
        entries = [dict(e) for e in raw_entries if isinstance(e, dict)]
        if not entries:
            raise NotFoundError(f"No credential pool entries for provider '{provider}'.")

        new_entries, selected, message = mutator(entries)
        if not isinstance(new_entries, list) or not new_entries:
            raise StoreError("Mutator produced an empty pool; refusing to write.")

        # Snapshot for rollback comparison; mutator must not have written secrets
        # to disk itself.
        pool[provider] = new_entries
        store["credential_pool"] = pool

        try:
            write_auth_store_atomic(
                auth_path, store, previous_bytes=previous_bytes
            )
        except Exception as exc:
            raise StoreError(f"Failed to write auth store: {exc}") from exc

        # Re-read verification under the same lock.
        try:
            verified = load_auth_store(auth_path)
        except Exception as exc:
            if previous_bytes is not None:
                try:
                    _restore_bytes(
                        auth_path,
                        previous_bytes,
                        mode=_desired_file_mode(auth_path),
                    )
                except Exception:
                    pass
            raise VerificationError(f"Post-write re-read failed: {exc}") from exc

        verified_pool = (verified.get("credential_pool") or {}).get(provider)
        if not isinstance(verified_pool, list) or not verified_pool:
            if previous_bytes is not None:
                try:
                    _restore_bytes(
                        auth_path,
                        previous_bytes,
                        mode=_desired_file_mode(auth_path),
                    )
                except Exception:
                    pass
            raise VerificationError("Post-write verification: provider pool missing")

        if verify is not None:
            try:
                verify(verified_pool, selected)
            except Exception as exc:
                if previous_bytes is not None:
                    try:
                        _restore_bytes(
                            auth_path,
                            previous_bytes,
                            mode=_desired_file_mode(auth_path),
                        )
                    except Exception:
                        pass
                raise VerificationError(str(exc)) from exc

        return MutateResult(
            provider=provider,
            entries=[dict(e) for e in verified_pool if isinstance(e, dict)],
            selected=selected,
            auth_path=auth_path,
            message=message,
        )


def read_pools(
    *,
    hermes_home: Optional[Path] = None,
    provider: Optional[str] = None,
) -> Tuple[Path, Dict[str, List[Dict[str, Any]]]]:
    """Read pools under lock (shared exclusive lock for consistency)."""
    home = hermes_home or get_hermes_home()
    auth_path = auth_file_path(home)
    lock_path = auth_lock_path(home)
    with interprocess_file_lock(lock_path):
        store = load_auth_store(auth_path)
        return auth_path, get_pool(store, provider=provider)
