"""HERMES_HOME / profile-safe path resolution.

Never hard-codes ``~/.hermes`` as the only home: respects ``HERMES_HOME``
and Hermes profile layouts so multi-profile operators stay isolated.
"""

from __future__ import annotations

import os
from pathlib import Path

# Plugin-local state lives under HERMES_HOME, never in the process CWD.
PLUGIN_STATE_DIRNAME = "credential-switcher"
ALIASES_FILENAME = "aliases.json"
AUTH_FILENAME = "auth.json"
AUTH_LOCK_SUFFIX = ".lock"

# Seat belt: refuse to touch the real operator auth store under pytest unless
# HERMES_HOME is explicitly redirected (mirrors Hermes hermetic test policy).
_REAL_AUTH_HINT = Path.home() / ".hermes" / AUTH_FILENAME


def get_hermes_home() -> Path:
    """Return the active Hermes home directory.

    Resolution order:
    1. ``HERMES_HOME`` environment variable (profile workers set this).
    2. Hermes ``get_hermes_home()`` when the host is importable.
    3. Platform-default ``~/.hermes`` (Linux/macOS) / ``%LOCALAPPDATA%/hermes``.
    """
    env = (os.environ.get("HERMES_HOME") or "").strip()
    if env:
        return Path(env).expanduser()

    try:
        from hermes_constants import get_hermes_home as _hermes_get_home

        return Path(_hermes_get_home())
    except Exception:
        pass

    if os.name == "nt":
        local = (os.environ.get("LOCALAPPDATA") or "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"


def auth_file_path(hermes_home: Path | None = None) -> Path:
    """Path to the active profile's ``auth.json``."""
    home = hermes_home or get_hermes_home()
    path = home / AUTH_FILENAME
    _pytest_refuse_real_auth(path)
    return path


def auth_lock_path(hermes_home: Path | None = None) -> Path:
    """Sibling lock file for interprocess coordination."""
    return auth_file_path(hermes_home).with_suffix(AUTH_LOCK_SUFFIX)


def plugin_state_dir(hermes_home: Path | None = None) -> Path:
    """Directory for plugin-owned config (aliases, etc.)."""
    return (hermes_home or get_hermes_home()) / PLUGIN_STATE_DIRNAME


def aliases_path(hermes_home: Path | None = None) -> Path:
    """User-configurable alias file (never ships with hard-coded aliases)."""
    return plugin_state_dir(hermes_home) / ALIASES_FILENAME


def _pytest_refuse_real_auth(path: Path) -> None:
    """Fail closed if a test would open the real user auth store."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        resolved = path.resolve(strict=False)
        real = _REAL_AUTH_HINT.resolve(strict=False)
    except Exception:
        return
    if resolved == real:
        raise RuntimeError(
            f"Refusing to touch real user auth store during tests: {path}. "
            "Set HERMES_HOME to a temporary directory."
        )


def is_profile_home(hermes_home: Path | None = None) -> bool:
    """Best-effort detection of ``~/.hermes/profiles/<name>`` layout."""
    home = hermes_home or get_hermes_home()
    parts = home.resolve(strict=False).parts
    return "profiles" in parts
