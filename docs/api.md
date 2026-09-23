# REST API

All responses are JSON. The dashboard uses exactly these endpoints, so anything it shows you can
automate.

Authentication: see "Access control" in `docs/configuration.md`. Send
`Authorization: Bearer <server.api_token>` where required.

## Read

| Method and path | Returns |
|---|---|
| `GET /healthz` | `{"ok": true}` |
| `GET /api/summary` | Organization posture: totals by tier, shadow, drift, unowned, stale, completeness; attention list; per-team and per-platform breakdowns; most common findings; control coverage; sources; daily trend. |
| `GET /api/agents` | Agent rows, riskiest first. Filters: `tier`, `team`, `flag` (shadow, drift, unowned, stale, incomplete), `q` (text). |
| `GET /api/agents/{id}` | `agent` (declared, observed, effective attributes, drift, sources), `assessment` (dimensions, controls, overrides, findings with fixes, target tier) and `history`. |
| `GET /api/sources` | Each source with type, schedule, next run, last status, last success, record count, error. |
| `GET /api/runs?limit=50` | Recent scan runs. |
| `GET /api/status` | Whether a scan is running and the last scan report. |

## Write

| Method and path | Body | Effect |
|---|---|---|
| `POST /api/scan` | `{}` or `{"source": "name"}` | Starts a background scan. `202` if started, `409` if one is already running. Poll `/api/status`. |
| `POST /api/agents` | A manifest as JSON (one agent, or `{"agents": [...]}`) | Declares agents under source `api`. `201` with the registered ids. |
| `DELETE /api/agents/{id}` | | Removes an API-declared agent. Agents from other sources come back on their next scan. |
| `POST /api/webhooks/{source}` | The provider's payload | Verifies the signature and rescans that source. The source needs `trigger: webhook`. |

## Examples

```bash
# Critical agents, as a list of ids
curl -s localhost:8484/api/agents?tier=critical | jq -r '.[].id'

# Why is this agent high?
curl -s localhost:8484/api/agents/refund-assistant | jq '.assessment.findings[] | {title, remediation, tier_if_fixed}'

# Register an agent from a deployment pipeline
curl -X POST localhost:8484/api/agents -H "Authorization: Bearer $AGENTPOSTURE_TOKEN" \
  -H 'Content-Type: application/json' -d @agent.json

# Sign a custom webhook
sig="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)"
curl -X POST localhost:8484/api/webhooks/manifests -H "X-AgentPosture-Signature: $sig" -d "$BODY"
```
