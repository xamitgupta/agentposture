# Scoring and policy

AgentPosture turns what it knows about an agent into a tier (low, medium, high, critical) using a
policy file. The built-in policy is `src/agentposture/policies/default.yaml`; export it with
`agentposture policy -o policy.yaml`, edit, and set `policy: ./policy.yaml`.

Every assessment stores the policy hash, and a new hash triggers reassessment of every agent, so a
policy change is always visible and auditable.

## Step 1: dimensions (inherent risk)

| Dimension | Weight | Level 0 | Level 1 | Level 2 | Level 3 | Unknown scores as |
|---|---:|---|---|---|---|---|
| Autonomy | 22 | read_only | recommend | act_with_approval | autonomous | 3 |
| Privilege | 20 | none | read | write | admin, or any irreversible tool | 2 |
| Data sensitivity | 18 | public | internal | confidential | restricted | 3 |
| Exposure | 15 | internal | partner | customer | public | 3 |
| Business impact | 15 | low | medium | high | critical | 2 |
| Ownership | 10 | owner and team | owner only | team only | nobody | n/a |

Data types raise sensitivity: `pii`, `financial`, `source_code`, `biometric` to at least
confidential; `phi`, `pci`, `credentials` to restricted.

```
inherent = 100 x sum(weight x level / 3) / sum(weight)
```

This measures **what the agent is allowed to do and to whom**, independent of how well it is
protected.

## Step 2: controls (residual risk)

Controls reduce risk only where they are relevant. A control *applies* to an agent when:

| Control | Weight | Applies when |
|---|---:|---|
| human_approval | 3 | The agent has irreversible tools. In place when every one of them requires approval. |
| kill_switch | 2 | Autonomy is act_with_approval or autonomous (or unknown). |
| audit_logging | 2 | The agent can write or has irreversible tools, or touches confidential data or above. |
| input_guardrails | 2 | Exposure is partner, customer or public. |
| output_guardrails | 2 | Exposure beyond internal and data confidential or above. |
| rate_limit | 1 | Exposure is public. |
| sandboxed | 2 | The agent can execute code or shell commands. |

```
coverage  = sum(weights of applicable controls in place) / sum(weights of applicable controls)
residual  = inherent x (1 - coverage x max_reduction)        # max_reduction = 35%
```

So a well-controlled agent can drop by up to about a third, but no amount of controls turns an
inherently dangerous agent into a low one. That is intentional: the residual tier should still tell
leadership where the exposure is.

## Step 3: tier

| Tier | Residual score |
|---|---|
| critical | 70 and above |
| high | 40 to 69.9 |
| medium | 22 to 39.9 |
| low | below 22 |

## Step 4: overrides (blast radius)

Some combinations are dangerous regardless of the average. An override sets a minimum tier.

| Override | Minimum tier | When |
|---|---|---|
| `autonomous-irreversible-external` | critical | Acts on its own, can do things that cannot be undone, and faces customers or the public. |
| `autonomous-irreversible-restricted` | critical | Acts on its own with irreversible actions over restricted data. |
| `admin-privilege-acting` | high | Holds admin or wildcard privileges and can act. |
| `restricted-data-public` | high | Restricted data reachable from a public-facing agent. |
| `shadow-agent-can-act` | high | Nobody declared this agent and it can change things. |
| `hardcoded-credential` | high | A model or cloud key is hardcoded in source. |

## Step 5: findings

Findings are specific, fixable gaps shown to owners. Each has remediation text, framework
references, and a `fix` used to compute what the tier would be if only that finding were fixed.
The agent's *target tier* is the tier with every finding fixed.

| Id | Finding | Severity | Frameworks |
|---|---|---|---|
| AP-001 | No accountable owner | high | NIST AI RMF GV-2.1 |
| AP-002 | Undeclared (shadow) agent | high | NIST AI RMF GV-1.6 |
| AP-003 | Running with more than it declares | high | NIST AI RMF MG-4.1, OWASP LLM06 |
| AP-004 | Irreversible actions without human approval | critical | OWASP LLM06, NIST AI RMF MG-2.4 |
| AP-005 | No kill switch | high | NIST AI RMF MG-2.4 |
| AP-006 | Untrusted input without input guardrails | high | OWASP LLM01 |
| AP-007 | Sensitive data can leave without output filtering | high | OWASP LLM02 |
| AP-008 | Actions are not audit logged | medium | NIST AI RMF MG-4.1 |
| AP-009 | Admin or wildcard privileges | high | OWASP LLM06 |
| AP-010 | Hardcoded credential in source | critical | CWE-798, OWASP LLM02 |
| AP-011 | Long-lived client secret | medium | NIST AI RMF MS-2.7 |
| AP-012 | Not seen recently | medium | NIST AI RMF GV-1.7 |
| AP-013 | Deprecated but still running | medium | NIST AI RMF GV-1.7 |
| AP-014 | Incomplete risk record | medium | NIST AI RMF MP-1.1 |
| AP-015 | Public agent without rate limiting | medium | OWASP LLM10 |
| AP-016 | Can execute code or shell commands | high | OWASP LLM05, OWASP LLM06 |

Framework references: NIST AI Risk Management Framework 1.0 subcategories (GV = Govern, MP = Map,
MS = Measure, MG = Manage), OWASP Top 10 for LLM Applications 2025 (LLM01 prompt injection, LLM02
sensitive information disclosure, LLM05 improper output handling, LLM06 excessive agency, LLM10
unbounded consumption), and CWE-798 (hardcoded credentials). The mappings are editable in the
policy; add ISO/IEC 42001, EU AI Act or internal control ids the same way.

## The condition language

Overrides and findings use the same small language. Paths reach into nested values with dots.

```yaml
when:
  all:
    - {attr: autonomy, is: autonomous}
    - {attr: exposure, at_least: customer}          # ordinal comparison
    - {attr: controls.kill_switch, is_not: true}
    - any:
        - {attr: data_types, contains_any: [pii, phi]}
        - {attr: owner, missing: true}
    - not: {attr: lifecycle, in: [development]}
```

Operators: `is`, `is_not`, `in`, `at_least`, `at_most`, `missing`, `not_empty`, `contains_any`,
combined with `all`, `any`, `not`.

Besides the manifest attributes, conditions can use these computed facts:

| Fact | Meaning |
|---|---|
| `declared` | At least one declared source knows this agent (false = shadow agent). |
| `has_drift` | Observed attributes exceed the declaration. |
| `unapproved_irreversible_tools` | Irreversible tools with no approval requirement. |
| `code_execution` | A tool runs code or shell commands. |
| `unknown_fields` | Which of autonomy, exposure, data sensitivity, business impact are unknown. |
| `status` | `active` or `stale`. |
| `days_since_seen` | Days since any source last reported the agent. |
| `irreversible_actions`, `privilege_level` | Derived from tools and privileges. |

Finding `detail` text can use `{name}`, `{sources_text}`, `{drift_text}`, `{unapproved_text}`,
`{privileges_text}`, `{unknown_text}` and any attribute name.

## Calibrating for your organization

1. Run `agentposture demo` and the policy against your own agents, then list the ten highest and ten
   lowest. If the order surprises your risk committee, adjust weights before thresholds.
2. Move thresholds so the tier counts match your review capacity: critical should be a list a
   committee can review weekly.
3. Add overrides for combinations your incident history says matter.
4. Add findings for internal standards (for example "production agents need a completed threat
   model", using a manifest field such as `threat_model: <link>` and `{attr: extra.threat_model,
   missing: true}`).
5. Commit the policy file and review changes to it like code.
