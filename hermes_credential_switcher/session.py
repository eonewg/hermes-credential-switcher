"""Session-apply messaging for pool priority selection.

Current Hermes has **no** public API to refresh credentials on an already-running
session. This plugin therefore reports only deterministic on-disk pool mutation
plus operator guidance to start a **new** session (``/new``).

No private Hermes session caches are inspected or mutated. No hypothetical
future API names are feature-detected.
"""

from __future__ import annotations

from typing import List


def new_session_apply_message() -> str:
    """Operator-facing explanation of when a selection takes effect."""
    return (
        "Selection is stored in the credential pool and applies to a **new** "
        "session. Current Hermes has no public API to rebind credentials on the "
        "active session; run `/new` (or start a new chat) so the agent rebuilds "
        "with the selected priority. "
        "This plugin does not touch private session caches."
    )


def public_api_status_lines() -> List[str]:
    """Human-readable session-apply status for ``status`` output."""
    return [
        "Current-session apply: not available (no public Hermes session credential API).",
        "Pool selection applies after `/new` or a new chat session.",
    ]
