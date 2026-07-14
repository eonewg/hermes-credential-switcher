"""Interprocess lock / concurrent mutation tests."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from hermes_credential_switcher.locking import LockTimeoutError, interprocess_file_lock
from hermes_credential_switcher.service import cmd_use
from tests.helpers import fake_entry, write_pool


def test_lock_blocks_until_release(hermes_home: Path, tmp_path: Path):
    lock_path = hermes_home / "auth.lock"
    entered = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def holder():
        try:
            with interprocess_file_lock(lock_path, timeout_seconds=5):
                entered.set()
                release.wait(timeout=5)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    t = threading.Thread(target=holder)
    t.start()
    assert entered.wait(timeout=2)

    with pytest.raises(LockTimeoutError):
        with interprocess_file_lock(lock_path, timeout_seconds=0.2):
            pass  # pragma: no cover

    release.set()
    t.join(timeout=2)
    assert not errors

    # After release, acquire succeeds.
    with interprocess_file_lock(lock_path, timeout_seconds=2):
        pass


def test_concurrent_use_serializes(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
                fake_entry(entry_id="c", label="three", priority=2),
            ]
        },
    )
    barriers = threading.Barrier(3)
    results: list[str] = []
    errors: list[BaseException] = []

    def worker(target: str):
        try:
            barriers.wait(timeout=5)
            out = cmd_use(target, provider="demo-provider", hermes_home=hermes_home)
            results.append(out)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("one",)),
        threading.Thread(target=worker, args=("two",)),
        threading.Thread(target=worker, args=("three",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert len(results) == 3
    entries = json.loads(auth_path.read_text())["credential_pool"]["demo-provider"]
    # Valid permutation with priorities 0..n-1 unique
    priorities = [e["priority"] for e in entries]
    assert sorted(priorities) == [0, 1, 2]
    assert len({e["id"] for e in entries}) == 3
    assert entries[0]["priority"] == 0
