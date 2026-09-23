"""The ``agentposture`` command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import STARTER_CONFIG, Config, ConfigError, SourceConfig, load_config
from .connectors import ConnectorError, available_connectors
from .engine import PolicyError, assess, load_policy
from .models import TIERS

EXAMPLE_MANIFEST = """\
# agent.yaml: tells AgentPosture what this agent is and how it is controlled.
# Reference: docs/manifest.md
apiVersion: agentposture/v1
kind: Agent
id: example-support-agent
name: Example Support Agent
description: Answers customer questions and drafts refunds for a human to approve.
owner: you@example.com
team: support
lifecycle: development          # development | staging | production | deprecated
business_impact: medium         # low | medium | high | critical
autonomy: act_with_approval     # read_only | recommend | act_with_approval | autonomous
exposure: customer              # internal | partner | customer | public
data:
  sensitivity: confidential     # public | internal | confidential | restricted
  types: [pii]
tools:
  - name: search_help_center
    action: read
  - name: issue_refund
    action: irreversible
    requires_approval: true
controls:
  kill_switch: true
  audit_logging: true
  input_guardrails: true
  output_guardrails: false
  rate_limit: true
"""

_COLORS = {"critical": "\033[31m", "high": "\033[33m", "medium": "\033[36m", "low": "\033[32m"}


def _c(tier: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_COLORS.get(tier, '')}{text}\033[0m"


def _service(args: argparse.Namespace):
    from .service import PostureService
    return PostureService(load_config(args.config))


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No agents found. Run `agentposture scan` first, or `agentposture demo` to explore.")
        return
    def cut(text: str, n: int) -> str:
        return text if len(text) <= n else text[: n - 2] + ".."
    print(f"{'TIER':9} {'SCORE':>5}  {'ID':30} {'NAME':28} {'TEAM':18} {'FINDINGS':>8}  FLAGS")
    for r in rows:
        print(f"{_c(r['tier'], r['tier'].ljust(9))} {r['score']:5.0f}  {cut(r['id'], 30):30} "
              f"{cut(r['name'], 28):28} {cut(r['team'] or 'unassigned', 18):18} {r['findings']:8}  "
              f"{','.join(r['flags'])}")


# ---------------------------------------------------------------- commands
def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.config or "agentposture.yaml")
    if target.exists() and not args.force:
        print(f"{target} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    target.write_text(STARTER_CONFIG.format(organization=args.org))
    print(f"Wrote {target}")
    manifest = target.parent / "agent.example.yaml"
    if not manifest.exists():
        manifest.write_text(EXAMPLE_MANIFEST)
        print(f"Wrote {manifest} (rename it to agent.yaml next to real agent code)")
    print("\nNext: `agentposture scan` then `agentposture serve`.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    policy = load_policy(cfg.policy, cfg.base_dir)
    print(f"Config OK: {len(cfg.sources)} source(s) for {cfg.organization}")
    print(f"Policy OK: {policy.name} ({len(policy.findings)} findings, {len(policy.overrides)} overrides)")
    from .connectors import get_connector
    problems = 0
    for s in cfg.sources:
        if s.type in ("manifest", "csv", "code_scan", "http_json") and s.enabled:
            try:
                n = sum(1 for _ in get_connector(s.type)(s, base_dir=cfg.base_dir).discover())
                print(f"  {s.name}: readable, {n} record(s)")
            except (ConnectorError, ConfigError) as exc:
                problems += 1
                print(f"  {s.name}: {exc}")
        else:
            print(f"  {s.name}: {s.type} (checked at scan time)")
    return 1 if problems else 0


def cmd_scan(args: argparse.Namespace) -> int:
    svc = _service(args)
    report = svc.scan(args.source, trigger="cli")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for name, s in report.sources.items():
            status = f"{s['found']} record(s)" if s["status"] == "ok" else f"FAILED: {s['error']}"
            print(f"  {name:24} {status}")
        rows = svc.agents_view()
        by = {t: sum(1 for r in rows if r["tier"] == t) for t in TIERS}
        print(f"\n{report.agents} agents ({', '.join(f'{by[t]} {t}' for t in reversed(TIERS))}); "
              f"{report.reassessed} reassessed in {report.duration_s:.1f}s")
    return 0 if report.ok else 2


def cmd_list(args: argparse.Namespace) -> int:
    rows = _service(args).agents_view(tier=args.tier, team=args.team, flag=args.flag)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        _print_table(rows)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    d = _service(args).agent_detail(args.agent_id)
    if not d:
        print(f"No agent with id {args.agent_id}. `agentposture list` shows ids.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(d, indent=2, default=str))
        return 0
    a, s = d["agent"], d["assessment"]
    at = a["attributes"]
    print(f"{at.get('name', a['id'])}  ({a['id']})")
    print(f"  tier {_c(s['tier'], s['tier'])}, score {s['score']} "
          f"({s['inherent_score']} before controls); all findings fixed -> {s['target_tier']}")
    print(f"  owner {at.get('owner') or 'nobody'}, team {at.get('team') or 'unassigned'}, "
          f"sources {', '.join(a['sources'])}")
    for k, v in s["dimensions"].items():
        print(f"  {k:17} {'#' * v['level']:3} {v['value']}")
    if s["overrides"]:
        print(f"  overrides: {', '.join(s['overrides'])}")
    for f in s["findings"]:
        print(f"\n  [{f['severity']}] {f['rule_id']} {f['title']}\n    {f['detail']}\n    Fix: {f['remediation']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve
    serve(_service(args), host=args.host, port=args.port, scan_on_start=not args.no_scan)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .report import render
    svc = _service(args)
    if args.scan:
        svc.scan(trigger="report")
    text = render(svc.export(), args.format)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """CI gate: score manifests without any server or database."""
    from .connectors.manifest import ManifestConnector
    from .merge import merge_evidence
    policy = load_policy(args.policy, Path.cwd())
    src = SourceConfig(name="check", type="manifest", options={"paths": args.paths})
    agents = merge_evidence(list(ManifestConnector(src, base_dir=Path.cwd()).discover()))
    if not agents:
        print("No agent manifests found.", file=sys.stderr)
        return 1
    limit = TIERS.index(args.fail_on)
    failed = 0
    results = []
    for agent in agents:
        r = assess(agent, policy)
        results.append(r.to_dict() | {"name": agent.name})
        bad = TIERS.index(r.tier) >= limit
        failed += bad
        if not args.json:
            print(f"{'FAIL' if bad else 'ok  '} {_c(r.tier, r.tier.ljust(8))} {r.score:5.1f}  {agent.name} ({agent.id})")
            for f in r.findings:
                print(f"       - [{f.severity}] {f.title}: {f.remediation}")
            if bad and not r.findings:
                print("       - No open findings: the tier comes from what this agent is allowed to do. "
                      "Reduce its scope, or record a risk acceptance and raise --fail-on for this path.")
    if args.json:
        print(json.dumps({"fail_on": args.fail_on, "failed": failed, "results": results}, indent=2))
    elif failed:
        print(f"\n{failed} agent(s) at {args.fail_on} or above. Fix the findings or raise --fail-on.")
    return 1 if failed else 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .service import PostureService
    from .store import Store
    workdir = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix="agentposture-demo-"))
    workdir.mkdir(parents=True, exist_ok=True)
    cfg = Config(organization="Acme Corp (demo)", storage_path=str(workdir / "demo.db"),
                 sources=[SourceConfig(name="demo-fleet", type="demo", schedule="0 */6 * * *")],
                 base_dir=workdir)
    svc = PostureService(cfg, Store(cfg.storage_path))
    svc.scan(trigger="demo")
    _seed_trend(svc)
    if args.out:
        from .report import render
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        export = svc.export()
        (out / "index.html").write_text(render(export, "html"), encoding="utf-8")
        (out / "report.md").write_text(render(export, "md"), encoding="utf-8")
        (out / "agents.csv").write_text(render(export, "csv"), encoding="utf-8")
        print(f"Wrote sample dashboard and reports to {out}/")
        return 0
    from .server import serve
    print("Demo data is synthetic. Press Ctrl+C to stop.")
    serve(svc, host=args.host, port=args.port, scan_on_start=False)
    return 0


def _seed_trend(svc: Any) -> None:
    """Give the demo a believable 90-day history: an inventory that grew and got safer."""
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    current = svc._snapshot()
    total = max(current["total"], 1)
    share = {t: current["by_tier"][t] / total for t in TIERS}
    for days_ago in range(90, 0, -3):
        f = days_ago / 90
        n = max(8, round(total * (1 - 0.25 * f)))
        crit = min(n, current["by_tier"]["critical"] + round(3 * f))
        high = min(n - crit, current["by_tier"]["high"] + round(2 * f))
        medium = min(n - crit - high, round(n * share["medium"]))
        snap = {"total": n, "by_tier": {"critical": crit, "high": high, "medium": medium,
                                         "low": n - crit - high - medium},
                "shadow": current["shadow"] + round(3 * f),
                "needs_action": current["needs_action"] + round(6 * f)}
        svc.store.add_snapshot(snap, (now - timedelta(days=days_ago)).isoformat())


def cmd_connectors(args: argparse.Namespace) -> int:
    for name, cls in sorted(available_connectors().items()):
        print(f"{name:12} {cls.evidence_kind:9} {cls.description}")
        if args.verbose:
            for opt, desc in cls.options.items():
                print(f"{'':24}{opt}: {desc}")
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    from importlib import resources
    text = resources.files("agentposture.policies").joinpath("default.yaml").read_text()
    if args.out:
        Path(args.out).write_text(text)
        print(f"Wrote {args.out}. Point `policy:` in agentposture.yaml at it.")
    else:
        sys.stdout.write(text)
    return 0


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentposture",
                                description="Find every AI agent in your organization and know how risky each one is.")
    p.add_argument("--version", action="version", version=f"agentposture {__version__}")
    p.add_argument("-c", "--config", help="path to agentposture.yaml (default: ./agentposture.yaml)")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    s = sub.add_parser("init", help="create a starter agentposture.yaml")
    s.add_argument("--org", default="My organization", help="organization name shown on the dashboard")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("validate", help="check the config, policy and local sources")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("scan", help="scan sources now and reassess")
    s.add_argument("--source", help="scan only this source")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("list", help="list agents, riskiest first")
    s.add_argument("--tier", choices=TIERS)
    s.add_argument("--team")
    s.add_argument("--flag", choices=["shadow", "drift", "unowned", "stale", "incomplete"])
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="explain one agent's tier and findings")
    s.add_argument("agent_id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("serve", help="run the dashboard, API and scheduler")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.add_argument("--no-scan", action="store_true", help="skip the scan at startup")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("report", help="export posture as html, json, md or csv")
    s.add_argument("--format", "-f", choices=["html", "json", "md", "csv"], default="html")
    s.add_argument("--out", "-o", help="file to write (default: stdout)")
    s.add_argument("--scan", action="store_true", help="scan before exporting")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("check", help="CI gate: score agent manifests and fail above a tier")
    s.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    s.add_argument("--fail-on", choices=TIERS, default="critical", help="fail at this tier or above")
    s.add_argument("--policy", default="default", help="policy file (default: built-in)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("demo", help="explore a realistic sample organization")
    s.add_argument("--port", type=int, default=8484)
    s.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 inside a container")
    s.add_argument("--dir", help="keep the demo database here instead of a temp directory")
    s.add_argument("--out", help="write a static sample dashboard and reports to this directory instead")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("connectors", help="list available source types")
    s.set_defaults(func=cmd_connectors)

    s = sub.add_parser("policy", help="print the default policy (to customize it)")
    s.add_argument("--out", "-o", help="write to a file instead of stdout")
    s.set_defaults(func=cmd_policy)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not args.verbose:
        logging.getLogger("agentposture").setLevel(logging.WARNING)
    try:
        return int(args.func(args) or 0)
    except (ConfigError, PolicyError, ConnectorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
