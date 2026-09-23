"""AWS Bedrock Agents: every agent, its action groups, guardrails and IAM role permissions.

Requires ``pip install "agentposture[aws]"`` and read-only credentials from the
standard AWS chain (env vars, profile, or instance role). Minimum IAM actions:
bedrock:ListAgents, bedrock:GetAgent, bedrock:ListAgentActionGroups,
bedrock:GetAgentActionGroup, bedrock:ListAgentKnowledgeBases, iam:ListAttachedRolePolicies,
iam:ListRolePolicies, iam:GetRolePolicy, iam:GetPolicy, iam:GetPolicyVersion.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterable
from typing import Any

from ..models import Evidence
from .base import Connector, ConnectorError, register


def _actions(doc: Any) -> list[str]:
    if isinstance(doc, str):
        doc = json.loads(urllib.parse.unquote(doc))
    out: list[str] = []
    stmts = doc.get("Statement", []) if isinstance(doc, dict) else []
    for st in stmts if isinstance(stmts, list) else [stmts]:
        if st.get("Effect") != "Allow":
            continue
        acts = st.get("Action", [])
        acts = [acts] if isinstance(acts, str) else acts
        resources = st.get("Resource", [])
        resources = [resources] if isinstance(resources, str) else resources
        for a in acts:
            out.append(f"{a}" + (" on *" if "*" in resources else ""))
    return out


@register
class AwsBedrockConnector(Connector):
    type_name = "aws_bedrock"
    evidence_kind = "observed"
    description = "Bedrock Agents across regions, with action groups, guardrails and IAM role scope."
    options = {"regions": "Regions to scan (default: us-east-1).",
               "profile": "Optional AWS profile name.",
               "inspect_iam": "Read the agent role's IAM policies (default true)."}

    def discover(self) -> Iterable[Evidence]:
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise ConnectorError('aws_bedrock needs boto3: pip install "agentposture[aws]"') from exc
        session = boto3.Session(profile_name=self.option("profile")) if self.option("profile") \
            else boto3.Session()
        iam = session.client("iam") if self.option("inspect_iam", True) else None
        for region in self.option("regions", ["us-east-1"]):
            client = session.client("bedrock-agent", region_name=region)
            try:
                pages = client.get_paginator("list_agents").paginate()
                summaries = [a for page in pages for a in page.get("agentSummaries", [])]
            except Exception as exc:  # botocore errors vary by version
                raise ConnectorError(f"{region}: cannot list Bedrock agents: {exc}") from exc
            for s in summaries:
                yield self._agent(client, iam, region, s["agentId"])

    def _agent(self, client: Any, iam: Any, region: str, agent_id: str) -> Evidence:
        agent = client.get_agent(agentId=agent_id)["agent"]
        tools: list[dict[str, Any]] = []
        groups = client.list_agent_action_groups(agentId=agent_id, agentVersion="DRAFT") \
            .get("actionGroupSummaries", [])
        for g in groups:
            if g.get("actionGroupState") == "DISABLED":
                continue
            detail = client.get_agent_action_group(
                agentId=agent_id, agentVersion="DRAFT", actionGroupId=g["actionGroupId"]
            ).get("agentActionGroup", {})
            functions = (detail.get("functionSchema") or {}).get("functions") or []
            if functions:
                for fn in functions:
                    tools.append({"name": fn["name"], "system": g.get("actionGroupName"),
                                  "requires_approval": fn.get("requireConfirmation") == "ENABLED"})
            else:
                tools.append({"name": g.get("actionGroupName", g["actionGroupId"]),
                              "system": g.get("actionGroupName")})
            sig = detail.get("parentActionGroupSignature")
            if sig == "AMAZON.CodeInterpreter":
                tools.append({"name": "code_interpreter", "action": "irreversible"})

        kbs = client.list_agent_knowledge_bases(agentId=agent_id, agentVersion="DRAFT") \
            .get("agentKnowledgeBaseSummaries", [])
        role_arn = agent.get("agentResourceRoleArn")
        privileges = self._role_actions(iam, role_arn) if iam and role_arn else []
        guard = agent.get("guardrailConfiguration") or {}
        attrs: dict[str, Any] = {
            "name": agent.get("agentName", agent_id),
            "description": agent.get("description"),
            "model": agent.get("foundationModel"),
            "lifecycle": "production" if agent.get("agentStatus") == "PREPARED" else "development",
            "tools": tools,
            "privileges": privileges,
            "identity": role_arn,
            "runtime": f"aws:{region}",
            "controls": {"input_guardrails": bool(guard), "output_guardrails": bool(guard)},
            "extra": {"knowledge_bases": [k.get("knowledgeBaseId") for k in kbs],
                      "agent_status": agent.get("agentStatus")},
        }
        arn = agent.get("agentArn", f"{region}:{agent_id}")
        fps = [f"aws_bedrock:{arn}"] + ([f"identity:{role_arn}"] if role_arn else [])
        return self.evidence(arn, attrs, fps)

    @staticmethod
    def _role_actions(iam: Any, role_arn: str) -> list[str]:
        role = role_arn.split("/")[-1]
        actions: list[str] = []
        try:
            for name in iam.list_role_policies(RoleName=role).get("PolicyNames", []):
                actions += _actions(iam.get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"])
            for p in iam.list_attached_role_policies(RoleName=role).get("AttachedPolicies", []):
                if p["PolicyName"] in ("AdministratorAccess", "PowerUserAccess"):
                    actions.append(f"{p['PolicyName']} (admin)")
                    continue
                ver = iam.get_policy(PolicyArn=p["PolicyArn"])["Policy"]["DefaultVersionId"]
                doc = iam.get_policy_version(PolicyArn=p["PolicyArn"], VersionId=ver)
                actions += _actions(doc["PolicyVersion"]["Document"])
        except Exception:
            actions.append("unreadable-role-policy")
        return sorted(set(actions))
