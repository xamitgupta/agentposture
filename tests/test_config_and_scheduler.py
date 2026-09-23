from datetime import datetime, timezone

import pytest

from agentposture.config import STARTER_CONFIG, ConfigError, load_config, parse_config, parse_duration, resolve_secret
from agentposture.scheduler import CronSchedule, Scheduler


def test_starter_config_parses(tmp_path):
    p = tmp_path / "agentposture.yaml"
    p.write_text(STARTER_CONFIG.format(organization="Acme"))
    cfg = load_config(p)
    assert cfg.organization == "Acme"
    assert [s.type for s in cfg.sources] == ["manifest", "code_scan"]
    assert cfg.max_age_by_tier["critical"] == 86400


@pytest.mark.parametrize("raw,msg", [
    ({"sources": [{"type": "nope"}]}, "unknown source type"),
    ({"sources": [{"type": "manifest"}, {"type": "manifest"}]}, "duplicate source name"),
    ({"sources": [{"type": "manifest", "schedule": "every hour"}]}, "5 fields"),
    ({"reassessment": {"max_age_by_tier": {"severe": "1d"}}}, "unknown tier"),
    ({"reassessment": {"stale_after": "soon"}}, "not a duration"),
    ({"version": 2}, "Unsupported config version"),
    ({"server": {"protect_reads": True}}, "protect_reads needs"),
])
def test_config_errors_name_the_problem(raw, msg):
    with pytest.raises(ConfigError, match=msg):
        parse_config(raw)


def test_secrets_come_from_env_and_files(tmp_path, monkeypatch):
    monkeypatch.setenv("AP_TEST_SECRET", "s3cret")
    assert resolve_secret("env:AP_TEST_SECRET") == "s3cret"
    f = tmp_path / "tok"
    f.write_text("from-file\n")
    assert resolve_secret(f"file:{f}") == "from-file"
    with pytest.raises(ConfigError, match="not set"):
        resolve_secret("env:AP_DOES_NOT_EXIST")


def test_durations():
    assert parse_duration("15m") == 900 and parse_duration("2w") == 1209600 and parse_duration(30) == 30


def test_cron_matching_and_next():
    c = CronSchedule("*/15 9-17 * * 1-5")
    monday_930 = datetime(2026, 9, 21, 9, 30, tzinfo=timezone.utc)
    assert c.matches(monday_930)
    assert not c.matches(datetime(2026, 9, 20, 9, 30, tzinfo=timezone.utc))  # Sunday
    assert c.next_after(monday_930) == datetime(2026, 9, 21, 9, 45, tzinfo=timezone.utc)
    assert CronSchedule("@daily").next_after(monday_930).hour == 0
    assert CronSchedule("0 0 * * 7").matches(datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        CronSchedule("61 * * * *")


def test_scheduler_runs_due_jobs_and_survives_failures():
    ran = []

    def job(name):
        ran.append(name)
        if name == "bad":
            raise RuntimeError("boom")

    s = Scheduler({"good": "* * * * *", "bad": "* * * * *"}, job)
    later = datetime.now(timezone.utc).replace(year=datetime.now().year + 1)
    assert sorted(s.run_pending(later)) == ["bad", "good"]
    assert all(t > later for t in s.next_run.values())
