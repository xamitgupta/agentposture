"""Score an agent: dimension levels -> weighted score -> tier -> overrides -> findings.

Every number in an assessment can be traced back to an attribute and a policy
line, so an owner can always answer "why is my agent High?".
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from ..models import (
    AUTONOMY,
    BUSINESS_IMPACT,
    DATA_SENSITIVITY,
    EXPOSURE,
    PRIVILEGE_LEVEL,
    TIERS,
    Agent,
    Assessment,
    Finding,
    ordinal,
    parse_ts,
)
from .policy import Policy, evaluate

_CODE_EXEC = re.compile(r"(run_command|shell|exec|code_interpreter|terminal|python_repl|eval)", re.I)
_REQUIRED = ("autonomy", "exposure", "data_sensitivity", "business_impact")
_LABELS = {"autonomy": AUTONOMY, "privilege": PRIVILEGE_LEVEL, "data_sensitivity": DATA_SENSITIVITY,
           "exposure": EXPOSURE, "business_impact": BUSINESS_IMPACT,
           "ownership": ["owner and team", "owner only", "team only", "nobody"]}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "unknown"


def _fmt_list(items: list[Any], limit: int = 4) -> str:
    items = [str(i) for i in items]
    if not items:
        return "none"
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def build_facts(agent: Agent, now: datetime | None = None) -> dict[str, Any]:
    """Everything a policy condition can refer to."""
    now = now or datetime.now(timezone.utc)
    a = copy.deepcopy(agent.attributes)
    facts: dict[str, Any] = dict(a)
    facts["controls"] = a.get("controls", {})
    facts["declared"] = agent.is_declared
    facts["observed"] = bool(agent.observed)
    facts["status"] = agent.status
    facts["has_drift"] = bool(agent.drift)
    facts["drift_text"] = "; ".join(
        f"{d['attribute'].replace('_', ' ')} declared {_fmt_list(d['declared']) if isinstance(d['declared'], list) else d['declared']}"
        f", observed {_fmt_list(d['observed']) if isinstance(d['observed'], list) else d['observed']}"
        for d in agent.drift)
    approval = set(facts["controls"].get("human_approval", []))
    tools = a.get("tools", [])
    facts["unapproved_irreversible_tools"] = [] if "*" in approval else sorted(
        t["name"] for t in tools if t["action"] == "irreversible"
        and t["name"] not in approval and not t.get("requires_approval"))
    facts["unapproved_text"] = _fmt_list(facts["unapproved_irreversible_tools"])
    facts["_irreversible_tools"] = [t["name"] for t in tools if t["action"] == "irreversible"]
    facts["code_execution"] = any(_CODE_EXEC.search(t["name"]) for t in tools)
    facts["unknown_fields"] = [f for f in _REQUIRED if ordinal(f, a.get(f)) is None]
    facts["unknown_text"] = _fmt_list(facts["unknown_fields"])
    facts["privileges_text"] = _fmt_list(a.get("privileges", []))
    facts["sources_text"] = _fmt_list(agent.sources)
    facts["hardcoded_text"] = _fmt_list((a.get("extra") or {}).get("hardcoded_key_files", []) or ["source"])
    seen = parse_ts(agent.last_seen)
    facts["days_since_seen"] = (now - seen).days if seen else 0
    facts["name"] = agent.name
    return facts


def _dimension_levels(facts: dict[str, Any], policy: Policy) -> dict[str, dict[str, Any]]:
    dims: dict[str, dict[str, Any]] = {}

    def ordinal_dim(key: str, attr: str) -> None:
        lvl = ordinal(attr, facts.get(attr))
        known = lvl is not None
        dims[key] = {"level": lvl if known else policy.unknown_levels[key],
                     "value": facts.get(attr) if known else "unknown", "known": known}

    ordinal_dim("autonomy", "autonomy")
    ordinal_dim("exposure", "exposure")
    ordinal_dim("business_impact", "business_impact")

    ordinal_dim("privilege", "privilege_level")
    if facts.get("irreversible_actions"):
        dims["privilege"].update(level=3, value="irreversible actions", known=True)

    ordinal_dim("data_sensitivity", "data_sensitivity")
    types = set(facts.get("data_types") or [])
    for level_name in ("confidential", "restricted"):
        if types & set(policy.sensitive_types.get(level_name, [])):
            floor = DATA_SENSITIVITY.index(level_name)
            d = dims["data_sensitivity"]
            if not d["known"] or d["level"] < floor:
                d.update(level=max(floor, d["level"] if d["known"] else floor),
                         value=f"{level_name} (holds {_fmt_list(sorted(types))})", known=True)

    owner, team = bool(facts.get("owner")), bool(facts.get("team"))
    lvl = 0 if owner and team else 1 if owner else 2 if team else 3
    dims["ownership"] = {"level": lvl, "value": _LABELS["ownership"][lvl], "known": True}

    for key, d in dims.items():
        d["weight"] = policy.weights[key]
    return dims


def _score(dims: dict[str, dict[str, Any]]) -> float:
    dims = {k: v for k, v in dims.items() if not k.startswith("_")}
    total = sum(d["weight"] for d in dims.values())
    raw = sum(d["weight"] * d["level"] / 3 for d in dims.values())
    return round(100 * raw / total, 1) if total else 0.0


def control_coverage(facts: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Which controls apply to this agent, and which of those are in place."""
    c = facts.get("controls") or {}
    def level(attr: str, unknown: int) -> int:
        v = ordinal(attr, facts.get(attr))
        return unknown if v is None else v

    acts = level("autonomy", 3) >= AUTONOMY.index("act_with_approval")
    writes = bool(facts.get("irreversible_actions")) or level("privilege_level", 2) >= 2
    sensitive = level("data_sensitivity", 3) >= 2
    outside = level("exposure", 3) >= 1
    irreversible = bool(facts.get("_irreversible_tools"))
    rules = {
        "human_approval": (irreversible, irreversible and not facts.get("unapproved_irreversible_tools")),
        "kill_switch": (acts, bool(c.get("kill_switch"))),
        "audit_logging": (writes or sensitive, bool(c.get("audit_logging"))),
        "input_guardrails": (outside, bool(c.get("input_guardrails"))),
        "output_guardrails": (outside and sensitive, bool(c.get("output_guardrails"))),
        "rate_limit": (facts.get("exposure") == "public", bool(c.get("rate_limit"))),
        "sandboxed": (bool(facts.get("code_execution")), bool(c.get("sandboxed"))),
    }
    return {k: {"applies": bool(a), "in_place": bool(a and p)} for k, (a, p) in rules.items()}


