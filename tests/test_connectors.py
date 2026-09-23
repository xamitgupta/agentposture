import json

import pytest

from agentposture.config import SourceConfig
from agentposture.connectors import ConnectorError, available_connectors, get_connector
from conftest import write


def run(type_name, base, **options):
    src = SourceConfig(name=type_name, type=type_name, options=options)
    return list(get_connector(type_name)(src, base_dir=base).discover())


def test_all_builtins_are_registered():
    assert {"manifest", "csv", "code_scan", "github", "aws_bedrock", "entra_id", "http_json",
            "demo"} <= set(available_connectors())


def test_manifest_single_multi_and_list_forms(tmp_path):
    write(tmp_path / "a" / "agent.yaml", """
        id: one
        name: One
        owner: a@x.io
        links: {identity: abc}
    """)
    write(tmp_path / "b" / "fleet.agent.yaml", """
        agents:
          - {id: two, name: Two}
          - {id: three, name: Three}
    """)
    items = run("manifest", tmp_path, paths=["."])
    assert sorted(e.external_id for e in items) == ["one", "three", "two"]
    one = next(e for e in items if e.external_id == "one")
    assert one.kind == "declared" and "identity:abc" in one.fingerprints and "id:one" in one.fingerprints


def test_manifest_in_git_repo_links_repo_when_alone(tmp_path):
    repo = tmp_path / "svc"
    write(repo / ".git" / "config", '[remote "origin"]\n\turl = git@github.com:Acme/Svc.git\n')
    write(repo / "agent.yaml", "id: svc-agent\n")
    [e] = run("manifest", tmp_path, paths=["."])
    assert "repo:acme/svc" in e.fingerprints


def test_manifest_errors_are_readable(tmp_path):
    write(tmp_path / "agent.yaml", "name: [unclosed\n")
    with pytest.raises(ConnectorError, match="invalid YAML"):
        run("manifest", tmp_path, paths=["."])


def test_csv(tmp_path):
    write(tmp_path / "agents.csv", """\
        id,name,owner,autonomy,tools,kill_switch,link_identity
        bot,Bot,b@x.io,autonomous,"search;delete_user",yes,spn-1
    """)
    [e] = run("csv", tmp_path, path="agents.csv")
    assert e.attributes["autonomy"] == "autonomous"
    assert e.attributes["controls"]["kill_switch"] is True
    assert e.attributes["irreversible_actions"] is True
    assert "identity:spn-1" in e.fingerprints


def test_code_scan_finds_agents_tools_hints_and_keys(tmp_path):
    repo = tmp_path / "growth"
    write(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    write(repo / "requirements.txt", "langchain==0.3\nopenai\n")
    write(repo / "bot.py", '''
        from langchain.tools import tool
        client_key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"

        @tool
        def send_bulk_email(to: str) -> str:
            return "ok"

        agent = make(model="gpt-4o", human_input_mode="NEVER")
    ''')
    write(repo / ".mcp.json", json.dumps({"mcpServers": {"filesystem": {}, "weather": {}}}))
    write(tmp_path / "plain" / "main.py", "print('no agents here')\n")
    [e] = run("code_scan", tmp_path, paths=["."])
    a = e.attributes
    assert a["name"] == "growth" and "repo:growth" in e.fingerprints
    assert "langchain" in a["frameworks"]
    names = {t["name"]: t["action"] for t in a["tools"]}
    assert names["send_bulk_email"] == "write"
    assert names["mcp:filesystem"] == "irreversible"
    assert a["autonomy"] == "autonomous"
    assert a["credential_type"] == "hardcoded_key"
    assert a["model"] == "gpt-4o"


def test_http_json_file_with_mapping(tmp_path):
    write(tmp_path / "reg.json", json.dumps({"data": {"items": [
        {"agent_id": "r1", "display": "Registry Bot", "risk": {"autonomy": "supervised"},
         "sp": "abc", "owner": {"email": "r@x.io"}}]}}))
    [e] = run("http_json", tmp_path, file="reg.json", items_path="data.items", id_field="agent_id",
              mapping={"name": "display", "autonomy": "risk.autonomy", "owner": "owner.email"},
              links={"identity": "sp"})
    assert e.attributes["name"] == "Registry Bot"
    assert e.attributes["autonomy"] == "act_with_approval"
    assert e.attributes["owner"] == "r@x.io"
    assert "identity:abc" in e.fingerprints


def test_webhook_signature_verification():
    import hashlib
    import hmac
    src = SourceConfig(name="gh", type="github", webhook_secret="shh", options={"org": "acme"})
    conn = get_connector("github")(src)
    body = b'{"ref":"main"}'
    sig = "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()
    assert conn.verify_webhook({"X-Hub-Signature-256": sig}, body)
    assert not conn.verify_webhook({"X-Hub-Signature-256": "sha256=bad"}, body)
