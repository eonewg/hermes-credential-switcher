"""Secret-safe output tests."""

from __future__ import annotations

from pathlib import Path

from hermes_credential_switcher.redact import (
    format_entry_line,
    public_entry_view,
    redact_text,
)
from hermes_credential_switcher.service import cmd_list, cmd_status, cmd_use
from tests.helpers import fake_entry, write_pool


SECRET = "fake-super-secret-token-value-xyz"
JWTISH = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJmYWtlIn0.fakesig"


def test_public_entry_view_strips_tokens():
    entry = fake_entry(
        entry_id="x",
        label="lab",
        priority=0,
        token=SECRET,
    )
    entry["refresh_token"] = "refresh-" + SECRET
    entry["agent_key"] = "agent-" + SECRET
    view = public_entry_view(entry, index=1)
    blob = str(view)
    assert SECRET not in blob
    assert "refresh_token" not in view
    assert "access_token" not in view
    assert "agent_key" not in view
    assert view["label"] == "lab"


def test_format_line_no_secrets():
    entry = fake_entry(entry_id="x", label="lab", priority=0, token=SECRET)
    line = format_entry_line(entry, index=1, selected=True)
    assert SECRET not in line
    assert "lab" in line


def test_list_and_status_redact(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0, token=SECRET),
                fake_entry(entry_id="b", label="two", priority=1, token=JWTISH),
            ]
        },
    )
    listed = cmd_list(hermes_home=hermes_home)
    status = cmd_status(hermes_home=hermes_home)
    assert SECRET not in listed
    assert SECRET not in status
    assert JWTISH not in listed
    assert JWTISH not in status
    assert "one" in listed


def test_use_output_redacts(hermes_home: Path, auth_path: Path):
    write_pool(
        auth_path,
        {
            "demo-provider": [
                fake_entry(entry_id="a", label="one", priority=0, token=SECRET),
                fake_entry(entry_id="b", label="two", priority=1, token=SECRET + "2"),
            ]
        },
    )
    out = cmd_use("two", provider="demo-provider", hermes_home=hermes_home)
    assert SECRET not in out
    assert "two" in out


def test_redact_text_masks_jwt_and_sk():
    text = f"token={JWTISH} key=sk-abcdefghijklmnopqrstuvwxyz0123456789"
    red = redact_text(text)
    assert JWTISH not in red
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in red
