"""Read Hermes ``credential_pool_strategies`` and gate priority mutations.

Priority reordering is a deterministic selection control **only** under the
``fill_first`` strategy. For ``round_robin`` / ``random`` / ``least_used``,
Hermes selects independently of list order, so this plugin fails closed on
``use`` with a remediation command rather than silently claiming an "active"
selection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import get_hermes_home

logger = logging.getLogger(__name__)

STRATEGY_FILL_FIRST = "fill_first"
STRATEGY_ROUND_ROBIN = "round_robin"
STRATEGY_RANDOM = "random"
STRATEGY_LEAST_USED = "least_used"

SUPPORTED_STRATEGIES = frozenset(
    {
        STRATEGY_FILL_FIRST,
        STRATEGY_ROUND_ROBIN,
        STRATEGY_RANDOM,
        STRATEGY_LEAST_USED,
    }
)

DEFAULT_STRATEGY = STRATEGY_FILL_FIRST


class StrategyError(Exception):
    """Pool strategy blocks a deterministic priority mutation."""


def _load_config_dict(hermes_home: Optional[Path] = None) -> Dict[str, Any]:
    """Load Hermes config for the active home without requiring Hermes imports.

    Prefer Hermes ``load_config()`` when importable (respects its resolution
    rules). Fall back to ``$HERMES_HOME/config.yaml`` YAML parse.
    """
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass

    home = hermes_home or get_hermes_home()
    path = home / "config.yaml"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import yaml  # type: ignore

        raw = yaml.safe_load(text)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    # Minimal fallback: only parse credential_pool_strategies block if PyYAML
    # is unavailable (stdlib-only). Enough for strategy keys used by this plugin.
    return _parse_strategies_lite(text)


def _parse_strategies_lite(text: str) -> Dict[str, Any]:
    """Very small YAML subset parser for credential_pool_strategies mapping."""
    lines = text.splitlines()
    in_block = False
    strategies: Dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("credential_pool_strategies:"):
            in_block = True
            rest = stripped.split(":", 1)[1].strip()
            if rest and rest not in {"{}", "null", "~"}:
                # inline map not supported in lite parser
                pass
            continue
        if in_block:
            if line and not line[0].isspace() and not line.startswith("\t"):
                break
            if ":" not in stripped:
                continue
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and val:
                strategies[key] = val
    return {"credential_pool_strategies": strategies} if strategies else {}


def get_pool_strategy(
    provider: str,
    *,
    hermes_home: Optional[Path] = None,
) -> str:
    """Return the configured strategy for *provider* (default ``fill_first``)."""
    cfg = _load_config_dict(hermes_home)
    strategies = cfg.get("credential_pool_strategies")
    if not isinstance(strategies, dict):
        return DEFAULT_STRATEGY
    raw = strategies.get(provider, "")
    strategy = str(raw or "").strip().lower()
    if strategy in SUPPORTED_STRATEGIES:
        return strategy
    return DEFAULT_STRATEGY


def require_fill_first_for_use(
    provider: str,
    *,
    hermes_home: Optional[Path] = None,
) -> str:
    """Return the strategy when it is fill_first; else raise StrategyError.

    Remediation points operators at Hermes native strategy configuration.
    """
    strategy = get_pool_strategy(provider, hermes_home=hermes_home)
    if strategy == STRATEGY_FILL_FIRST:
        return strategy
    raise StrategyError(
        f"Provider '{provider}' uses credential pool strategy '{strategy}'. "
        "Priority reorder only deterministically controls selection under "
        f"'{STRATEGY_FILL_FIRST}'. Under '{strategy}', Hermes chooses entries "
        "by rotation/usage/random rules, so this plugin refuses to claim an "
        "active selection. Remediation: set "
        f"`credential_pool_strategies.{provider}: {STRATEGY_FILL_FIRST}` in "
        "config.yaml (or run `hermes auth` → Set rotation strategy), then "
        "retry `/cred use`."
    )


def strategy_status_line(
    provider: str,
    strategy: str,
) -> str:
    if strategy == STRATEGY_FILL_FIRST:
        return (
            f"Strategy [{provider}]: {strategy} — priority 0 is the preferred "
            "healthy entry (deterministic under fill_first)."
        )
    return (
        f"Strategy [{provider}]: {strategy} — priority order is NOT the active "
        f"selector; use is blocked until strategy is {STRATEGY_FILL_FIRST}."
    )
