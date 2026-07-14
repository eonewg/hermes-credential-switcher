# Security Policy

## What this plugin does

`hermes-credential-switcher` reorders **operator-owned** **manual API-key**
entries already present in a Hermes `auth.json` credential pool under
`fill_first`. `list` / `status` are generic for any provider. **0.1.0 fails
closed on `use` for every OAuth credential entry** (all providers) and for
known normalized seeded sources (e.g. Codex `device_code`, Anthropic env/OAuth
seeds), because provider OAuth may require singleton/token-source
synchronization that raw pool reorder cannot guarantee.

It does **not**:

- Implement OAuth or device-code login
- Mutate OAuth pool entries (fail closed)
- Refresh provider tokens
- Automatically rotate credentials on rate limits
- Bypass provider quotas or terms of service
- Encourage or facilitate account sharing / third-party “friend account” pooling
- Claim any-provider runtime activation

Credentials managed through this plugin must be owned or explicitly authorized
by the operator. Provider terms of service apply.

## Sensitive data handling

| Concern | Behavior |
|--------|----------|
| Auth path | `$HERMES_HOME/auth.json` only (profile-safe via `HERMES_HOME`) |
| Locking | Interprocess advisory lock on `$HERMES_HOME/auth.lock` (same sibling lock Hermes uses: `auth.json` → `auth.lock`) |
| Writes | Atomic temp-file replace; mode **0600 or stricter** preserved |
| Rollback | In-memory previous bytes only — **no durable plaintext token backups** |
| Verification | Re-read after write under the same lock |
| Output / logs | Access tokens, refresh tokens, agent keys, and secret-shaped strings are redacted |
| Aliases | User-configured only; no hard-coded account nicknames |
| Session cache | Does **not** touch private Hermes attributes such as `_session_model_overrides` or `_agent_cache` |

## Threat model notes

- **Local multi-process races**: mitigated by file lock + atomic replace + re-read verification.
- **Accidental secret disclosure**: list/status/use formatters never include token fields; redaction also scans free text.
- **Test isolation**: under `PYTEST_CURRENT_TEST`, resolving the real user `~/.hermes/auth.json` raises rather than reading or writing it.
- **Malicious plugins / compromised host**: out of scope — if the host user can read `auth.json`, tokens are already available to that user.

## Reporting vulnerabilities

Please report security issues privately to the repository maintainers (open a
draft security advisory on GitHub if available, or contact the listed owners).
Do **not** attach real `auth.json` files or live tokens to public issues.

## Operator checklist

1. Keep `auth.json` mode `0600` (the plugin preserves stricter modes).
2. Use separate Hermes profiles (`HERMES_HOME`) for hard isolation boundaries.
3. Define aliases only for accounts you own or are authorized to operate.
4. Run `/new` after `use` — current Hermes has no public current-session credential rebind API.
5. Never commit `auth.json`, `.env`, or alias files that embed secrets.
