"""User-configurable credential aliases.

Aliases are **never** hard-coded (no me/zuo/friend defaults). Operators
define them under HERMES_HOME or via Hermes plugin config.

Sources (later overrides earlier):
1. ``$HERMES_HOME/credential-switcher/aliases.json``
2. ``plugins.entries.hermes-credential-switcher.aliases`` in config.yaml
   (when Hermes config is importable)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .paths import aliases_path, get_hermes_home, plugin_state_dir

logger = logging.getLogger(__name__)

PLUGIN_CONFIG_KEY = "hermes-credential-switcher"


@dataclass(frozen=True)
class AliasTarget:
    """Resolved alias destination."""

    target: str
    provider: Optional[str] = None


def _parse_alias_value(value: Any) -> Optional[AliasTarget]:
    if isinstance(value, str):
        text = value.strip()
        return AliasTarget(target=text) if text else None
    if isinstance(value, Mapping):
        target = value.get("target") or value.get("id") or value.get("label")
        if not isinstance(target, str) or not target.strip():
            return None
        provider = value.get("provider")
        prov = str(provider).strip() if provider else None
        return AliasTarget(target=target.strip(), provider=prov or None)
    return None


def load_aliases_file(path: Path) -> Dict[str, AliasTarget]:
    """Load aliases from a JSON file. Missing file → empty map."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring malformed aliases file %s: %s", path, exc)
        return {}
    return _coerce_alias_map(raw)


def _coerce_alias_map(raw: Any) -> Dict[str, AliasTarget]:
    if not isinstance(raw, dict):
        return {}
    # Allow either flat map or {"aliases": {...}}
    body = raw.get("aliases") if isinstance(raw.get("aliases"), dict) else raw
    if not isinstance(body, dict):
        return {}
    out: Dict[str, AliasTarget] = {}
    for key, value in body.items():
        name = str(key).strip()
        if not name or name in {"aliases", "version"}:
            # Skip envelope keys when flat-merged
            if name in {"aliases", "version"} and "aliases" in raw:
                continue
            if name in {"version"}:
                continue
        if name in {"aliases", "version"}:
            continue
        parsed = _parse_alias_value(value)
        if parsed is not None:
            out[name.lower()] = parsed
    return out


def load_config_aliases() -> Dict[str, AliasTarget]:
    """Best-effort read of plugins.entries aliases from Hermes config."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return {}
    plugins = cfg.get("plugins") if isinstance(cfg, dict) else None
    if not isinstance(plugins, dict):
        return {}
    entries = plugins.get("entries") or {}
    if not isinstance(entries, dict):
        return {}
    entry = entries.get(PLUGIN_CONFIG_KEY) or entries.get("credential-switcher") or {}
    if not isinstance(entry, dict):
        return {}
    aliases = entry.get("aliases")
    if aliases is None:
        return {}
    return _coerce_alias_map(aliases if isinstance(aliases, dict) else {"aliases": aliases})


def load_aliases(hermes_home: Optional[Path] = None) -> Dict[str, AliasTarget]:
    """Merge file + config aliases (config wins on key collision)."""
    home = hermes_home or get_hermes_home()
    merged = load_aliases_file(aliases_path(home))
    merged.update(load_config_aliases())
    return merged


def expand_alias(
    token: str,
    aliases: Optional[Mapping[str, AliasTarget]] = None,
    *,
    hermes_home: Optional[Path] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Expand *token* if it is a configured alias.

    Returns ``(resolved_target, provider_or_None, alias_name_or_None)``.
    When *token* is not an alias, returns ``(token, None, None)``.
    """
    raw = (token or "").strip()
    if not raw:
        return raw, None, None
    table = aliases if aliases is not None else load_aliases(hermes_home)
    hit = table.get(raw.lower())
    if hit is None:
        return raw, None, None
    return hit.target, hit.provider, raw


def save_aliases(
    aliases: Mapping[str, AliasTarget],
    *,
    hermes_home: Optional[Path] = None,
) -> Path:
    """Persist aliases to the plugin state file (operator tooling / tests)."""
    home = hermes_home or get_hermes_home()
    path = aliases_path(home)
    plugin_state_dir(home).mkdir(parents=True, exist_ok=True)
    body = {
        "version": 1,
        "aliases": {
            name: (
                {"target": alias.target, "provider": alias.provider}
                if alias.provider
                else alias.target
            )
            for name, alias in aliases.items()
        },
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def format_aliases(aliases: Mapping[str, AliasTarget]) -> str:
    if not aliases:
        return (
            "No aliases configured.\n"
            f"Create {aliases_path()} as JSON, e.g.\n"
            '  {"aliases": {"work": "my-work-label", "backup": '
            '{"provider": "openai-codex", "target": "abc123"}}}\n'
            "Aliases are operator-defined; this plugin never ships hard-coded "
            "account nicknames."
        )
    lines = ["Configured aliases:"]
    for name in sorted(aliases):
        alias = aliases[name]
        if alias.provider:
            lines.append(f"  {name} → {alias.provider}:{alias.target}")
        else:
            lines.append(f"  {name} → {alias.target}")
    return "\n".join(lines)