def _mitigation(facts: dict[str, Any], policy: Policy) -> tuple[float, dict[str, Any]]:
    cov = control_coverage(facts)
    applicable = {k: w for k, w in policy.control_weights.items() if cov[k]["applies"]}
    total = sum(applicable.values())
    present = sum(w for k, w in applicable.items() if cov[k]["in_place"])
    ratio = present / total if total else 0.0
    return ratio * policy.max_reduction, cov


def _tier(facts: dict[str, Any], policy: Policy) -> tuple[float, str, list[str], dict[str, Any]]:
    dims = _dimension_levels(facts, policy)
    inherent = _score(dims)
    reduction, cov = _mitigation(facts, policy)
    score = round(inherent * (1 - reduction), 1)
    dims["_meta"] = {"inherent_score": inherent, "reduction": round(reduction * 100, 1),
                     "controls": cov}
    tier = policy.tier_for(score)
    applied = []
    for o in policy.overrides:
        if evaluate(o["when"], facts):
            applied.append(o["id"])
            if TIERS.index(o["min_tier"]) > TIERS.index(tier):
                tier = o["min_tier"]
    return score, tier, applied, dims


def _apply_fix(facts: dict[str, Any], fix: dict[str, Any]) -> dict[str, Any]:
    patched = copy.deepcopy(facts)
    for path, value in fix.items():
        parts = path.split(".")
        cur = patched
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return patched


def assess(agent: Agent, policy: Policy, now: datetime | None = None) -> Assessment:
    facts = build_facts(agent, now)
    score, tier, applied, dims = _tier(facts, policy)
    meta = dims.pop("_meta")
    findings: list[Finding] = []
    all_fixes: dict[str, Any] = {}
    for rule in policy.findings:
        if not evaluate(rule["when"], facts):
            continue
        tier_if_fixed = None
        if rule.get("fix"):
            _, fixed_tier, _, _ = _tier(_apply_fix(facts, rule["fix"]), policy)
            tier_if_fixed = fixed_tier
            all_fixes.update(rule["fix"])
        findings.append(Finding(
            rule_id=rule["id"], title=rule["title"], severity=rule["severity"],
            detail=str(rule.get("detail", rule["title"])).format_map(_SafeDict(
                {k: (v if not isinstance(v, list) else _fmt_list(v)) for k, v in facts.items()})),
            remediation=str(rule["remediation"]).strip(),
            frameworks=list(rule.get("frameworks", [])), tier_if_fixed=tier_if_fixed))
    sev = {s: i for i, s in enumerate(("critical", "high", "medium", "low"))}
    findings.sort(key=lambda f: (TIERS.index(f.tier_if_fixed or tier) - TIERS.index(tier),
                                 sev[f.severity], f.rule_id))
    target_tier = _tier(_apply_fix(facts, all_fixes), policy)[1] if all_fixes else tier
    return Assessment(agent_id=agent.id, score=score, tier=tier, dimensions=dims,
                      findings=findings, overrides=applied, policy_hash=policy.hash,
                      inherent_score=meta["inherent_score"], control_reduction=meta["reduction"],
                      controls=meta["controls"], target_tier=target_tier)
