# The agent manifest (`agent.yaml`)

The manifest is how an owner tells AgentPosture what discovery cannot see: what the agent is for,
how bad a failure would be, what data it touches, and which controls exist. It lives in the agent's
repository, so it is versioned and reviewed with the code it describes.

Name the file `agent.yaml`, `agent.yml`, `<anything>.agent.yaml`, or `agents.yaml`. For editor
completion add this first line:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/xamitgupta/agentposture/main/schemas/agent-manifest.schema.json
```

## Minimal

```yaml
id: research-copilot
owner: tom@acme.example
team: developer-experience
autonomy: recommend
exposure: internal
business_impact: low
data: {sensitivity: internal}
```

Anything you omit is scored as risky and listed in finding AP-014 until it is filled in.

## Full reference

| Field | Values | Meaning |
|---|---|---|
| `id` | string | Stable, unique id. Used to join with the same agent in other sources and in the API. |
| `name`, `description` | string | Shown on the dashboard. |
| `owner` | email | The accountable person. Missing owner is finding AP-001. |
| `team` | string | Used for the per-team view. |
| `lifecycle` | development, staging, production, deprecated | Deprecated agents that are still seen raise AP-013. |
| `business_impact` | low, medium, high, critical | The worst realistic outcome if this agent misbehaves. |
| `autonomy` | read_only, recommend, act_with_approval, autonomous | read_only: only reads. recommend: suggests, a person acts. act_with_approval: acts after a person approves. autonomous: acts on its own. |
| `exposure` | internal, partner, customer, public | Who can send the agent input. Anything beyond internal is treated as untrusted input. |
| `data.sensitivity` | public, internal, confidential, restricted | Your data classification for what the agent can read. |
| `data.types` | list: pii, phi, pci, financial, credentials, source_code, biometric, ... | Raises sensitivity to at least confidential or restricted per the policy. |
| `model` | string | For the record, e.g. `anthropic/claude-sonnet`. |
| `tools` | list of names or objects | What the agent can call. Object form: `name`, `action` (read, write, irreversible), `system`, `requires_approval`. Without `action`, it is inferred from the name (`delete_*`, `refund`, `transfer`, `deploy`, `run_command` are irreversible). |
| `privileges` | list of strings | Permissions of the agent's identity (IAM actions, OAuth scopes). Wildcards and admin roles raise privilege to admin. |
| `controls.human_approval` | true, or a list of tool names | Which tools require a person to approve. Also set per tool with `requires_approval`. |
| `controls.kill_switch` | bool | The agent can be stopped in one step (feature flag, revocable credential). |
| `controls.audit_logging` | bool | Every tool call is logged centrally with principal, inputs and result. |
| `controls.input_guardrails` | bool | Prompt-injection or content filtering on input. |
| `controls.output_guardrails` | bool | Sensitive-data filtering on output. |
| `controls.rate_limit` | bool | Per-user and global rate limits or a spend cap. |
| `controls.sandboxed` | bool | Code execution runs in an isolated sandbox. |
| `links` | map | Join keys to other sources: `repo: owner/name`, `identity: <service principal or role>`, `aws_bedrock: <agent ARN>`, or any `key: value` a connector emits. |

## Several agents in one file

```yaml
agents:
  - {id: triage-bot, owner: a@acme.example, autonomy: recommend, exposure: internal}
  - {id: reply-bot, owner: a@acme.example, autonomy: act_with_approval, exposure: customer}
```

Multiple YAML documents separated by `---` also work.

## Linking to discovered agents

The same agent is often seen by several sources. AgentPosture joins them when they share a key:

- A repository with exactly one manifest is linked to that repository automatically, so the
  `code_scan` or `github` result for the repository merges into the declaration.
- Add `links.identity` with the agent's service principal (Entra app id, AWS role ARN) to join the
  identity-provider view.
- Add `links.aws_bedrock` with the agent ARN to join the Bedrock view.

When joined, the dashboard shows declared and observed values side by side and flags drift.

## Registering without a file

Pipelines and internal portals can declare agents through the API with the same fields as JSON:

```bash
curl -X POST http://localhost:8484/api/agents \
  -H "Authorization: Bearer $AGENTPOSTURE_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"invoice-bot","owner":"f@acme.example","autonomy":"recommend","exposure":"internal"}'
```

## Checking a manifest before merge

```bash
agentposture check . --fail-on high
```

prints each agent's tier and findings with fixes, and exits 1 if any agent is at or above the tier.
