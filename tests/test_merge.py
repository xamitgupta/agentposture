from agentposture.merge import group_evidence, merge_evidence
from agentposture.models import Evidence
from agentposture.normalize import normalize_attributes


def ev(source, ext, kind, attrs, fps=()):
    return Evidence(source=source, source_type=source, external_id=ext, kind=kind,
                    attributes=normalize_attributes(attrs), fingerprints=list(fps))


def test_evidence_joins_on_shared_fingerprints_transitively():
    items = [ev("manifest", "bot", "declared", {"id": "bot"}, ["repo:acme/bot"]),
             ev("code", "r", "observed", {"name": "acme/bot"}, ["repo:acme/bot", "identity:123"]),
             ev("entra", "123", "observed", {"name": "sp"}, ["identity:123"]),
             ev("code", "other", "observed", {"name": "other"})]
    groups = group_evidence(items)
    assert sorted(len(g) for g in groups) == [1, 3]


def test_merge_is_risk_conservative_and_records_drift():
    items = [ev("manifest", "bot", "declared",
                {"id": "bot", "name": "Bot", "owner": "a@x.io", "autonomy": "recommend",
                 "exposure": "internal", "tools": ["search"]}, ["repo:acme/bot"]),
             ev("aws", "arn", "observed",
                {"name": "bot-prod", "autonomy": "autonomous", "exposure": "internal",
                 "tools": ["search", "delete_records"], "owner": "someone@else.io"}, ["repo:acme/bot"])]
    [agent] = merge_evidence(items)
    assert agent.id == "bot"
    assert agent.attributes["name"] == "Bot"              # declared wins for identity fields
    assert agent.attributes["owner"] == "a@x.io"
    assert agent.attributes["autonomy"] == "autonomous"   # riskier observation wins
    assert agent.attributes["irreversible_actions"] is True
    drifted = {d["attribute"] for d in agent.drift}
    assert {"autonomy", "tools"} <= drifted
    assert agent.is_declared


def test_undeclared_agent_gets_a_stable_generated_id():
    a1 = merge_evidence([ev("code", "x", "observed", {"name": "Shadow Thing"})])[0]
    a2 = merge_evidence([ev("code", "x", "observed", {"name": "Shadow Thing"})])[0]
    assert a1.id == a2.id and a1.id.startswith("shadow-thing-")
    assert not a1.is_declared
