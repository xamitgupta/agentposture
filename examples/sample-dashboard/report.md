# Agent risk posture: Acme Corp (demo)

Generated 2026-09-23T21:09:37+00:00 with AgentPosture default policy.

**29 agents.** 6 critical, 8 high, 10 medium, 5 low.
14 need action, 4 undeclared (shadow), 5 drifted from their declaration, 5 without an owner, 0 stale. Record completeness 86%.

## Needs action

| Tier | Agent | Team | Most important fix |
|---|---|---|---|
| critical | acme/ops-mcp (`acme-ops-mcp-9d16d1`) | unassigned | Irreversible actions without human approval |
| critical | hackathon-slack-agent (`hackathon-slack-agent-beba3b`) | unassigned | No accountable owner |
| critical | acme/finance-scripts (`acme-finance-scripts-740aa6`) | unassigned | No accountable owner |
| critical | acme/growth-hacks (`acme-growth-hacks-f93f04`) | unassigned | Hardcoded credential in source |
| critical | Account Recovery Agent (`account-recovery-agent`) | customer-support | Irreversible actions without human approval |
| critical | Chargeback Autopilot (`chargeback-autopilot`) | payments | Irreversible actions without human approval |
| high | Dependency Updater (`dependency-updater`) | developer-experience | Irreversible actions without human approval |
| high | On-call Remediator (`oncall-remediator`) | platform | Irreversible actions without human approval |
| high | Lead Enrichment Agent (`lead-enrichment-agent`) | growth | No kill switch |
| high | Candidate Screener (`candidate-screener`) | people | Untrusted input without input guardrails |

## Risk by team

| Team | Agents | Critical | High | Medium | Low | Urgent findings |
|---|---:|---:|---:|---:|---:|---:|
| unassigned | 4 | 4 | 0 | 0 | 0 | 13 |
| payments | 2 | 1 | 1 | 0 | 0 | 4 |
| customer-support | 4 | 1 | 0 | 2 | 1 | 5 |
| platform | 3 | 0 | 2 | 0 | 1 | 4 |
| developer-experience | 3 | 0 | 1 | 2 | 0 | 4 |
| growth | 3 | 0 | 1 | 1 | 1 | 2 |
| people | 2 | 0 | 1 | 1 | 0 | 2 |
| data | 2 | 0 | 1 | 1 | 0 | 1 |
| security | 3 | 0 | 1 | 1 | 1 | 2 |
| finance | 2 | 0 | 0 | 1 | 1 | 0 |
| legal | 1 | 0 | 0 | 1 | 0 | 0 |

## Most common findings

| Finding | Severity | Agents |
|---|---|---:|
| Irreversible actions without human approval (AP-004) | critical | 5 |
| Hardcoded credential in source (AP-010) | critical | 1 |
| No kill switch (AP-005) | high | 6 |
| No accountable owner (AP-001) | high | 5 |
| Running with more than it declares (AP-003) | high | 5 |
| Undeclared (shadow) agent (AP-002) | high | 4 |
| Admin or wildcard privileges (AP-009) | high | 4 |
| Untrusted input without input guardrails (AP-006) | high | 3 |
| Can execute code or shell commands (AP-016) | high | 2 |
| Sensitive data can leave without output filtering (AP-007) | high | 2 |
| Actions are not audit logged (AP-008) | medium | 4 |
| Incomplete risk record (AP-014) | medium | 4 |
| Long-lived client secret (AP-011) | medium | 1 |
| Deprecated but still running (AP-013) | medium | 1 |
| Public agent without rate limiting (AP-015) | medium | 1 |

## All agents

