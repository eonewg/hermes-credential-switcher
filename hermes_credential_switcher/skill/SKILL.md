---
name: credential-switcher
description: Switch Hermes credential-pool priority via /cred.
version: 0.1.0
author: Hermes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Credentials, Auth, Credential Pool, Priority, Operator]
---

# Credential Switcher Skill

Operator-owned **priority switcher** for Hermes credential pools. Complements
native multi-credential pools with list/status/use helpers. Does **not**
implement OAuth, token refresh, automatic rotation, or current-session rebind.

## When to Use

- Prefer a specific already-authorized **manual API-key** pool entry under **fill_first**
- Secret-safe list/status of pool entries for any provider
- Clear cooldown/exhaustion on one manual entry (`--reset`)
- Do **not** use for OAuth accounts — 0.1.0 fails closed; use native `hermes auth`

## Prerequisites

- Plugin enabled: `hermes plugins enable hermes-credential-switcher`
- Python ≥ 3.11 Hermes runtime
- Operator-owned credentials already in `$HERMES_HOME/auth.json` (via native auth)
- For `use`: provider strategy `fill_first` and a **manual non-OAuth** target
- Optional aliases file: `$HERMES_HOME/credential-switcher/aliases.json`

## How to Run

In-session slash (preferred when chatting with Hermes):

```text
/cred list [provider]
/cred status [provider]
/cred use <target> [--provider NAME] [--reset]
/cred aliases
```

From a Hermes `terminal` session (or any shell where `hermes` is on PATH):

```bash
hermes credential list [provider]
hermes credential status [provider]
hermes credential use <target> [--provider NAME] [--reset]
hermes credential aliases
```

After a successful `use`, start a **new** session with `/new` (or a new chat).
Current Hermes has no public API to rebind credentials on the active session.

## Quick Reference

| Action | Slash | Terminal (`hermes credential …`) |
|--------|-------|-----------------------------------|
| List pools | `/cred list [provider]` | `list [provider]` |
| Health + strategy | `/cred status [provider]` | `status [provider]` |
| Reorder priority | `/cred use <target> …` | `use <target> …` |
| Show aliases | `/cred aliases` | `aliases` |

**Target matching (exact only):** user alias → exact id → exact label → 1-based index.

**Scope:** `list`/`status` = any-provider. `use` = manual API-key entries under `fill_first` only.

## Procedure

1. **Inspect** with `/cred list` or `/cred status` (tokens never printed).
2. Confirm strategy is `fill_first` for the provider; otherwise remediating
   `use` will fail closed with a config hint.
3. **Select** a healthy manual API-key target: `/cred use <label|id|index> [--provider NAME]`.
4. If the target is exhausted/dead and you own the fix: `/cred use <target> --reset`.
5. Run `/new` so a new session rebuilds against the updated pool order.
6. Optional: configure aliases only for accounts you own or are authorized to operate.

## Pitfalls

- **OAuth entries**: 0.1.0 fails closed for **every** OAuth credential (all providers).
  Provider OAuth may need singleton/token-source sync that raw reorder cannot guarantee.
- **Normalized seeds**: Codex `device_code`, Anthropic env/OAuth seeds, and similar
  sources also fail closed on `use`.
- **Non-`fill_first` strategies**: `round_robin` / `random` / `least_used` block `use`.
- **No current-session apply**: disk write only; always `/new` after `use`.
- **Not any-provider activation**: do not claim runtime switch for OAuth/singleton pools.
- **Never** print tokens, market quota bypass, or third-party account pooling.

## Verification

- `/cred list` / `status` show pools without secret fields.
- `use` on a healthy manual API-key entry under `fill_first` reports verified reorder.
- `use` on OAuth or known seeded sources fails closed with a clear remediation.
- After `use`, a **new** session (`/new`) reflects the preferred entry under `fill_first`.
- Real operator `auth.json` is never touched by tests; only `$HERMES_HOME` profiles.
