# Configuration

AgentPosture reads one YAML file, `agentposture.yaml` in the current directory by default (or
`-c path`). `agentposture init` writes a commented starter; `agentposture validate` checks it.

Only `sources` is needed in practice. Everything else has a default.

```yaml
version: 1
organization: Acme Corp

storage:
  path: ./agentposture.db             # relative paths are relative to this file

server:
  host: 127.0.0.1
  port: 8484
  api_token: env:AGENTPOSTURE_TOKEN   # optional; see "Access control" below
  protect_reads: false

policy: default                       # or ./policy.yaml

sources:
  - name: manifests                   # unique; shown in the dashboard
    type: manifest                    # see docs/connectors.md
    paths: ["./"]                     # connector-specific options sit alongside
    schedule: "*/30 * * * *"          # optional cron
    trigger: webhook                  # optional: webhook | manual
    webhook_secret: env:MANIFEST_HOOK_SECRET
    enabled: true

reassessment:
  on_change: true
  max_age_by_tier: {critical: 1d, high: 7d, medium: 30d, low: 90d}
  stale_after: 14d

dashboard:
  refresh: on_demand                  # or 5m, 1h ...
  history_days: 180
```

## Secrets

Never put a secret in the file. Any credential option accepts:

- `env:NAME` reads an environment variable,
- `file:/path` reads a file (for Docker and Kubernetes secrets),
- a literal value (only sensible for local testing).

A missing variable produces an error naming the exact key, for example
`sources.github.token: environment variable GITHUB_TOKEN is not set.`

## Cadence

Three things decide when data is refreshed, and they combine:

| Setting | Scope | Use it for |
|---|---|---|
| `schedule` (cron) on a source | That source | Regular discovery. Expensive sources (a large GitHub org) every few hours, cheap ones (manifests, a registry API) more often. |
| `trigger: webhook` on a source | That source | Near real-time: rescan when GitHub reports a push. Signed with `webhook_secret`. |
| Scan button, `POST /api/scan`, `agentposture scan` | One source or all | On demand, before a review or after a change. |
| `reassessment.max_age_by_tier` | Each agent | Re-check risky agents often even when nothing changed, so a critical agent is never judged on stale data. |
| `reassessment.on_change` | Each agent | Rescore the moment any attribute changes. |

A source with neither `schedule` nor `trigger` runs on demand only. Cron uses five fields
(`minute hour day month weekday`, UTC) with `*`, `*/n`, ranges, lists, and `@hourly`, `@daily`,
`@weekly`, `@monthly`.

The dashboard itself refreshes only when you load or scan, unless `dashboard.refresh` is set.

## Access control

| Configuration | Reads (dashboard, GET API) | Writes (scan, register, delete) |
|---|---|---|
| No `api_token` | Anyone who can reach the port | Only clients on the same machine (loopback) |
| `api_token` set | Anyone who can reach the port | Requests with `Authorization: Bearer <token>` |
| `api_token` and `protect_reads: true` | Requests with the token (the dashboard asks for it once) | Requests with the token |

The default binds to `127.0.0.1`. To share the dashboard, put it behind your SSO proxy (see
`docs/deployment.md`) rather than exposing the port directly. Webhooks are authenticated by their
signature, not the token.

## Policy

`policy: default` uses the built-in policy. To change weights, thresholds, overrides or findings:

```bash
agentposture policy -o policy.yaml
# edit policy.yaml, then in agentposture.yaml:  policy: ./policy.yaml
agentposture validate
```

Changing the policy reassesses every agent on the next reconcile. See `docs/scoring.md`.

## Stale agents and retention

An agent that no source has reported for `stale_after` is flagged stale and gets finding AP-012.
Evidence older than three times `stale_after` (minimum 30 days) is deleted, so a decommissioned
agent drops out of the inventory by itself after its stale period has been visible for a while.
Assessments are kept per agent (latest 200). Daily posture snapshots are kept for `history_days`.

## Environment variables used by connectors

| Connector | Variables (conventional names; any name works via `env:`) |
|---|---|
| `github` | `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET` |
| `aws_bedrock` | The standard AWS chain: `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, instance or pod role |
| `entra_id` | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` |
| server | `AGENTPOSTURE_TOKEN` |