| Tier | Score | Agent | Owner | Findings | Flags |
|---|---:|---|---|---:|---|
| critical | 95 | acme/ops-mcp (`acme-ops-mcp-9d16d1`) | nobody | 6 | shadow, unowned, incomplete |
| critical | 95 | hackathon-slack-agent (`hackathon-slack-agent-beba3b`) | nobody | 6 | shadow, unowned, incomplete |
| critical | 88 | acme/finance-scripts (`acme-finance-scripts-740aa6`) | nobody | 4 | shadow, unowned, incomplete |
| critical | 88 | acme/growth-hacks (`acme-growth-hacks-f93f04`) | nobody | 6 | shadow, unowned, incomplete |
| critical | 82 | Account Recovery Agent (`account-recovery-agent`) | lee.w@acme.example | 4 |  |
| critical | 68 | Chargeback Autopilot (`chargeback-autopilot`) | marco.r@acme.example | 4 | drift |
| high | 59 | Dependency Updater (`dependency-updater`) | nobody | 3 | unowned |
| high | 58 | On-call Remediator (`oncall-remediator`) | arjun.m@acme.example | 4 | drift |
| high | 43 | Refund Assistant (`refund-assistant`) | priya.n@acme.example | 0 |  |
| high | 43 | Lead Enrichment Agent (`lead-enrichment-agent`) | sam.o@acme.example | 2 | drift |
| high | 42 | Candidate Screener (`candidate-screener`) | zoe.a@acme.example | 2 |  |
| high | 41 | Phishing Responder (`phishing-responder`) | kai.s@acme.example | 0 |  |
| high | 41 | Pipeline Doctor (`pipeline-doctor`) | mia.c@acme.example | 0 |  |
| high | 40 | Deploy Copilot (`deploy-copilot`) | arjun.m@acme.example | 0 |  |
| medium | 40 | Campaign Publisher (`campaign-publisher`) | ivy.t@acme.example | 0 |  |
| medium | 37 | Invoice Matcher (`invoice-matcher`) | omar.f@acme.example | 0 |  |
| medium | 35 | Legacy FAQ Bot (`old-faq-bot`) | former.employee@acme.example | 3 |  |
| medium | 34 | Support Triage Bot (`support-triage-bot`) | dana.k@acme.example | 0 |  |
| medium | 32 | Access Review Assistant (`access-review-assistant`) | rob.g@acme.example | 2 | drift |
| medium | 28 | Test Writer (`test-writer`) | tom.h@acme.example | 1 |  |
| medium | 24 | Contract Redliner (`contract-redliner`) | ana.p@acme.example | 0 |  |
| medium | 24 | PR Reviewer (`pr-reviewer`) | tom.h@acme.example | 0 |  |
| medium | 24 | Benefits Helpdesk (`benefits-helpdesk`) | zoe.a@acme.example | 0 |  |
| medium | 24 | SQL Analyst (`sql-analyst`) | mia.c@acme.example | 1 | drift |
| low | 20 | Expense Auditor (`expense-auditor`) | omar.f@acme.example | 0 |  |
| low | 20 | Sales Email Writer (`sales-email-writer`) | sam.o@acme.example | 0 |  |
| low | 17 | Support Reply Drafter (`support-reply-drafter`) | dana.k@acme.example | 0 |  |
| low | 15 | Threat Intel Summarizer (`threat-intel-summarizer`) | kai.s@acme.example | 0 |  |
| low | 13 | Cloud Cost Reporter (`cost-report-bot`) | nina.b@acme.example | 0 |  |

## Findings by agent

### acme/ops-mcp (critical)

