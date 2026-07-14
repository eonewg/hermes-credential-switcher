"""Terminal CLI: ``hermes credential …``."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Optional, Sequence

from .commands import HELP_TEXT, dispatch_cred
from .service import CommandError, cmd_aliases, cmd_list, cmd_status, cmd_use


def setup_credential_parser(parser: argparse.ArgumentParser) -> None:
    """Populate the ``hermes credential`` subparser (plugin API setup_fn)."""
    sub = parser.add_subparsers(dest="credential_command")

    p_list = sub.add_parser("list", help="List credential pool entries (secret-safe)")
    p_list.add_argument("provider", nargs="?", default=None, help="Optional provider id")

    p_status = sub.add_parser("status", help="Show health and selection status")
    p_status.add_argument("provider", nargs="?", default=None, help="Optional provider id")

    p_use = sub.add_parser(
        "use",
        help="Reorder pool priority so target is preferred (fill_first priority 0)",
    )
    p_use.add_argument(
        "target",
        help="Exact label, exact id, 1-based index, or configured alias",
    )
    p_use.add_argument(
        "--provider",
        default=None,
        help="Provider id when multiple pools exist",
    )
    p_use.add_argument(
        "--reset",
        action="store_true",
        help="Clear only the target's cooldown/exhaustion fields before use",
    )

    sub.add_parser("aliases", help="Show user-configured aliases")
    sub.add_parser("help", help="Show credential command help")


def credential_command(args: Any) -> int:
    """Handler for ``hermes credential`` (plugin API handler_fn)."""
    cmd = getattr(args, "credential_command", None) or "help"
    try:
        if cmd in {None, "help"}:
            text = HELP_TEXT.replace("/cred", "hermes credential")
            print(text)
            return 0
        if cmd == "list":
            print(cmd_list(provider=getattr(args, "provider", None)))
            return 0
        if cmd == "status":
            print(cmd_status(provider=getattr(args, "provider", None)))
            return 0
        if cmd == "aliases":
            print(cmd_aliases())
            return 0
        if cmd == "use":
            print(
                cmd_use(
                    getattr(args, "target", ""),
                    provider=getattr(args, "provider", None),
                    reset=bool(getattr(args, "reset", False)),
                )
            )
            return 0
        print(HELP_TEXT.replace("/cred", "hermes credential"))
        return 0
    except CommandError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"✗ Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Standalone CLI entry for local testing (``python -m hermes_credential_switcher``)."""
    parser = argparse.ArgumentParser(
        prog="hermes-credential-switcher",
        description="Operator-owned Hermes credential pool priority switcher",
    )
    setup_credential_parser(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "credential_command", None):
        # Fall back to free-form dispatch for convenience.
        if argv:
            print(dispatch_cred(" ".join(argv)))
            return 0
        print(HELP_TEXT.replace("/cred", "hermes credential"))
        return 0
    return credential_command(args)
