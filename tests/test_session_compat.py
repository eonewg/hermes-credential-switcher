"""Session apply messaging — no invented public APIs."""

from __future__ import annotations

from pathlib import Path
import re

from hermes_credential_switcher.service import cmd_use
from hermes_credential_switcher.session import (
    new_session_apply_message,
    public_api_status_lines,
)
from tests.helpers import fake_entry, write_pool


def test_fallback_message_suggests_new_session(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0),
                fake_entry(entry_id="b", label="two", priority=1),
            ]
        },
    )
    out = cmd_use("two", provider="demo-provider", hermes_home=hermes_home)
    assert "/new" in out
    assert "new" in out.lower()
    # Must not claim private cache eviction
    assert "_session_model_overrides" not in out
    assert "_agent_cache" not in out
    # Must not invent hypothetical public API names
    assert "refresh_current_session_credentials" not in out
    assert "apply_credential_pool_selection" not in out
    assert "session_credentials" not in out


def test_session_helpers_are_deterministic():
    msg = new_session_apply_message()
    assert "/new" in msg
    assert "no public API" in msg.lower() or "no public" in msg.lower()
    lines = public_api_status_lines()
    assert any("not available" in line.lower() for line in lines)
    joined = "\n".join(lines)
    assert "refresh_current_session_credentials" not in joined
    assert "apply_credential_pool_selection" not in joined


def test_no_private_attribute_access_in_source():
    """Source must not *access* private session caches (mentions in docs OK)."""
    root = Path(__file__).resolve().parents[1] / "hermes_credential_switcher"
    access_re = re.compile(
        r"""(?x)
        getattr\s*\([^)]*_(?:session_model_overrides|agent_cache)
        | setattr\s*\([^)]*_(?:session_model_overrides|agent_cache)
        | \._session_model_overrides\b
        | \._agent_cache\b
        | \[['\"]_session_model_overrides['\"]\]
        | \[['\"]_agent_cache['\"]\]
        """
    )
    invent_re = re.compile(
        r"refresh_current_session_credentials|apply_credential_pool_selection"
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        match = access_re.search(text)
        assert match is None, f"{path.name} accesses private attribute: {match.group(0)!r}"
        # session.py must not invent speculative API symbols
        if path.name == "session.py":
            assert invent_re.search(text) is None, path.name
