# Security of AgentPosture itself

AgentPosture holds a map of where your organization's riskiest AI agents are and what they can do.
This page describes how it protects that and what you should configure.

## What it stores

Agent metadata (names, owners, teams, tool names, permission names, controls), assessment results
and scan history, in one SQLite file. It never stores secrets it finds: the code scanner records
*that* a hardcoded key exists and in which file, never the key. Connector credentials are read from
environment variables or files at runtime and are not written to the database.

## Threat model and mitigations

| Threat | Mitigation |
|---|---|
| Unauthorized people browse the risk map | Binds to 127.0.0.1 by default; deploy behind SSO (docs/deployment.md); optional `protect_reads` with a token. |
| Someone triggers scans or injects fake agents | Writes require the API token, or a loopback client when no token is set. Token comparison is constant-time. |
| Forged webhooks | HMAC-SHA256 signature over the raw body, constant-time comparison; webhooks only for sources with `trigger: webhook`. |
| Stolen scanner credentials | Every connector needs read-only permissions only (documented per connector). Use short-lived credentials (IRSA, workload identity, fine-grained tokens) where possible. |
| Malicious content in scanned data (names, descriptions, manifests) | YAML is parsed with `safe_load`; all dashboard output is HTML-escaped; strict Content-Security-Policy with no inline scripts; no templates evaluate scanned data. |
| Path traversal to read server files | Static files are served only from the packaged dashboard directory by bare file name. |
| Oversized requests | Request bodies are capped at 1 MB. |
| Clickjacking, MIME sniffing, referrer leaks | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. |
| Supply chain | One runtime dependency (PyYAML); optional boto3. The dashboard loads no third-party scripts; the only external request is the Google Fonts stylesheet, which falls back to system fonts if blocked. |
| Tampering with results | The policy hash is stored with every assessment; history is append-only through the application. Back up and restrict write access to the database file. |

## Hardening checklist

- [ ] Set `server.api_token` from a secret store.
- [ ] Serve through an SSO proxy restricted to the right groups.
- [ ] Use read-only, least-privilege credentials for each connector.
- [ ] Restrict filesystem access to the database file and its backups.
- [ ] Keep the policy file in version control and review changes.
- [ ] Pin the AgentPosture version and update deliberately.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
