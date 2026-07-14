"""Exact target matching for pool entries.

Resolution order for a target string (after optional alias expansion):

1. Exact ``id`` match (case-sensitive)
2. Exact ``label`` match (case-insensitive, full string only — no substring)
3. 1-based numeric index

Ambiguous multi-matches raise with a clear operator message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class MatchResult:
    index: int  # 0-based
    entry: Dict[str, Any]
    matched_by: str  # "id" | "label" | "index" | "alias"


class MatchError(ValueError):
    """Target could not be resolved uniquely."""


def resolve_target(
    entries: Sequence[Dict[str, Any]],
    target: str,
    *,
    matched_via_alias: Optional[str] = None,
) -> MatchResult:
    """Resolve *target* against *entries*.

    Parameters
    ----------
    entries:
        Provider pool entries in current order.
    target:
        Exact id, exact label, or 1-based index (as decimal digits).
    matched_via_alias:
        If set, recorded in the result for messaging (alias already expanded).
    """
    raw = (target or "").strip()
    if not raw:
        raise MatchError("No credential target provided.")

    # 1) Exact id (case-sensitive)
    id_matches = [
        (i, e)
        for i, e in enumerate(entries)
        if str(e.get("id") or "") == raw
    ]
    if len(id_matches) == 1:
        i, e = id_matches[0]
        return MatchResult(
            index=i,
            entry=dict(e),
            matched_by="alias" if matched_via_alias else "id",
        )
    if len(id_matches) > 1:
        raise MatchError(
            f'Ambiguous credential id "{raw}". '
            "Duplicate ids in the pool — fix auth.json or use a 1-based index."
        )

    # 2) Exact label (case-insensitive, full-string only)
    label_matches = [
        (i, e)
        for i, e in enumerate(entries)
        if str(e.get("label") or "").strip().lower() == raw.lower()
    ]
    if len(label_matches) == 1:
        i, e = label_matches[0]
        return MatchResult(
            index=i,
            entry=dict(e),
            matched_by="alias" if matched_via_alias else "label",
        )
    if len(label_matches) > 1:
        raise MatchError(
            f'Ambiguous credential label "{raw}". '
            "Use the exact id or 1-based index instead."
        )

    # 3) 1-based index (digits only — do not treat ids that are numeric-looking
    #    with non-digit chars as indices; pure digit strings are indices when
    #    no id/label matched).
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(entries):
            e = entries[index - 1]
            return MatchResult(
                index=index - 1,
                entry=dict(e),
                matched_by="alias" if matched_via_alias else "index",
            )
        raise MatchError(
            f"No credential #{index} (pool has {len(entries)} entr"
            f"{'y' if len(entries) == 1 else 'ies'})."
        )

    raise MatchError(
        f'No credential matching "{raw}". '
        "Use exact label, exact id, or 1-based index."
    )


def list_providers(pool: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    return sorted(pool.keys())


def infer_provider(
    pool: Dict[str, List[Dict[str, Any]]],
    *,
    provider: Optional[str],
    target: Optional[str] = None,
) -> str:
    """Pick a provider when the operator omitted it.

    Rules:
    * Explicit provider wins.
    * If exactly one provider has entries, use it.
    * If *target* uniquely matches across all pools, use that provider.
    * Otherwise raise MatchError asking the operator to specify provider.
    """
    if provider:
        if provider not in pool or not pool[provider]:
            raise MatchError(f"No credential pool entries for provider '{provider}'.")
        return provider

    non_empty = {k: v for k, v in pool.items() if v}
    if not non_empty:
        raise MatchError("No credential pool entries found in auth.json.")
    if len(non_empty) == 1:
        return next(iter(non_empty))

    if target:
        hits: List[Tuple[str, MatchResult]] = []
        for prov, entries in non_empty.items():
            try:
                hits.append((prov, resolve_target(entries, target)))
            except MatchError:
                continue
        if len(hits) == 1:
            return hits[0][0]
        if len(hits) > 1:
            names = ", ".join(p for p, _ in hits)
            raise MatchError(
                f'Target "{target}" matches multiple providers ({names}). '
                "Pass an explicit provider."
            )

    names = ", ".join(sorted(non_empty))
    raise MatchError(
        f"Multiple providers have credentials ({names}). "
        "Pass an explicit provider."
    )
