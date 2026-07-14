"""High-level list / status / use operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .aliases import expand_alias, format_aliases, load_aliases
from .compat import (
    MutationCompatibilityError,
    compatibility_caveat_lines,
    require_mutation_allowed,
)
from .matching import MatchError, infer_provider, resolve_target
from .redact import format_entry_line, redact_text
from .session import new_session_apply_message, public_api_status_lines
from .strategy import (
    StrategyError,
    get_pool_strategy,
    require_fill_first_for_use,
    strategy_status_line,
)
from .store import (
    NotFoundError,
    StoreError,
    UnhealthyCredentialError,
    VerificationError,
    clear_target_cooldown,
    entry_is_healthy,
    mutate_pool,
    read_pools,
    reorder_priority,
)


class CommandError(Exception):
    """User-facing command failure (already secret-safe)."""


def _format_provider_block(
    provider: str,
    entries: Sequence[Dict[str, Any]],
    *,
    mark_selected: bool = True,
) -> List[str]:
    lines = [f"[{provider}] ({len(entries)} entr{'y' if len(entries) == 1 else 'ies'})"]
    if not entries:
        lines.append("  (empty)")
        return lines
    for display_idx, entry in enumerate(entries, start=1):
        lines.append(
            "  "
            + format_entry_line(
                entry,
                index=display_idx,
                selected=(mark_selected and display_idx == 1),
            )
        )
    return lines


def cmd_list(
    *,
    provider: Optional[str] = None,
    hermes_home: Optional[Path] = None,
) -> str:
    try:
        auth_path, pool = read_pools(hermes_home=hermes_home, provider=provider)
    except StoreError as exc:
        raise CommandError(str(exc)) from exc
    if provider and provider not in pool:
        raise CommandError(f"No credential pool entries for provider '{provider}'.")
    if not pool:
        return (
            f"No credential pool entries found in {auth_path}.\n"
            "Add credentials with Hermes native auth (`hermes auth add` / login) first."
        )
    lines = [f"Credential pools ({auth_path}):"]
    for prov in sorted(pool):
        strategy = get_pool_strategy(prov, hermes_home=hermes_home)
        lines.append(strategy_status_line(prov, strategy))
        # Only claim a preference marker under fill_first.
        lines.extend(
            _format_provider_block(
                prov, pool[prov], mark_selected=(strategy == "fill_first")
            )
        )
    lines.append("")
    lines.append(
        "Use: /cred use <target> [--provider NAME] [--reset]  "
        "or  hermes credential use <target> ..."
    )
    lines.append(
        "Note: priority reorder is deterministic only under fill_first; "
        "list is generic and does not claim active selection for other strategies."
    )
    return "\n".join(lines)


def cmd_status(
    *,
    provider: Optional[str] = None,
    hermes_home: Optional[Path] = None,
) -> str:
    try:
        auth_path, pool = read_pools(hermes_home=hermes_home, provider=provider)
    except StoreError as exc:
        raise CommandError(str(exc)) from exc
    if provider and provider not in pool:
        raise CommandError(f"No credential pool entries for provider '{provider}'.")
    if not pool:
        return f"No credential pool entries found in {auth_path}."

    lines = [f"Credential status ({auth_path}):"]
    total = 0
    unhealthy = 0
    for prov in sorted(pool):
        entries = pool[prov]
        total += len(entries)
        strategy = get_pool_strategy(prov, hermes_home=hermes_home)
        lines.append(f"[{prov}]")
        lines.append(f"  {strategy_status_line(prov, strategy)}")
        for idx, entry in enumerate(entries, start=1):
            healthy, reason = entry_is_healthy(entry)
            if not healthy:
                unhealthy += 1
            flag = "healthy" if healthy else f"UNHEALTHY ({reason})"
            # Do not mark index-1 as "selected" unless fill_first (order is
            # only a preference signal under that strategy).
            selected = strategy == "fill_first" and idx == 1
            lines.append(
                "  "
                + format_entry_line(entry, index=idx, selected=selected)
                + f" · {flag}"
            )
    lines.append("")
    lines.append(f"Summary: {total} total, {unhealthy} unhealthy.")
    lines.extend(public_api_status_lines())
    lines.extend(compatibility_caveat_lines())
    aliases = load_aliases(hermes_home)
    if aliases:
        lines.append(f"Aliases configured: {len(aliases)} (see /cred aliases).")
    else:
        lines.append("Aliases: none configured (user-defined only).")
    return "\n".join(lines)


def cmd_aliases(*, hermes_home: Optional[Path] = None) -> str:
    return format_aliases(load_aliases(hermes_home))


def cmd_use(
    target: str,
    *,
    provider: Optional[str] = None,
    reset: bool = False,
    hermes_home: Optional[Path] = None,
) -> str:
    """Promote *target* to priority 0.

    Plain use reorders only and fails clearly when the target is unhealthy,
    the pool strategy is not fill_first, the target is OAuth (any provider),
    or the target is a known-unsafe provider-normalized seeded source.
    ``reset=True`` clears only that target's cooldown/exhaustion fields
    before the health check and reorder. Manual API-key entries under
    fill_first remain supported.
    """
    if not (target or "").strip():
        raise CommandError(
            "Missing target. Usage: use <label|id|index> [--provider NAME] [--reset]"
        )

    aliases = load_aliases(hermes_home)
    resolved_target, alias_provider, alias_name = expand_alias(
        target, aliases, hermes_home=hermes_home
    )
    effective_provider = provider or alias_provider

    _auth_path, pool = read_pools(hermes_home=hermes_home)
    try:
        prov = infer_provider(
            pool, provider=effective_provider, target=resolved_target
        )
    except MatchError as exc:
        raise CommandError(str(exc)) from exc

    try:
        require_fill_first_for_use(prov, hermes_home=hermes_home)
    except StrategyError as exc:
        raise CommandError(str(exc)) from exc

    def mutator(entries: List[Dict[str, Any]]):
        try:
            match = resolve_target(
                entries,
                resolved_target,
                matched_via_alias=alias_name,
            )
        except MatchError as exc:
            raise NotFoundError(str(exc)) from exc

        working = [dict(e) for e in entries]
        selected = dict(working[match.index])

        try:
            require_mutation_allowed(prov, selected)
        except MutationCompatibilityError as exc:
            raise StoreError(str(exc)) from exc

        if reset:
            selected = clear_target_cooldown(selected)
            working[match.index] = selected

        healthy, reason = entry_is_healthy(selected)
        if not healthy:
            raise UnhealthyCredentialError(
                f"Credential is unhealthy ({reason}). "
                "Plain use only reorders priority and refuses unhealthy "
                "targets. Re-run with --reset to clear this target's "
                "cooldown/exhaustion fields, or fix the credential via "
                "Hermes native auth."
            )

        reordered = reorder_priority(working, match.index)
        selected = reordered[0]
        label = selected.get("label") or selected.get("id") or resolved_target
        via = f" (alias '{alias_name}')" if alias_name else ""
        reset_note = (
            " Cooldown/exhaustion fields cleared for target." if reset else ""
        )
        msg = (
            f"Selected `{label}` for provider '{prov}'{via}; "
            f"priority reordered to 0 under fill_first.{reset_note}"
        )
        return reordered, selected, msg

    def verify_fn(
        verified_entries: List[Dict[str, Any]],
        selected: Optional[Dict[str, Any]],
    ) -> None:
        if not selected:
            raise VerificationError("missing selected entry")
        selected_id = selected.get("id")
        if not verified_entries:
            raise VerificationError("verified pool empty")
        head = verified_entries[0]
        if head.get("id") != selected_id:
            raise VerificationError(
                f"head id {head.get('id')!r} != selected {selected_id!r}"
            )
        pri = head.get("priority")
        if pri is not None and pri != 0 and pri != "0":
            raise VerificationError(f"head priority {pri!r} != 0")
        if reset:
            for key in (
                "last_status",
                "last_status_at",
                "last_error_code",
                "last_error_reason",
                "last_error_message",
                "last_error_reset_at",
            ):
                if key in head and head[key] is not None:
                    raise VerificationError(
                        f"{key} not cleared after --reset (still {head[key]!r})"
                    )

    try:
        result = mutate_pool(
            hermes_home=hermes_home,
            provider=prov,
            mutator=mutator,
            verify=verify_fn,
        )
    except UnhealthyCredentialError as exc:
        raise CommandError(str(exc)) from exc
    except NotFoundError as exc:
        raise CommandError(str(exc)) from exc
    except StoreError as exc:
        raise CommandError(f"Credential switch failed: {exc}") from exc

    lines = [
        f"✓ {result.message}",
        f"Auth store: {result.auth_path}",
        "Verified: priority write-back re-read ✓",
        new_session_apply_message(),
        "",
    ]
    lines.extend(compatibility_caveat_lines())
    lines.append("")
    lines.extend(
        _format_provider_block(prov, result.entries, mark_selected=True)
    )
    return redact_text("\n".join(lines))
