"""Slash-command (`/cred`) and shared argument parsing."""

from __future__ import annotations

import shlex
from typing import List, Optional, Tuple

from .service import (
    CommandError,
    cmd_aliases,
    cmd_list,
    cmd_status,
    cmd_use,
)

HELP_TEXT = """\
/cred — credential pool priority switcher (v0.1.0)

Commands:
  /cred list [provider]              List pool entries (secret-safe)
  /cred status [provider]            Health + strategy status
  /cred use <target> [options]       Reorder priority (fill_first only)
  /cred aliases                      Show user-configured aliases

Options for use:
  --provider <name>   Provider id when multiple pools exist
  --reset             Clear only the target's cooldown/exhaustion fields

Target matching (exact only):
  • exact credential id
  • exact credential label
  • 1-based index (as shown in list)
  • user-configured alias (never hard-coded)

Examples:
  /cred list
  /cred status openrouter
  /cred use work --provider openrouter
  /cred use 2 --reset

Notes:
  • Complements Hermes native credential pools; does not do OAuth or rotation.
  • Credentials must be operator-owned and authorized; provider terms apply.
  • Priority reorder is deterministic ONLY under fill_first. Other strategies
    fail closed on use (set credential_pool_strategies.<provider>: fill_first).
  • Selection is stored on disk and applies after /new (no public current-
    session rebind API on current Hermes).
  • list/status are any-provider; use is manual non-OAuth pools under fill_first.
  • 0.1.0 fails closed on use for every OAuth entry and known normalized
    seeded sources (Codex device_code, Anthropic env/OAuth seeds, etc.).
"""


def parse_cred_args(raw_args: str) -> Tuple[str, List[str], bool, Optional[str]]:
    """Parse slash/CLI free-form args.

    Returns ``(action, positional, reset, provider)``.
    """
    text = (raw_args or "").strip()
    if not text:
        return "help", [], False, None

    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()

    reset = False
    provider: Optional[str] = None
    positional: List[str] = []
    i = 0
    while i < len(parts):
        tok = parts[i]
        if tok in {"--reset", "--reset-target"}:
            reset = True
            i += 1
            continue
        if tok == "--provider" and i + 1 < len(parts):
            provider = parts[i + 1]
            i += 2
            continue
        if tok.startswith("--provider="):
            provider = tok.split("=", 1)[1]
            i += 1
            continue
        if tok in {"-h", "--help", "help"}:
            return "help", [], False, None
        positional.append(tok)
        i += 1

    if not positional:
        return "help", [], reset, provider

    action = positional[0].lower()
    rest = positional[1:]

    # Allow `/cred <provider>` as list shorthand when first token is not a verb.
    verbs = {"list", "ls", "status", "use", "select", "aliases", "alias", "help"}
    if action not in verbs:
        # `/cred openai-codex` → list that provider
        # `/cred 2` or `/cred mylabel` → use target (if looks like use)
        # Prefer list when token contains '/' or known as provider-like with no more args
        if not rest and not reset:
            # Ambiguous: treat non-verb single token as list filter if it has
            # no digits-only form... Actually operator mental model from
            # prototype: bare target means use. Keep that.
            return "use", [action], reset, provider
        if rest and not reset and rest[0] not in {"--reset"}:
            # `/cred openai-codex work` → use with provider
            return "use", rest, reset, action
        return "use", [action] + rest, reset, provider

    if action in {"ls"}:
        action = "list"
    if action in {"select"}:
        action = "use"
    if action in {"alias"}:
        action = "aliases"
    return action, rest, reset, provider


def dispatch_cred(
    raw_args: str,
    *,
    hermes_home=None,
) -> str:
    """Dispatch a `/cred` or shared CLI invocation; returns operator text."""
    action, rest, reset, provider = parse_cred_args(raw_args)

    try:
        if action == "help":
            return HELP_TEXT
        if action == "list":
            prov = provider or (rest[0] if rest else None)
            return cmd_list(provider=prov, hermes_home=hermes_home)
        if action == "status":
            prov = provider or (rest[0] if rest else None)
            return cmd_status(provider=prov, hermes_home=hermes_home)
        if action == "aliases":
            return cmd_aliases(hermes_home=hermes_home)
        if action == "use":
            if not rest:
                raise CommandError(
                    "Missing target. Usage: use <label|id|index> "
                    "[--provider NAME] [--reset]"
                )
            # Support: use <provider> <target>
            target = rest[0]
            if len(rest) >= 2 and provider is None:
                # Could be `use openai-codex work` or `use work`
                # If two tokens, first may be provider.
                # Heuristic: if first token equals a known pool provider, treat as provider.
                from .store import read_pools

                _path, pool = read_pools(hermes_home=hermes_home)
                if rest[0] in pool:
                    provider = rest[0]
                    target = rest[1]
                else:
                    target = rest[0]
            return cmd_use(
                target,
                provider=provider,
                reset=reset,
                hermes_home=hermes_home,
            )
        return HELP_TEXT
    except CommandError as exc:
        return f"✗ {exc}"


def handle_cred_slash(raw_args: str) -> str:
    """Hermes slash-command handler: ``fn(raw_args: str) -> str``."""
    return dispatch_cred(raw_args or "")
