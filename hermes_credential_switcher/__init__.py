"""hermes-credential-switcher — Hermes plugin for operator-owned pool priority.

Complements Hermes native credential pools. Does **not** implement OAuth,
token refresh, or automatic rotation. Public surfaces:

* Slash command: ``/cred``
* Terminal CLI: ``hermes credential``

Enable with::

    hermes plugins enable hermes-credential-switcher

or install via pip (entry point ``hermes_agent.plugins``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__version__ = "0.1.0"
__all__ = ["register", "__version__"]

_PLUGIN_DIR = Path(__file__).resolve().parent
_SKILL_PATH = _PLUGIN_DIR / "skill" / "SKILL.md"


def register(ctx: Any) -> None:
    """Hermes plugin entry — register slash command, CLI subcommand, and skill."""
    from .cli import (
        credential_command,
        setup_credential_parser,
    )
    from .commands import handle_cred_slash

    ctx.register_command(
        name="cred",
        handler=handle_cred_slash,
        description=(
            "List/status/use operator-owned credentials in Hermes credential "
            "pools (priority reorder only; no OAuth)."
        ),
        args_hint="[list|status|use] [provider] [target] [--reset]",
    )

    ctx.register_cli_command(
        name="credential",
        help="Credential pool priority switcher (list/status/use)",
        setup_fn=setup_credential_parser,
        handler_fn=credential_command,
        description=(
            "Operator-owned credential priority helpers. Complements native "
            "Hermes credential pools without reimplementing OAuth or rotation."
        ),
    )

    if _SKILL_PATH.is_file():
        try:
            ctx.register_skill(
                name="credential-switcher",
                path=_SKILL_PATH,
                description=(
                    "How to list, inspect, and switch Hermes credential-pool "
                    "priority with /cred and hermes credential."
                ),
            )
        except Exception:
            # Skill registration is best-effort; commands still work.
            pass
