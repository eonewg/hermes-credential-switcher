"""Command parsing and plugin registration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import hermes_credential_switcher as plugin
from hermes_credential_switcher.cli import setup_credential_parser, credential_command
from hermes_credential_switcher.commands import dispatch_cred, parse_cred_args
from hermes_credential_switcher.service import cmd_list
from tests.helpers import fake_entry, write_pool
import argparse


def test_parse_list_status_use():
    assert parse_cred_args("list")[0] == "list"
    assert parse_cred_args("status demo")[0:2] == ("status", ["demo"])
    action, rest, reset, provider = parse_cred_args("use secondary --reset --provider demo")
    assert action == "use"
    assert rest == ["secondary"]
    assert reset is True
    assert provider == "demo"


def test_parse_use_provider_positional():
    action, rest, reset, provider = parse_cred_args("use demo-provider secondary")
    assert action == "use"
    # provider may be inferred later; positional keeps both
    assert "secondary" in rest or rest[0] == "demo-provider"


def test_dispatch_list(hermes_home: Path, auth_path: Path, two_entry_pool):
    out = dispatch_cred("list", hermes_home=hermes_home)
    assert "demo-provider" in out
    assert "primary" in out
    assert "fake-token" not in out


def test_dispatch_use(hermes_home: Path, auth_path: Path, two_entry_pool):
    out = dispatch_cred("use secondary --provider demo-provider", hermes_home=hermes_home)
    assert out.startswith("✓")


def test_dispatch_help():
    out = dispatch_cred("")
    assert "/cred" in out
    assert "--reset" in out


def test_register_wires_commands_and_skill():
    recorded = {
        "commands": [],
        "cli": [],
        "skills": [],
    }

    class FakeCtx:
        def register_command(self, name, handler, description="", args_hint=""):
            recorded["commands"].append(
                {
                    "name": name,
                    "handler": handler,
                    "description": description,
                    "args_hint": args_hint,
                }
            )

        def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
            recorded["cli"].append(
                {
                    "name": name,
                    "help": help,
                    "setup_fn": setup_fn,
                    "handler_fn": handler_fn,
                    "description": description,
                }
            )

        def register_skill(self, name, path, description=""):
            recorded["skills"].append(
                {"name": name, "path": Path(path), "description": description}
            )

    plugin.register(FakeCtx())

    assert any(c["name"] == "cred" for c in recorded["commands"])
    assert any(c["name"] == "credential" for c in recorded["cli"])
    assert recorded["skills"], "expected bundled skill registration"
    skill = recorded["skills"][0]
    assert skill["path"].name == "SKILL.md"
    assert skill["path"].is_file()

    # Slash handler is callable
    handler = recorded["commands"][0]["handler"]
    text = handler("help")
    assert "list" in text.lower()


def test_cli_parser_and_handler(hermes_home: Path, auth_path: Path, two_entry_pool, capsys):
    parser = argparse.ArgumentParser()
    setup_credential_parser(parser)
    args = parser.parse_args(["list", "demo-provider"])
    rc = credential_command(args)
    assert rc == 0
    captured = capsys.readouterr()
    assert "demo-provider" in captured.out
    assert "fake-token" not in captured.out


def test_cli_use(hermes_home: Path, auth_path: Path, two_entry_pool, capsys):
    parser = argparse.ArgumentParser()
    setup_credential_parser(parser)
    args = parser.parse_args(
        ["use", "secondary", "--provider", "demo-provider"]
    )
    rc = credential_command(args)
    assert rc == 0
    assert "✓" in capsys.readouterr().out
