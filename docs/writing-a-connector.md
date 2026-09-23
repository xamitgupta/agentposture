# Writing a connector

A connector yields evidence. That is the whole contract. Storage, joining, merging, scoring,
scheduling and the dashboard are handled for you.

```python
from agentposture.connectors import Connector, ConnectorError, register


@register
class VertexConnector(Connector):
    type_name = "vertex_ai"            # used as `type:` in agentposture.yaml
    evidence_kind = "observed"         # or "declared" for sources owners maintain
    description = "Agents in Google Vertex AI Agent Builder."
    options = {"project": "GCP project id", "location": "e.g. us-central1"}

    def discover(self):
        project = self.option("project")
        if not project:
            raise ConnectorError("vertex_ai needs `project`")    # shown to the user as-is
        for agent in list_agents(project, self.option("location", "us-central1")):  # your API call
            yield self.evidence(
                external_id=agent["name"],                    # stable id inside this source
                attributes={                                  # normalized vocabulary, see below
                    "name": agent["displayName"],
                    "tools": [t["name"] for t in agent.get("tools", [])],
                    "privileges": agent.get("scopes", []),
                    "identity": agent.get("serviceAccount"),
                },
                fingerprints=[f"identity:{agent['serviceAccount']}"],  # join keys
            )
```

## Rules

1. **Read-only.** Never modify the system you scan. Document the minimum permissions in the
   connector docstring and in `docs/connectors.md`.
2. **Normalize through `self.evidence(...)`.** It maps aliases, classifies tools, derives privilege
   level and adds the source fingerprint.
3. **Emit join keys** your other sources emit: `identity:<principal>` for service principals, IAM
   roles and service accounts; `repo:<owner/name>` for code; `<type>:<resource id>` for cloud
   resources. This is what turns separate sightings into one agent.
4. **Only report what you know.** Omit an attribute rather than guess; unknown is scored
   conservatively on purpose.
5. **Raise `ConnectorError`** with an actionable message for configuration, network and permission
   problems. Other exceptions are caught and recorded too, but look like bugs.
6. **Secrets** come from `self.option("token", secret=True)`, which resolves `env:` and `file:`.
7. **HTTP** without dependencies: `from agentposture.connectors import _http` and
   `_http.request(url, headers=..., with_link=True)`.

## Attributes you can set

`id`, `name`, `description`, `owner`, `team`, `lifecycle`, `business_impact`, `autonomy`, `exposure`,
`data_sensitivity`, `data_types`, `tools` (names or `{name, action, system, requires_approval}`),
`privileges`, `privilege_level`, `irreversible_actions`, `controls` (`kill_switch`,
`audit_logging`, `input_guardrails`, `output_guardrails`, `rate_limit`, `sandboxed`,
`human_approval`), `model`, `identity`, `repo`, `runtime`, `credential_type` (`hardcoded_key`,
`client_secret`, `certificate`, `federated_or_managed`), `frameworks`, and anything else, which is
kept under `extra` and shown on the dashboard.

## Shipping it

**Inside this repository:** add `src/agentposture/connectors/<name>.py`, add the module name to
`_BUILTINS` in `connectors/__init__.py`, document it in `docs/connectors.md`, and add a test in
`tests/test_connectors.py` that runs `discover()` against a fixture (no network in tests).

**As a separate package** (for private systems): declare an entry point and install the package
next to AgentPosture. No fork needed.

```toml
[project.entry-points."agentposture.connectors"]
vertex_ai = "my_package.vertex:VertexConnector"
```

A complete example lives in `examples/custom-connector/`.

## Webhooks

If your source can push events, set `trigger: webhook` and `webhook_secret` on the source. The
default `verify_webhook` accepts an HMAC-SHA256 signature of the body in `X-Hub-Signature-256` or
`X-AgentPosture-Signature` (`sha256=<hex>`). Override `verify_webhook(headers, body)` for other
schemes.
