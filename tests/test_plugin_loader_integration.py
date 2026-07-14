"""Isolated integration test against the real Hermes plugin loader.

CI sets ``HERMES_AGENT_SOURCE`` after checking out NousResearch/hermes-agent.
The loader runs in a subprocess with a temporary ``HERMES_HOME`` so this test
cannot mutate the parent pytest process or the operator's real auth state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _has_hermes_plugins(path: Path) -> bool:
    return path.is_dir() and (path / "hermes_cli" / "plugins.py").is_file()


def resolve_hermes_agent_source() -> Optional[Path]:
    """Locate Hermes source without hard-coding a local user home."""
    env = (os.environ.get("HERMES_AGENT_SOURCE") or "").strip()
    if env:
        candidate = Path(env).expanduser()
        return candidate.resolve() if _has_hermes_plugins(candidate) else None

    for relative in (Path(".ci") / "hermes-agent", Path("hermes-agent")):
        candidate = (PLUGIN_ROOT / relative).resolve()
        if _has_hermes_plugins(candidate):
            return candidate

    sibling = (PLUGIN_ROOT.parent / "hermes-agent").resolve()
    return sibling if _has_hermes_plugins(sibling) else None


@pytest.fixture()
def isolated_hermes_home(tmp_path: Path) -> Path:
    home = tmp_path / "hermes-home"
    plugins = home / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "hermes-credential-switcher").symlink_to(
        PLUGIN_ROOT, target_is_directory=True
    )
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - hermes-credential-switcher\n",
        encoding="utf-8",
    )
    (home / "auth.json").write_text(
        '{"version": 1, "providers": {}, "credential_pool": {}}\n',
        encoding="utf-8",
    )
    return home


def test_hermes_plugin_loader_registers_slash_and_cli(
    isolated_hermes_home: Path,
):
    hermes_src = resolve_hermes_agent_source()
    if hermes_src is None:
        pytest.skip(
            "Hermes source unavailable (set HERMES_AGENT_SOURCE or use .ci/hermes-agent)"
        )

    probe = r'''
import argparse
import importlib.abc
import json
import os
import sys
from pathlib import Path

hermes_src = Path(sys.argv[1]).resolve()
hermes_home = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(hermes_src))
os.chdir(hermes_home)

class BlockTopLevelPluginImport(importlib.abc.MetaPathFinder):
    """Prove directory loading does not depend on a pip/editable install."""
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hermes_credential_switcher" or fullname.startswith(
            "hermes_credential_switcher."
        ):
            raise ModuleNotFoundError(
                "top-level hermes_credential_switcher blocked by integration probe"
            )
        return None

sys.meta_path.insert(0, BlockTopLevelPluginImport())

import hermes_cli.plugins as plugins_mod
plugins_mod._plugin_manager = None
empty_bundled = hermes_home / "empty-bundled"
empty_bundled.mkdir()
plugins_mod.get_bundled_plugins_dir = lambda: empty_bundled

mgr = plugins_mod.PluginManager()
mgr._scan_entry_points = lambda: []
mgr.discover_and_load(force=True)
loaded = mgr._plugins.get("hermes-credential-switcher")
assert loaded is not None, list(mgr._plugins)
assert loaded.enabled is True, loaded.error
assert not loaded.error, loaded.error

slash = mgr._plugin_commands["cred"]
help_text = slash["handler"]("help")
assert "list" in help_text.lower()

cli = mgr._cli_commands["credential"]
parser = argparse.ArgumentParser()
cli["setup_fn"](parser)
args = parser.parse_args(["list"])
assert cli["handler_fn"](args) == 0

print(json.dumps({
    "plugin": loaded.manifest.name,
    "slash": "cred" in mgr._plugin_commands,
    "cli": "credential" in mgr._cli_commands,
    "auth_path": str(hermes_home / "auth.json"),
}))
'''

    env = os.environ.copy()
    env["HERMES_HOME"] = str(isolated_hermes_home)
    env["PYTEST_CURRENT_TEST"] = "plugin_loader_subprocess"
    env.pop("HERMES_SAFE_MODE", None)
    completed = subprocess.run(
        [sys.executable, "-c", probe, str(hermes_src), str(isolated_hermes_home)],
        cwd=isolated_hermes_home,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["plugin"] == "hermes-credential-switcher"
    assert payload["slash"] is True
    assert payload["cli"] is True
    assert Path(payload["auth_path"]).resolve() == (
        isolated_hermes_home / "auth.json"
    ).resolve()
    assert isolated_hermes_home.resolve() != (Path.home() / ".hermes").resolve()
