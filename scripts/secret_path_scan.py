#!/usr/bin/env python3
"""Scan the repo for accidental real-home Hermes paths and secret-shaped fixtures.

Fails CI if:
* Source/tests reference a hard-coded local user Hermes home
  (``/home/<user>/.hermes`` or ``C:\\Users\\<user>\\.hermes``), not only auth.json
* Test fixtures embed long live-looking JWTs / sk- keys that look production-real
* Any tracked file is named auth.json (real stores must never be committed)

This is a lightweight guardrail — not a full secret scanner.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Disallow absolute real-home style Hermes paths in code/tests/docs.
# Must catch any /home/<user>/.hermes and C:\Users\<user>\.hermes leakage
# (not only auth.json), including the old integration-test hard-coded path.
# Path.home() / ".hermes" constructs used for defensive refusal are OK.
BAD_HOME_PATHS = [
    re.compile(r"/home/[^/\s\"'`]+/\.hermes\b"),
    re.compile(r"[Cc]:\\Users\\[^\\\s\"'`]+\\\.hermes\b"),
    re.compile(r"[Cc]:/Users/[^/\s\"'`]+/\.hermes\b"),
]

# Fixture tokens must look fake.
LIVE_LOOKING = [
    re.compile(r"sk-(?:live|prod)[A-Za-z0-9_-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
]

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".ci",  # CI checkouts of hermes-agent — not scanned as product source
    ".mypy_cache",
    ".ruff_cache",
    ".eggs",
    "htmlcov",
    ".tox",
}

# Files that may mention real-home refusal patterns as documentation of the rule.
ALLOWLIST_REL = frozenset(
    {
        "scripts/secret_path_scan.py",
        "hermes_credential_switcher/paths.py",
        "SECURITY.md",
        "README.md",
    }
)


def _should_skip_dir(part: str) -> bool:
    if part in SKIP_DIR_NAMES:
        return True
    if part.endswith(".egg-info"):
        return True
    return False


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if any(_should_skip_dir(p) for p in rel_parts[:-1]):
            continue
        # Allow .github; skip other hidden dirs already handled by name set.
        if any(
            part.startswith(".") and part not in {".github", ".gitignore"}
            for part in rel_parts[:-1]
        ):
            continue
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".json"}:
            if path.name not in {"LICENSE", "plugin.yaml"}:
                continue
        yield path


def main() -> int:
    errors = []
    for path in iter_files():
        rel = path.relative_to(ROOT)
        rel_posix = rel.as_posix()
        if path.name == "auth.json":
            errors.append(f"tracked auth.json is forbidden: {rel_posix}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if rel_posix in ALLOWLIST_REL:
            # Still forbid live-looking keys; allow documented path patterns.
            for pat in LIVE_LOOKING:
                if pat.search(text):
                    errors.append(f"{rel_posix}: live-looking secret pattern {pat.pattern}")
            continue

        for pat in BAD_HOME_PATHS:
            if pat.search(text):
                errors.append(
                    f"{rel_posix}: hard-coded local Hermes home path leakage "
                    f"({pat.pattern})"
                )

        for pat in LIVE_LOOKING:
            if pat.search(text):
                errors.append(f"{rel_posix}: live-looking secret pattern {pat.pattern}")

        # Ensure tests don't call the real home auth by string constant write.
        if "tests" in rel.parts:
            if "open(Path.home()" in text and "auth.json" in text:
                errors.append(f"{rel_posix}: opens Path.home() auth.json")

    if errors:
        print("secret/path scan FAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print("secret/path scan OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
