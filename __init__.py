"""Directory-plugin shim for ``~/.hermes/plugins/hermes-credential-switcher/``.

Hermes loads ``register(ctx)`` from this package root when the repo is
cloned or copied into the user plugins directory. Pip installs use the
``hermes_agent.plugins`` entry point on ``hermes_credential_switcher`` instead.

Loaded by Hermes as a package (``hermes_plugins.<slug>`` with
``submodule_search_locations``), so the implementation package is imported
relatively — no global ``sys.path`` mutation. Absolute import is only a
fallback when this file is loaded without package context (e.g. pytest
collecting the repo root).
"""

from __future__ import annotations

if __package__:
    from .hermes_credential_switcher import __version__, register
else:  # pragma: no cover - direct/non-package loaders
    from hermes_credential_switcher import __version__, register

__all__ = ["register", "__version__"]
