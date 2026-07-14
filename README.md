# hermes-credential-switcher

Standalone open-source **Hermes plugin** for operator-owned **credential pool priority** switching.

It **complements** Hermes native multi-credential pools. It does **not** reimplement OAuth, device-code login, token refresh, or automatic rotation.

| Surface | Command |
|--------|---------|
| In-session slash | `/cred` |
| Terminal CLI | `hermes credential` |

Repository: [https://github.com/eonewg/hermes-credential-switcher](https://github.com/eonewg/hermes-credential-switcher)

## What it is (and is not)

**Is**

- **List / status** helpers for **any** provider’s `credential_pool` entries in `auth.json`
- **Use** (priority reorder) for **manual non-OAuth / API-key** pool entries under **`fill_first`**
- Exact target selection by **label**, **id**, or **1-based index**
- Optional **user-configured** aliases
- Safe on-disk updates: profile-aware paths, interprocess lock, atomic replace, mode `0600` or stricter, re-read verification
- Secret-safe operator output (tokens never printed)

**Is not**

- Any-provider runtime activation or “switch any OAuth account”
- A quota-bypass tool
- An account-sharing or “friend account pool” product
- A replacement for `hermes auth` / provider login flows
- A private-API session monkeypatcher (`_session_model_overrides`, `_agent_cache`, etc. are off-limits)

Credentials must be **operator-owned or explicitly authorized**. Provider terms of service apply.

## Install

### Option A — user plugin directory

```bash
git clone https://github.com/eonewg/hermes-credential-switcher ~/.hermes/plugins/hermes-credential-switcher
hermes plugins enable hermes-credential-switcher
```

### Option B — pip entry point

```bash
pip install .
# discovers via [project.entry-points."hermes_agent.plugins"]
hermes plugins enable hermes-credential-switcher
```

Restart Hermes (or reload plugins) after enabling.

## Usage

```text
/cred list [provider]
/cred status [provider]
/cred use <target> [--provider NAME] [--reset]
/cred aliases

hermes credential list [provider]
hermes credential status [provider]
hermes credential use <target> [--provider NAME] [--reset]
hermes credential aliases
```

### Target matching

Exact match only, in order:

1. User alias (if configured)
2. Exact credential `id`
3. Exact credential `label` (case-insensitive full string)
4. 1-based index from `list` / `status`

Ambiguous matches fail with a clear error (use id or index).

### `use` semantics

| Invocation | Behavior |
|-----------|----------|
| `use <target>` | Reorder only: selected entry → priority `0`. **Requires** `fill_first`. **Fails** if target is unhealthy, strategy is non-`fill_first`, target is **OAuth** (any provider), or target is a known-unsafe normalized seeded source. |
| `use <target> --reset` | Clear **only that target’s** cooldown/exhaustion fields, then reorder (same gates). |

Other entries are left untouched. No OAuth side effects. Manual API-key entries under `fill_first` remain supported.

### Pool strategy (`credential_pool_strategies`)

Hermes strategies live in `config.yaml`:

```yaml
credential_pool_strategies:
  openrouter: fill_first   # default; only mode where priority 0 is deterministic
  # anthropic: round_robin
```

- **`fill_first` (default)**: priority reorder is a deterministic preference signal.
- **`round_robin` / `random` / `least_used`**: this plugin **fails closed** on `use` and does **not** claim active selection. Remediation: set the provider strategy to `fill_first` (config.yaml or `hermes auth` → Set rotation strategy).

`list` / `status` report the configured strategy and only mark “selected” under `fill_first`.

### Health rules

- Explicit `exhausted` / `dead` → unhealthy.
- Env / keyring / Vault / fingerprint **reference-only** entries are **not** unhealthy merely because no raw token is persisted.
- Missing runtime material is unhealthy only for **manual** secret entries without a recognized external reference/fingerprint.

### Aliases (user-defined only)

This plugin **never** ships hard-coded nicknames. Create:

```json
// $HERMES_HOME/credential-switcher/aliases.json
{
  "version": 1,
  "aliases": {
    "work": "my-work-label",
    "backup": { "provider": "openrouter", "target": "abc123" }
  }
}
```

Or under Hermes config:

```yaml
plugins:
  enabled:
    - hermes-credential-switcher
  entries:
    hermes-credential-switcher:
      aliases:
        work: my-work-label
```

### Profiles and paths

All paths honor `HERMES_HOME` (Hermes profiles included):

- Auth store: `$HERMES_HOME/auth.json`
- Lock: `$HERMES_HOME/auth.lock`
- Aliases: `$HERMES_HOME/credential-switcher/aliases.json`

### Current session vs new session

Current Hermes has **no public API** to rebind credentials on the active session. Selection is written to the pool and **applies after `/new`** (or a new chat). The plugin reports this explicitly. It will not reach into private session overrides or agent caches.

## Compatibility caveat (important)

> **This plugin only reorders `credential_pool` in `auth.json`.**
>
> **0.1.0 fails closed on `use` for every OAuth credential entry (all providers)** and for known normalized seeded sources (notably Codex `device_code` singleton sync and Anthropic env/OAuth seed ranking). Provider OAuth state may require singleton/token-source synchronization that raw pool reorder cannot guarantee.
>
> `list` / `status` remain generic (any-provider). `use` supports **manual API-key** entries under **`fill_first`** only. Prefer Hermes native `hermes auth` for OAuth and normalized seeds.
>
> This is **not** any-provider runtime activation.

## Safety properties

- Interprocess file lock around read-modify-write (`auth.lock`)
- Atomic replace of `auth.json`
- Preserve mode **0600 or stricter**
- Failure rollback via **in-memory** previous bytes only (no durable plaintext token backups on disk)
- Post-write re-read verification
- Redacted list/status/use output

See [SECURITY.md](./SECURITY.md).

## Bundled skill

On load the plugin registers a read-only skill via `ctx.register_skill` (qualified name `hermes-credential-switcher:credential-switcher`). Load it with Hermes `skill_view` when you want operator guidance in-session.

## Roadmap

- **Native switch delegation**: once upstream Hermes lands operator credential-switch support (e.g. [PR #45513](https://github.com/NousResearch/hermes-agent/pull/45513) or an equivalent), this plugin should **delegate** to the native `hermes auth switch` (or successor) path instead of maintaining a parallel mutation surface where core covers it.
- **Stable session context only**: consume a **public** current-session / credential-rebind API only after a core public surface exists in that direction (see existing work such as [PR #42416](https://github.com/NousResearch/hermes-agent/pull/42416)). **Never** private monkeypatch (`_session_model_overrides`, `_agent_cache`, or other non-public attributes).
- **0.1.0 intentionally blocks OAuth mutation**: every OAuth entry and known normalized seeded sources fail closed on `use`; list/status stay generic; manual API-key pools under `fill_first` remain the supported mutation scope until safer core APIs exist.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
python -m compileall hermes_credential_switcher tests
```

Requires **Python ≥ 3.11**. Tests use **fake fixtures only**. They never read or write a real `~/.hermes/auth.json`.

For the real Hermes plugin-loader integration test, set:

```bash
export HERMES_AGENT_SOURCE=/path/to/hermes-agent   # must contain hermes_cli/plugins.py
pytest tests/test_plugin_loader_integration.py
```

CI checks out `NousResearch/hermes-agent` into `.ci/hermes-agent` and sets `HERMES_AGENT_SOURCE` automatically. Do not hard-code local user home paths in tests or docs.

## License

MIT — see [LICENSE](./LICENSE).
