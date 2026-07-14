"""Interprocess advisory file lock (fcntl / msvcrt).

Mirrors Hermes ``hermes_cli.auth._file_lock`` semantics closely enough for
standalone operation without importing Hermes internals.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]

DEFAULT_LOCK_TIMEOUT_SECONDS = 15.0

_lock_holder = threading.local()


class LockTimeoutError(TimeoutError):
    """Raised when the advisory lock cannot be acquired in time."""


@contextmanager
def interprocess_file_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    holder: threading.local | None = None,
) -> Iterator[None]:
    """Cross-process exclusive lock, reentrant per-thread via *holder*."""
    holder = holder or _lock_holder
    if getattr(holder, "depth", 0) > 0:
        holder.depth += 1
        try:
            yield
        finally:
            holder.depth -= 1
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if fcntl is None and msvcrt is None:
        # Last-resort single-process guard (rare platforms).
        holder.depth = 1
        try:
            yield
        finally:
            holder.depth = 0
        return

    if msvcrt and (not lock_path.exists() or lock_path.stat().st_size == 0):
        lock_path.write_text(" ", encoding="utf-8")

    mode = "r+" if msvcrt else "a+"
    with lock_path.open(mode, encoding="utf-8") as lock_file:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    assert msvcrt is not None
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except (BlockingIOError, OSError, PermissionError):
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(
                        f"Timed out waiting for lock: {lock_path}"
                    ) from None
                time.sleep(0.05)

        holder.depth = 1
        try:
            yield
        finally:
            holder.depth = 0
            if fcntl is not None:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
            elif msvcrt is not None:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except (OSError, IOError):
                    pass


def atomic_replace(src: Path, dst: Path) -> None:
    """Atomically replace *dst* with *src* (same filesystem)."""
    os.replace(str(src), str(dst))