- **Irreversible actions without human approval** (critical, AP-004): acme/ops-mcp can call mcp:kubernetes, mcp:shell with no human approval step. Fix: Require approval for these tools (list them under controls.human_approval and enforce it in the runtime), or replace them with reversible alternatives such as drafts or holds.
- **No accountable owner** (high, AP-001): No person is recorded as owning acme/ops-mcp. Fix: Add `owner:` (a person's email) and `team:` to the agent's manifest.
- **Undeclared (shadow) agent** (high, AP-002): acme/ops-mcp was discovered in demo-fleet but nobody has declared it. Fix: Find the team running it and commit an agent.yaml next to its code, or shut it down. Declaring it records business impact, data sensitivity and controls that discovery cannot see.
- **Can execute code or shell commands** (high, AP-016): acme/ops-mcp can run code or commands outside a sandbox. Fix: Run code execution in an isolated sandbox with no network or credentials by default; set controls.sandboxed.
- **Actions are not audit logged** (medium, AP-008): There is no audit trail of what acme/ops-mcp does or reads. Fix: Log every tool call with the principal, inputs and result to your central log store; set controls.audit_logging.
- **Incomplete risk record** (medium, AP-014): Missing or unrecognized values for autonomy, exposure, data_sensitivity, business_impact; they are scored as high risk until filled in. Fix: Add these fields to the agent's manifest. See docs/manifest.md for allowed values.

### hackathon-slack-agent (critical)

- **No accountable owner** (high, AP-001): No person is recorded as owning hackathon-slack-agent. Fix: Add `owner:` (a person's email) and `team:` to the agent's manifest.
- **Undeclared (shadow) agent** (high, AP-002): hackathon-slack-agent was discovered in demo-fleet but nobody has declared it. Fix: Find the team running it and commit an agent.yaml next to its code, or shut it down. Declaring it records business impact, data sensitivity and controls that discovery cannot see.
- **Admin or wildcard privileges** (high, AP-009): hackathon-slack-agent holds broad privileges: Microsoft Graph:Chat.ReadWrite.All, Microsoft Graph:Mail.ReadWrite. Fix: Replace wildcard and admin grants with the specific actions the agent's tools need.
- **Actions are not audit logged** (medium, AP-008): There is no audit trail of what hackathon-slack-agent does or reads. Fix: Log every tool call with the principal, inputs and result to your central log store; set controls.audit_logging.
- **Long-lived client secret** (medium, AP-011): hackathon-slack-agent authenticates with a static client secret. Fix: Switch to workload identity federation, a managed identity, or a certificate with short rotation.
- **Incomplete risk record** (medium, AP-014): Missing or unrecognized values for autonomy, exposure, data_sensitivity, business_impact; they are scored as high risk until filled in. Fix: Add these fields to the agent's manifest. See docs/manifest.md for allowed values.

### acme/finance-scripts (critical)

- **No accountable owner** (high, AP-001): No person is recorded as owning acme/finance-scripts. Fix: Add `owner:` (a person's email) and `team:` to the agent's manifest.
- **Undeclared (shadow) agent** (high, AP-002): acme/finance-scripts was discovered in demo-fleet but nobody has declared it. Fix: Find the team running it and commit an agent.yaml next to its code, or shut it down. Declaring it records business impact, data sensitivity and controls that discovery cannot see.
- **Actions are not audit logged** (medium, AP-008): There is no audit trail of what acme/finance-scripts does or reads. Fix: Log every tool call with the principal, inputs and result to your central log store; set controls.audit_logging.
- **Incomplete risk record** (medium, AP-014): Missing or unrecognized values for autonomy, exposure, data_sensitivity, business_impact; they are scored as high risk until filled in. Fix: Add these fields to the agent's manifest. See docs/manifest.md for allowed values.

### acme/growth-hacks (critical)

- **Hardcoded credential in source** (critical, AP-010): A model or cloud key is committed in source. Fix: Revoke the key now, move it to a secrets manager, and add secret scanning to the repository.
- **No accountable owner** (high, AP-001): No person is recorded as owning acme/growth-hacks. Fix: Add `owner:` (a person's email) and `team:` to the agent's manifest.
- **Undeclared (shadow) agent** (high, AP-002): acme/growth-hacks was discovered in demo-fleet but nobody has declared it. Fix: Find the team running it and commit an agent.yaml next to its code, or shut it down. Declaring it records business impact, data sensitivity and controls that discovery cannot see.
- **No kill switch** (high, AP-005): acme/growth-hacks can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.
- **Actions are not audit logged** (medium, AP-008): There is no audit trail of what acme/growth-hacks does or reads. Fix: Log every tool call with the principal, inputs and result to your central log store; set controls.audit_logging.
- **Incomplete risk record** (medium, AP-014): Missing or unrecognized values for exposure, data_sensitivity, business_impact; they are scored as high risk until filled in. Fix: Add these fields to the agent's manifest. See docs/manifest.md for allowed values.

### Account Recovery Agent (critical)

- **Irreversible actions without human approval** (critical, AP-004): Account Recovery Agent can call reset_mfa with no human approval step. Fix: Require approval for these tools (list them under controls.human_approval and enforce it in the runtime), or replace them with reversible alternatives such as drafts or holds.
- **No kill switch** (high, AP-005): Account Recovery Agent can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.
- **Untrusted input without input guardrails** (high, AP-006): Account Recovery Agent takes input from outside the company without prompt-injection filtering. Fix: Put an input filter or guardrail in front of the model and set controls.input_guardrails.
- **Sensitive data can leave without output filtering** (high, AP-007): Account Recovery Agent handles restricted data and answers people outside the company unfiltered. Fix: Add output filtering for sensitive data (PII, secrets) and set controls.output_guardrails.

### Chargeback Autopilot (critical)

- **Irreversible actions without human approval** (critical, AP-004): Chargeback Autopilot can call accept_chargeback with no human approval step. Fix: Require approval for these tools (list them under controls.human_approval and enforce it in the runtime), or replace them with reversible alternatives such as drafts or holds.
- **Running with more than it declares** (high, AP-003): Observed behavior exceeds the declaration: privilege level declared write, observed admin. Fix: Either reduce the agent's real permissions and tools to what was declared, or update the manifest so reviewers see the true scope.
- **No kill switch** (high, AP-005): Chargeback Autopilot can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.
- **Admin or wildcard privileges** (high, AP-009): Chargeback Autopilot holds broad privileges: payments:*. Fix: Replace wildcard and admin grants with the specific actions the agent's tools need.

### Dependency Updater (high)

- **Irreversible actions without human approval** (critical, AP-004): Dependency Updater can call merge_pull_request with no human approval step. Fix: Require approval for these tools (list them under controls.human_approval and enforce it in the runtime), or replace them with reversible alternatives such as drafts or holds.
- **No accountable owner** (high, AP-001): No person is recorded as owning Dependency Updater. Fix: Add `owner:` (a person's email) and `team:` to the agent's manifest.
- **No kill switch** (high, AP-005): Dependency Updater can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.

### On-call Remediator (high)

- **Irreversible actions without human approval** (critical, AP-004): On-call Remediator can call run_command with no human approval step. Fix: Require approval for these tools (list them under controls.human_approval and enforce it in the runtime), or replace them with reversible alternatives such as drafts or holds.
- **Running with more than it declares** (high, AP-003): Observed behavior exceeds the declaration: privilege level declared write, observed admin. Fix: Either reduce the agent's real permissions and tools to what was declared, or update the manifest so reviewers see the true scope.
- **Admin or wildcard privileges** (high, AP-009): On-call Remediator holds broad privileges: arn:aws:iam::aws:policy/AdministratorAccess. Fix: Replace wildcard and admin grants with the specific actions the agent's tools need.
- **Can execute code or shell commands** (high, AP-016): On-call Remediator can run code or commands outside a sandbox. Fix: Run code execution in an isolated sandbox with no network or credentials by default; set controls.sandboxed.

### Lead Enrichment Agent (high)

- **No kill switch** (high, AP-005): Lead Enrichment Agent can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.
- **Running with more than it declares** (high, AP-003): Observed behavior exceeds the declaration: tools declared update_crm_record, web_search, observed send_outreach_email. Fix: Either reduce the agent's real permissions and tools to what was declared, or update the manifest so reviewers see the true scope.

### Candidate Screener (high)

- **Untrusted input without input guardrails** (high, AP-006): Candidate Screener takes input from outside the company without prompt-injection filtering. Fix: Put an input filter or guardrail in front of the model and set controls.input_guardrails.
- **Sensitive data can leave without output filtering** (high, AP-007): Candidate Screener handles restricted data and answers people outside the company unfiltered. Fix: Add output filtering for sensitive data (PII, secrets) and set controls.output_guardrails.

### Legacy FAQ Bot (medium)

- **Untrusted input without input guardrails** (high, AP-006): Legacy FAQ Bot takes input from outside the company without prompt-injection filtering. Fix: Put an input filter or guardrail in front of the model and set controls.input_guardrails.
- **Deprecated but still running** (medium, AP-013): Legacy FAQ Bot is marked deprecated but is still active. Fix: Finish decommissioning by disabling the agent and revoking its identity and keys.
- **Public agent without rate limiting** (medium, AP-015): Anyone can drive unbounded usage and cost through Legacy FAQ Bot. Fix: Add per-user and global rate limits and a spend cap; set controls.rate_limit.

### Access Review Assistant (medium)

- **Running with more than it declares** (high, AP-003): Observed behavior exceeds the declaration: privilege level declared read, observed admin. Fix: Either reduce the agent's real permissions and tools to what was declared, or update the manifest so reviewers see the true scope.
- **Admin or wildcard privileges** (high, AP-009): Access Review Assistant holds broad privileges: Microsoft Graph:Directory.ReadWrite.All. Fix: Replace wildcard and admin grants with the specific actions the agent's tools need.

### Test Writer (medium)

- **No kill switch** (high, AP-005): Test Writer can take actions but there is no documented way to stop it immediately. Fix: Add a feature flag or revocable credential that disables the agent in one step, and set controls.kill_switch.

### SQL Analyst (medium)

- **Running with more than it declares** (high, AP-003): Observed behavior exceeds the declaration: privilege level declared read, observed write. Fix: Either reduce the agent's real permissions and tools to what was declared, or update the manifest so reviewers see the true scope.

