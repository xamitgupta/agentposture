# Connectors

A connector is a source of evidence about agents. **Declared** connectors record what owners say;
**observed** connectors record what is actually running. Use at least one of each: declarations
supply business context, observation keeps declarations honest and finds shadow agents.

Every connector is read-only. List them with `agentposture connectors -v`.

## `manifest` (declared)

Reads `agent.yaml`, `agent.yml`, `*.agent.yaml`, `*.agent.yml` and `agents.yaml` files.

```yaml
- name: manifests
  type: manifest
  paths: ["/srv/checkouts", "./platform-agents"]
  patterns: ["agent.yaml", "*.agent.yaml"]     # optional
```

Permissions: read access to the directories. For a whole GitHub organization use `github` instead.

## `code_scan` (observed)

Walks local checkouts and reports each git repository that contains an agent, recognized by:

- agent framework imports or dependencies: LangChain, LangGraph, CrewAI, AutoGen, LlamaIndex,
  OpenAI Agents SDK and Assistants, Semantic Kernel, Pydantic AI, smolagents, Google ADK, Strands,
  Mastra, Vercel AI SDK, MCP servers;
- LLM SDKs (OpenAI, Anthropic, Bedrock, Vertex AI) together with tool definitions;
- MCP client configs (`.mcp.json`, `mcp.json`, `claude_desktop_config.json`); servers such as
  filesystem, shell, databases, cloud and payment APIs count as irreversible tools.

It also extracts tool names (`@tool`, `@function_tool`, `Tool(name=...)`, OpenAI function schemas,
`server.tool(...)`), model names, autonomy hints (`human_input_mode="NEVER"` means autonomous;
`interrupt_before`, `HumanApprovalCallbackHandler`, `requires_approval=True` mean approval), and
hardcoded OpenAI, Anthropic or AWS keys (the key is never stored, only the file path).

```yaml
- name: code
  type: code_scan
  paths: ["/srv/checkouts"]
  include_llm_apps: false   # true also reports LLM SDK usage without tools
```

Files over 512 KB, `node_modules`, virtual environments and build output are skipped.

## `github` (observed + declared)

Scans every repository in an organization through the REST API: manifests become declared
evidence, and the same detection rules as `code_scan` run on dependency files, MCP configs and
source files (up to `max_files_per_repo`, default 400, dependency files first).

```yaml
- name: github
  type: github
  org: acme
  token: env:GITHUB_TOKEN
  repos: [payments-bot, support-agent]     # optional allow-list
  api_url: https://github.acme.example/api/v3   # GitHub Enterprise Server
  include_archived: false
  schedule: "0 */6 * * *"
  trigger: webhook
  webhook_secret: env:GITHUB_WEBHOOK_SECRET
```

Permissions: a fine-grained token with **Contents: read** and **Metadata: read** on the
repositories, or a GitHub App with the same. For webhooks, add an organization webhook for `push`
events to `https://<host>/api/webhooks/github` with content type `application/json` and the same
secret.

## `aws_bedrock` (observed)

Lists Bedrock Agents in each region with their action groups (functions, user-confirmation
settings, code interpreter), knowledge bases, guardrail configuration, and the permissions of the
agent's IAM service role. Requires `pip install "agentposture[aws]"`.

```yaml
- name: aws-prod
  type: aws_bedrock
  regions: [us-east-1, us-west-2]
  profile: security-audit        # optional; otherwise the default credential chain
  inspect_iam: true
```

Least-privilege IAM policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock:ListAgents", "bedrock:GetAgent", "bedrock:ListAgentActionGroups",
      "bedrock:GetAgentActionGroup", "bedrock:ListAgentKnowledgeBases",
      "iam:ListRolePolicies", "iam:GetRolePolicy", "iam:ListAttachedRolePolicies",
      "iam:GetPolicy", "iam:GetPolicyVersion"
    ],
    "Resource": "*"
  }]
}
```

For several accounts, add one source per account with a profile that assumes a read-only role there.
Functions with user confirmation enabled count as requiring human approval.

## `entra_id` (observed)

Lists service principals that represent agents, with their application permissions (app role
assignments), delegated grants, first owner, and credential type (static client secret versus
certificate or federated/managed identity).

```yaml
- name: entra
  type: entra_id
  tenant_id: env:AZURE_TENANT_ID
  client_id: env:AZURE_CLIENT_ID
  client_secret: env:AZURE_CLIENT_SECRET
  tag: AIAgent                              # principals carrying this tag (default)
  # name_prefix: agent-                     # or by display name
  # filter: "startswith(displayName,'ai-')" # or any Graph OData filter
```

Permissions: register an app for the scanner, grant the Microsoft Graph application permission
**Application.Read.All**, and grant admin consent. The principal's `appId` becomes the
`identity:` join key, so a manifest with `links: {identity: <appId>}` joins it.

## `http_json` (declared by default)

Reads any JSON API or JSON file: an internal agent registry, a Backstage catalog, a CMDB export.

```yaml
- name: registry
  type: http_json
  url: https://registry.internal/api/agents     # or: file: ./export.json
  headers: {Authorization: env:REGISTRY_AUTH_HEADER}
  items_path: data.items          # dotted path to the list
  next_path: data.next            # dotted path to the next page URL (optional)
  id_field: slug
  mapping:                        # AgentPosture attribute: dotted path in each item
    name: display_name
    owner: owner.email
    autonomy: governance.autonomy
  links: {identity: runtime.service_principal}
  kind: declared                  # or observed, if the registry is generated by discovery
```

Fields not in `mapping` pass through by name, so a registry that already uses AgentPosture's
attribute names needs no mapping.

**Backstage example:** `url: https://backstage.internal/api/catalog/entities/by-query?filter=spec.type=ai-agent`,
`items_path: items`, `id_field: metadata.name`, `mapping: {name: metadata.title, owner: spec.owner,
lifecycle: spec.lifecycle, description: metadata.description}`, `next_path` omitted (use a filter
that fits one page, or a small wrapper).

## `csv` (declared)

The fastest way to load a spreadsheet inventory. One row per agent. Columns use attribute names;
list columns (`tools`, `data_types`, `privileges`, `human_approval`) are separated by `;` or `,`;
control columns (`kill_switch`, `audit_logging`, `input_guardrails`, `output_guardrails`,
`rate_limit`, `sandboxed`) accept yes/no; `link_<key>` columns become join keys.

```yaml
- {name: inventory, type: csv, path: ./agents.csv, trigger: manual}
```

See `examples/agents.csv`.

## `demo`

A synthetic 29-agent organization. Used by `agentposture demo`.

## API registrations

Agents declared with `POST /api/agents` appear as source `api`. They need no configuration.

## Not built in yet

Google Vertex AI Agent Builder, Azure AI Foundry Agent Service, Salesforce Agentforce, ServiceNow,
Okta, and gateway or proxy logs are good candidates. A connector is typically 50 to 150 lines; see
`docs/writing-a-connector.md` and `examples/custom-connector/`.
