"""A realistic sample fleet so you can see the whole product before connecting anything.

``agentposture demo`` uses this. It emits declared manifests, discovered
platform agents that drift from their declarations, and shadow agents nobody
registered, which is what a first scan of a real organization tends to look like.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..models import Evidence
from .base import Connector, register

C_FULL = {"kill_switch": True, "audit_logging": True, "input_guardrails": True,
          "output_guardrails": True, "rate_limit": True}
C_BASIC = {"audit_logging": True, "rate_limit": True}

# (id, team, owner, declared attributes, observed overrides or None, observed-only?)
FLEET: list[tuple[str, str, str | None, dict[str, Any], dict[str, Any] | None, bool]] = [
    ("refund-assistant", "payments", "priya.n@acme.example", dict(
        name="Refund Assistant", lifecycle="production", exposure="customer", autonomy="act_with_approval",
        business_impact="high", data_sensitivity="confidential", data_types=["pii", "financial"],
        tools=[{"name": "lookup_order"}, {"name": "issue_refund", "action": "irreversible",
                                           "requires_approval": True}],
        controls=C_FULL), {"privileges": ["payments:refund:write", "orders:read"]}, False),
    ("chargeback-autopilot", "payments", "marco.r@acme.example", dict(
        name="Chargeback Autopilot", lifecycle="production", exposure="internal", autonomy="autonomous",
        business_impact="critical", data_sensitivity="restricted", data_types=["pci", "financial"],
        tools=[{"name": "fetch_dispute"}, {"name": "submit_evidence"}, {"name": "accept_chargeback",
                                                                         "action": "irreversible"}],
        controls={"audit_logging": True}), {"privileges": ["payments:*"]}, False),
    ("support-triage-bot", "customer-support", "dana.k@acme.example", dict(
        name="Support Triage Bot", lifecycle="production", exposure="public", autonomy="recommend",
        business_impact="medium", data_sensitivity="confidential", data_types=["pii"],
        tools=[{"name": "search_kb"}, {"name": "create_ticket"}], controls=C_FULL), None, False),
    ("support-reply-drafter", "customer-support", "dana.k@acme.example", dict(
        name="Support Reply Drafter", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="low", data_sensitivity="confidential", data_types=["pii"],
        tools=[{"name": "search_kb"}, {"name": "draft_reply"}], controls=C_BASIC), None, False),
    ("account-recovery-agent", "customer-support", "lee.w@acme.example", dict(
        name="Account Recovery Agent", lifecycle="production", exposure="public", autonomy="autonomous",
        business_impact="critical", data_sensitivity="restricted", data_types=["pii", "credentials"],
        tools=[{"name": "verify_identity"}, {"name": "reset_mfa", "action": "irreversible"},
               {"name": "send_reset_email"}],
        controls={"audit_logging": True, "rate_limit": True}), None, False),
    ("sales-email-writer", "growth", "sam.o@acme.example", dict(
        name="Sales Email Writer", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="low", data_sensitivity="internal", tools=[{"name": "crm_lookup"}],
        controls=C_BASIC), None, False),
    ("lead-enrichment-agent", "growth", "sam.o@acme.example", dict(
        name="Lead Enrichment Agent", lifecycle="production", exposure="internal", autonomy="autonomous",
        business_impact="medium", data_sensitivity="confidential", data_types=["pii"],
        tools=[{"name": "web_search"}, {"name": "update_crm_record"}], controls=C_BASIC),
        {"tools": [{"name": "web_search"}, {"name": "update_crm_record"},
                   {"name": "send_outreach_email"}]}, False),
    ("campaign-publisher", "growth", "ivy.t@acme.example", dict(
        name="Campaign Publisher", lifecycle="staging", exposure="public", autonomy="act_with_approval",
        business_impact="medium", data_sensitivity="internal",
        tools=[{"name": "draft_post"}, {"name": "publish_post", "action": "irreversible",
                                         "requires_approval": True}], controls=C_FULL), None, False),
    ("deploy-copilot", "platform", "arjun.m@acme.example", dict(
        name="Deploy Copilot", lifecycle="production", exposure="internal", autonomy="act_with_approval",
        business_impact="critical", data_sensitivity="confidential", data_types=["source_code"],
        tools=[{"name": "read_pipeline"}, {"name": "trigger_deploy", "action": "irreversible",
                                           "requires_approval": True},
               {"name": "rollback_release", "action": "irreversible", "requires_approval": True}],
        controls=C_FULL), None, False),
    ("oncall-remediator", "platform", "arjun.m@acme.example", dict(
        name="On-call Remediator", lifecycle="production", exposure="internal", autonomy="autonomous",
        business_impact="critical", data_sensitivity="confidential",
        tools=[{"name": "read_metrics"}, {"name": "restart_service"},
               {"name": "scale_cluster"}, {"name": "run_command", "action": "irreversible"}],
        controls={"kill_switch": True, "audit_logging": True}),
        {"privileges": ["arn:aws:iam::aws:policy/AdministratorAccess"]}, False),
    ("cost-report-bot", "platform", "nina.b@acme.example", dict(
        name="Cloud Cost Reporter", lifecycle="production", exposure="internal", autonomy="read_only",
        business_impact="low", data_sensitivity="internal", tools=[{"name": "read_billing"}],
        controls=C_BASIC), None, False),
    ("pr-reviewer", "developer-experience", "tom.h@acme.example", dict(
        name="PR Reviewer", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="medium", data_sensitivity="confidential", data_types=["source_code"],
        tools=[{"name": "read_diff"}, {"name": "post_review_comment"}], controls=C_FULL), None, False),
    ("test-writer", "developer-experience", "tom.h@acme.example", dict(
        name="Test Writer", lifecycle="development", exposure="internal", autonomy="act_with_approval",
        business_impact="low", data_sensitivity="confidential", data_types=["source_code"],
        tools=[{"name": "read_repo"}, {"name": "open_pull_request"}], controls=C_BASIC), None, False),
    ("dependency-updater", "developer-experience", None, dict(
        name="Dependency Updater", lifecycle="production", exposure="internal", autonomy="autonomous",
        business_impact="medium", data_sensitivity="confidential", data_types=["source_code"],
        tools=[{"name": "open_pull_request"}, {"name": "merge_pull_request", "action": "irreversible"}],
        controls={"audit_logging": True}), None, False),
    ("threat-intel-summarizer", "security", "kai.s@acme.example", dict(
        name="Threat Intel Summarizer", lifecycle="production", exposure="internal", autonomy="read_only",
        business_impact="medium", data_sensitivity="confidential", tools=[{"name": "read_feeds"}],
        controls=C_FULL), None, False),
    ("phishing-responder", "security", "kai.s@acme.example", dict(
        name="Phishing Responder", lifecycle="production", exposure="internal", autonomy="act_with_approval",
        business_impact="high", data_sensitivity="restricted", data_types=["pii", "credentials"],
        tools=[{"name": "read_mailbox"}, {"name": "quarantine_email", "requires_approval": True},
               {"name": "disable_user", "action": "irreversible", "requires_approval": True}],
        controls=C_FULL), None, False),
    ("access-review-assistant", "security", "rob.g@acme.example", dict(
        name="Access Review Assistant", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="high", data_sensitivity="confidential", data_types=["pii"],
        tools=[{"name": "list_entitlements"}, {"name": "draft_revocation"}], controls=C_FULL),
        {"privileges": ["Microsoft Graph:Directory.ReadWrite.All"]}, False),
    ("pipeline-doctor", "data", "mia.c@acme.example", dict(
        name="Pipeline Doctor", lifecycle="production", exposure="internal", autonomy="act_with_approval",
        business_impact="high", data_sensitivity="restricted", data_types=["pii", "financial"],
        tools=[{"name": "read_dag"}, {"name": "rerun_task"}, {"name": "drop_partition",
                                                               "action": "irreversible", "requires_approval": True}],
        controls=C_FULL), None, False),
    ("sql-analyst", "data", "mia.c@acme.example", dict(
        name="SQL Analyst", lifecycle="production", exposure="internal", autonomy="read_only",
        business_impact="medium", data_sensitivity="restricted", data_types=["pii", "financial"],
        tools=[{"name": "run_query"}], controls={"audit_logging": True}),
        {"privileges": ["warehouse:readwrite"]}, False),
    ("candidate-screener", "people", "zoe.a@acme.example", dict(
        name="Candidate Screener", lifecycle="production", exposure="partner", autonomy="recommend",
        business_impact="high", data_sensitivity="restricted", data_types=["pii"],
        tools=[{"name": "read_resume"}, {"name": "score_candidate"}], controls=C_BASIC), None, False),
    ("benefits-helpdesk", "people", "zoe.a@acme.example", dict(
        name="Benefits Helpdesk", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="medium", data_sensitivity="restricted", data_types=["pii", "phi"],
        tools=[{"name": "search_policies"}, {"name": "lookup_enrollment"}], controls=C_FULL), None, False),
    ("invoice-matcher", "finance", "omar.f@acme.example", dict(
        name="Invoice Matcher", lifecycle="production", exposure="internal", autonomy="act_with_approval",
        business_impact="high", data_sensitivity="confidential", data_types=["financial"],
        tools=[{"name": "read_invoice"}, {"name": "match_po"}, {"name": "approve_payment",
                                                                 "action": "irreversible", "requires_approval": True}],
        controls=C_FULL), None, False),
    ("expense-auditor", "finance", "omar.f@acme.example", dict(
        name="Expense Auditor", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="medium", data_sensitivity="confidential", data_types=["financial", "pii"],
        tools=[{"name": "read_expenses"}, {"name": "flag_expense"}], controls=C_FULL), None, False),
    ("contract-redliner", "legal", "ana.p@acme.example", dict(
        name="Contract Redliner", lifecycle="production", exposure="internal", autonomy="recommend",
        business_impact="medium", data_sensitivity="confidential",
        tools=[{"name": "read_contract"}, {"name": "suggest_edits"}], controls=C_FULL), None, False),
    ("old-faq-bot", "customer-support", "former.employee@acme.example", dict(
        name="Legacy FAQ Bot", lifecycle="deprecated", exposure="public", autonomy="recommend",
        business_impact="low", data_sensitivity="internal", tools=[{"name": "search_faq"}],
        controls={}), {"last_active": "recent"}, False),
    # --- shadow agents: discovered, never declared --------------------------------------
    ("repo:acme/growth-hacks", "", None, dict(
        name="acme/growth-hacks", repo="acme/growth-hacks", frameworks=["langchain", "openai"],
        tools=[{"name": "scrape_profiles"}, {"name": "send_bulk_email"}], autonomy="autonomous",
        credential_type="hardcoded_key"), None, True),
    ("repo:acme/finance-scripts", "", None, dict(
        name="acme/finance-scripts", repo="acme/finance-scripts", frameworks=["crewai", "anthropic"],
        tools=[{"name": "read_ledger"}, {"name": "post_journal_entry"}]), None, True),
    ("repo:acme/ops-mcp", "", None, dict(
        name="acme/ops-mcp", repo="acme/ops-mcp", frameworks=["mcp-server"],
        tools=[{"name": "mcp:shell", "action": "irreversible"}, {"name": "mcp:kubernetes",
                                                                    "action": "irreversible"}]), None, True),
    ("sp-hackathon-agent", "", None, dict(
        name="hackathon-slack-agent", identity="3f1c9a70-hackathon",
        privileges=["Microsoft Graph:Mail.ReadWrite", "Microsoft Graph:Chat.ReadWrite.All"],
        credential_type="client_secret"), None, True),
]


@register
class DemoConnector(Connector):
    type_name = "demo"
    evidence_kind = "declared"
    description = "A realistic sample fleet for trying AgentPosture without connecting anything."
    options = {}

    def discover(self) -> Iterable[Evidence]:
        for agent_id, team, owner, declared, observed, shadow in FLEET:
            if shadow:
                platform = "entra_id" if agent_id.startswith("sp-") else "code_scan"
                attrs = dict(declared)
                attrs["platform"] = platform
                fps = [f"identity:{attrs['identity']}"] if "identity" in attrs else [agent_id]
                yield self.evidence(agent_id, attrs, fps, kind="observed")
                continue
            attrs = dict(declared, id=agent_id, team=team)
            if owner:
                attrs["owner"] = owner
            yield self.evidence(agent_id, attrs, [f"repo:acme/{agent_id}"], kind="declared")
            if observed is not None:
                obs = {"name": declared["name"], "tools": declared.get("tools", [])}
                obs.update({k: v for k, v in observed.items() if k != "last_active"})
                obs["platform"] = "aws_bedrock"
                yield self.evidence(f"arn:aws:bedrock:us-east-1:123456789012:agent/{agent_id}",
                                    obs, [f"repo:acme/{agent_id}"], kind="observed")
