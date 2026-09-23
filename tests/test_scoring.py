import pytest

from agentposture.engine import PolicyError, assess, load_policy
from agentposture.engine.policy import Policy, evaluate
from agentposture.merge import merge_evidence
from agentposture.models import Evidence
from agentposture.normalize import normalize_attributes


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def agent(kind="declared", **attrs):
    attrs.setdefault("id", "a1")
    e = Evidence(source="s", source_type="t", external_id="a1", kind=kind,
                 attributes=normalize_attributes(attrs))
    return merge_evidence([e])[0]


SAFE = dict(owner="o@x.io", team="t", autonomy="read_only", exposure="internal",
            data_sensitivity="internal", business_impact="low", tools=[{"name": "search", "action": "read"}])


def test_low_risk_agent_is_low_with_no_findings(policy):
    r = assess(agent(**SAFE), policy)
    assert r.tier == "low"
    assert r.findings == []


def test_unknown_values_score_as_risky(policy):
    r = assess(agent(owner="o@x.io", team="t"), policy)
    assert r.inherent_score > assess(agent(**SAFE), policy).inherent_score
    assert "AP-014" in [f.rule_id for f in r.findings]


def test_override_forces_critical(policy):
    r = assess(agent(**{**SAFE, "autonomy": "autonomous", "exposure": "public",
                        "tools": [{"name": "issue_refund"}]}), policy)
    assert r.tier == "critical"
    assert "autonomous-irreversible-external" in r.overrides
    ap004 = next(f for f in r.findings if f.rule_id == "AP-004")
    assert ap004.severity == "critical"
    assert "issue_refund" in ap004.detail


def test_controls_reduce_residual_risk(policy):
    base = {**SAFE, "autonomy": "act_with_approval", "exposure": "customer", "data_sensitivity": "confidential",
            "business_impact": "high", "tools": [{"name": "refund", "action": "irreversible", "requires_approval": True}]}
    bare = assess(agent(**base), policy)
    full = assess(agent(**base, controls={"kill_switch": True, "audit_logging": True, "input_guardrails": True,
                                         "output_guardrails": True}), policy)
    assert bare.inherent_score == full.inherent_score
    assert full.score < bare.score
    assert full.control_reduction == pytest.approx(35.0)
    assert full.controls["human_approval"] == {"applies": True, "in_place": True}
    assert full.controls["rate_limit"]["applies"] is False


def test_findings_report_tier_if_fixed_and_target(policy):
    r = assess(agent(**{**SAFE, "autonomy": "act_with_approval", "exposure": "customer",
                        "data_sensitivity": "confidential", "business_impact": "high",
                        "tools": [{"name": "create_ticket"}]}), policy)
    assert {f.rule_id for f in r.findings} >= {"AP-005", "AP-006", "AP-007", "AP-008"}
    assert r.target_tier is not None
    assert ["low", "medium", "high", "critical"].index(r.target_tier) <= \
        ["low", "medium", "high", "critical"].index(r.tier)


def test_shadow_agent_that_can_write_is_at_least_high(policy):
    r = assess(agent(kind="observed", name="x", tools=[{"name": "update_record"}]), policy)
    assert r.tier in ("high", "critical")
    assert "shadow-agent-can-act" in r.overrides
    assert "AP-002" in [f.rule_id for f in r.findings]


def test_sensitive_data_types_raise_sensitivity(policy):
    r = assess(agent(**{**SAFE, "data_types": ["phi"]}), policy)
    assert r.dimensions["data_sensitivity"]["level"] == 3


def test_condition_language():
    facts = {"autonomy": "autonomous", "controls": {"kill_switch": False}, "data_types": ["pii"], "owner": None}
    assert evaluate({"attr": "autonomy", "at_least": "act_with_approval"}, facts)
    assert evaluate({"attr": "controls.kill_switch", "is_not": True}, facts)
    assert evaluate({"attr": "data_types", "contains_any": ["pii", "phi"]}, facts)
    assert evaluate({"attr": "owner", "missing": True}, facts)
    assert evaluate({"all": [{"attr": "autonomy", "is": "autonomous"}, {"not": {"attr": "owner", "not_empty": True}}]}, facts)
    assert not evaluate({"any": [{"attr": "autonomy", "is": "read_only"}]}, facts)


def test_policy_validation_errors_are_clear():
    with pytest.raises(PolicyError, match="unknown dimension"):
        Policy.from_dict({"version": 1, "dimensions": {"vibes": {"weight": 1}}})
    with pytest.raises(PolicyError, match="min_tier"):
        Policy.from_dict({"version": 1, "dimensions": {"autonomy": {"weight": 1}},
                          "overrides": [{"id": "x", "min_tier": "severe", "when": {"attr": "a", "is": 1}}]})
    with pytest.raises(PolicyError, match="unknown operator"):
        Policy.from_dict({"version": 1, "dimensions": {"autonomy": {"weight": 1}},
                          "findings": [{"id": "X", "title": "t", "severity": "low", "remediation": "r",
                                        "when": {"attr": "a", "equals": 1}}]})


def test_default_policy_hash_is_stable(policy):
    assert policy.hash == load_policy().hash
