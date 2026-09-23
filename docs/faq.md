# FAQ

**Do we need an agent registry before using this?**
No. Start with `code_scan` or `github` plus your identity provider, and AgentPosture builds the
inventory from what it finds. Every undeclared agent shows up as a shadow agent with an owner-less
finding, which is your registration backlog. If you already have a registry, connect it with
`http_json` and it becomes one of the declared sources.

**How is this different from an AI security posture management (AI-SPM) product?**
It is narrower and open: an inventory and a transparent, editable risk model for agents, designed
to be adopted in an afternoon. It does not inspect prompts or traffic at runtime. It pairs well
with runtime guardrails and gateways, whose presence it records as controls.

**Why SQLite?**
It removes a database from the adoption path, needs no operations, and handles tens of thousands of
agents. Back it up as a file.

**Why is my agent high when it has every control?**
Controls reduce inherent risk by up to 35%. An autonomous agent that can move money for customers is
still a high-risk agent when well controlled; the tier tells leadership where exposure is, and the
empty findings list tells them it is managed. Adjust `controls.max_reduction` or thresholds in your
policy if your risk appetite differs.

**Why are unknown values scored as risky?**
So missing information can never make an agent look safe, and so owners have a reason to complete
their records. The finding AP-014 lists exactly which fields are missing.

**A declared agent and a discovered one are the same thing but show twice. Why?**
They share no join key. Add `links:` to the manifest (for example `identity:` with the service
principal id, or `repo:` with `owner/name`), or keep one manifest per repository so the repository
link is added automatically.

**Can I change the scoring?**
Yes. `agentposture policy -o policy.yaml`, edit, and set `policy: ./policy.yaml`. See
`docs/scoring.md`. Every agent is reassessed on the next reconcile.

**Does it change anything in the systems it scans?**
No. Every connector is read-only.

**Can I run it without a server?**
Yes. `agentposture scan` and `agentposture report -f html -o posture.html` produce a self-contained
dashboard file. `agentposture check` scores manifests in CI with no database at all.

**How do I map findings to our control framework?**
Add your control ids to the `frameworks:` list of each finding in your policy. They appear in the
dashboard and reports.
