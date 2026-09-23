import json
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from agentposture.cli import main
from agentposture.config import SourceConfig
from agentposture.report import render
from agentposture.server import _State, make_handler
from conftest import write


def test_demo_fleet_end_to_end(demo_service):
    s = demo_service.summary()
    t = s["totals"]
    assert t["agents"] == 29
    assert t["shadow"] == 4 and t["drift"] >= 4 and t["needs_action"] > 0
    assert sum(t["by_tier"].values()) == 29
    assert s["attention"][0]["tier"] == "critical"
    assert {c["control"] for c in s["controls"]} >= {"kill_switch", "human_approval"}
    d = demo_service.agent_detail("chargeback-autopilot")
    assert d["assessment"]["tier"] == "critical" and d["agent"]["drift"]


def test_reassessment_only_when_needed(demo_service):
    agents, reassessed = demo_service.reconcile()
    assert agents == 29 and reassessed == 0
    assert demo_service.reconcile(force=True)[1] == 29


def test_changes_trigger_reassessment_and_history(make_service, tmp_path):
    m = write(tmp_path / "agent.yaml", "id: bot\nowner: a@x.io\nteam: t\nautonomy: read_only\n")
    svc = make_service([SourceConfig(name="m", type="manifest", options={"paths": ["."]})])
    svc.scan()
    first = svc.agent_detail("bot")["assessment"]
    m.write_text("id: bot\nowner: a@x.io\nteam: t\nautonomy: autonomous\n")
    report = svc.scan()
    assert report.reassessed == 1
    d = svc.agent_detail("bot")
    assert d["assessment"]["score"] > first["score"] and len(d["history"]) == 2


def test_stale_agents_are_flagged(make_service, tmp_path):
    write(tmp_path / "agent.yaml", "id: bot\n")
    svc = make_service([SourceConfig(name="m", type="manifest", options={"paths": ["."]})], stale_after=60)
    svc.scan()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    svc.store._q("UPDATE evidence SET last_seen=?", (old,))
    svc.reconcile()
    row = svc.agents_view()[0]
    assert "stale" in row["flags"]
    assert "AP-012" in [f["rule_id"] for f in svc.agent_detail("bot")["assessment"]["findings"]]


def test_failing_source_does_not_block_others(make_service, tmp_path):
    write(tmp_path / "agent.yaml", "id: bot\n")
    svc = make_service([SourceConfig(name="missing", type="csv", options={"path": "nope.csv"}),
                        SourceConfig(name="m", type="manifest", options={"paths": ["."]})])
    report = svc.scan()
    assert report.sources["missing"]["status"] == "error" and report.sources["m"]["status"] == "ok"
    assert report.agents == 1 and not report.ok


def test_api_registration_joins_discovered_agent(make_service):
    svc = make_service([SourceConfig(name="demo", type="demo")])
    svc.scan()
    svc.register({"id": "new-bot", "name": "New Bot", "owner": "n@x.io", "autonomy": "recommend"})
    assert svc.agent_detail("new-bot")["agent"]["sources"] == ["api"]
    assert svc.unregister("new-bot") and svc.agent_detail("new-bot") is None


@pytest.mark.parametrize("fmt", ["html", "json", "md", "csv"])
def test_reports_render(demo_service, fmt):
    out = render(demo_service.export(), fmt)
    assert "Chargeback Autopilot" in out
    if fmt == "html":
        assert '<script id="snapshot"' in out and "app.js" not in out.split("<script id")[0][-200:]


@pytest.fixture
def server(demo_service):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(_State(demo_service)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.headers, r.read()


def test_server_reads_and_dashboard(server):
    status, headers, body = get(server + "/api/summary")
    assert status == 200 and json.loads(body)["totals"]["agents"] == 29
    assert json.loads(get(server + "/api/agents?tier=critical")[2])[0]["tier"] == "critical"
    assert json.loads(get(server + "/api/agents/refund-assistant")[2])["agent"]["id"] == "refund-assistant"
    status, headers, body = get(server + "/")
    assert b"AgentPosture" in body and "default-src 'self'" in headers["Content-Security-Policy"]
    assert get(server + "/app.js")[0] == 200
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + "/../pyproject.toml")
    assert e.value.code == 404


def test_server_writes_from_loopback_and_webhook_rejects_bad_signature(server):
    req = urllib.request.Request(server + "/api/agents", method="POST",
                                 data=json.dumps({"id": "via-api", "name": "Via API"}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 201
    req = urllib.request.Request(server + "/api/webhooks/demo", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code in (401, 403)


def test_token_is_required_when_configured(demo_service):
    demo_service.config.api_token = "t0ken"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(_State(demo_service)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/api/scan"
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(url, method="POST", data=b"{}"))
        assert e.value.code == 401
        ok = urllib.request.Request(url, method="POST", data=b"{}", headers={"Authorization": "Bearer t0ken"})
        with urllib.request.urlopen(ok) as r:
            assert r.status in (202, 409)
    finally:
        httpd.shutdown()


def test_cli_check_gates_on_tier(tmp_path, capsys):
    write(tmp_path / "safe" / "agent.yaml", """
        id: safe
        owner: a@x.io
        team: t
        autonomy: read_only
        exposure: internal
        business_impact: low
        data: {sensitivity: internal}
    """)
    write(tmp_path / "risky" / "agent.yaml", """
        id: risky
        autonomy: autonomous
        exposure: public
        tools: [issue_refund]
    """)
    assert main(["check", str(tmp_path / "safe"), "--fail-on", "high"]) == 0
    assert main(["check", str(tmp_path), "--fail-on", "high"]) == 1
    assert "risky" in capsys.readouterr().out


def test_cli_init_scan_list(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--org", "Acme"]) == 0
    (tmp_path / "agent.example.yaml").rename(tmp_path / "agent.yaml")
    assert main(["validate"]) == 0
    assert main(["scan"]) == 0
    capsys.readouterr()
    assert main(["list"]) == 0
    assert "example-support-agent" in capsys.readouterr().out
    assert main(["show", "example-support-agent"]) == 0
    assert main(["report", "-f", "md", "-o", "r.md"]) == 0 and (tmp_path / "r.md").exists()
