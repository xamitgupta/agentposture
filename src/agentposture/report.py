"""Exports: a self-contained HTML dashboard snapshot, JSON, Markdown and CSV.

The HTML snapshot is the live dashboard with the data embedded, so it can be
emailed, attached to an audit ticket, or published as a static page.
"""

from __future__ import annotations

import csv
import io
import json
from importlib import resources
from typing import Any

from .models import TIERS


def _asset(name: str) -> str:
    return resources.files("agentposture.dashboard").joinpath(name).read_text(encoding="utf-8")


def html_snapshot(export: dict[str, Any]) -> str:
    html = _asset("index.html")
    css, js = _asset("styles.css"), _asset("app.js")
    data = json.dumps(export, default=str, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace('<link rel="stylesheet" href="styles.css">', f"<style>\n{css}\n</style>")
    html = html.replace("<!--SNAPSHOT-->",
                        f'<script id="snapshot" type="application/json">{data}</script>')
    html = html.replace('<script src="app.js"></script>', f"<script>\n{js}\n</script>")
    return html


def markdown(export: dict[str, Any]) -> str:
    s, agents = export["summary"], export["agents"]
    t = s["totals"]
    out = [f"# Agent risk posture: {s['organization']}", "",
           f"Generated {s['generated_at']} with {s['policy']['name']}.", "",
           f"**{t['agents']} agents.** " + ", ".join(f"{t['by_tier'][x]} {x}" for x in reversed(TIERS)) + ".",
           f"{t['needs_action']} need action, {t['shadow']} undeclared (shadow), {t['drift']} drifted "
           f"from their declaration, {t['unowned']} without an owner, {t['stale']} stale. "
           f"Record completeness {t['record_completeness']}%.", "",
           "## Needs action", ""]
    if s["attention"]:
        out += ["| Tier | Agent | Team | Most important fix |", "|---|---|---|---|"]
        out += [f"| {a['tier']} | {a['name']} (`{a['id']}`) | {a['team'] or 'unassigned'} | {a['top_finding'] or ''} |"
                for a in s["attention"]]
    else:
        out.append("No agent has an open critical or high finding.")
    out += ["", "## Risk by team", "", "| Team | Agents | Critical | High | Medium | Low | Urgent findings |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    out += [f"| {tm['team']} | {tm['agents']} | {tm['critical']} | {tm['high']} | {tm['medium']} | {tm['low']} | "
            f"{tm['open_urgent']} |" for tm in s["teams"]]
    out += ["", "## Most common findings", "", "| Finding | Severity | Agents |", "|---|---|---:|"]
    out += [f"| {f['title']} ({f['rule_id']}) | {f['severity']} | {f['agents']} |" for f in s["top_findings"]]
    out += ["", "## All agents", "", "| Tier | Score | Agent | Owner | Findings | Flags |",
            "|---|---:|---|---|---:|---|"]
    out += [f"| {a['tier']} | {a['score']:.0f} | {a['name']} (`{a['id']}`) | {a['owner'] or 'nobody'} | "
            f"{a['findings']} | {', '.join(a['flags'])} |" for a in agents]
    out += ["", "## Findings by agent", ""]
    for a in agents:
        d = export["details"][a["id"]]
        fs = d["assessment"]["findings"] if d and d.get("assessment") else []
        if not fs:
            continue
        out += [f"### {a['name']} ({a['tier']})", ""]
        for f in fs:
            out.append(f"- **{f['title']}** ({f['severity']}, {f['rule_id']}): {f['detail']} "
                       f"Fix: {f['remediation']}")
        out.append("")
    return "\n".join(out) + "\n"


def csv_table(export: dict[str, Any]) -> str:
    buf = io.StringIO()
    cols = ["id", "name", "tier", "score", "inherent_score", "target_tier", "team", "owner", "lifecycle",
            "autonomy", "exposure", "data_sensitivity", "findings", "urgent_findings", "top_finding",
            "flags", "platforms", "sources", "last_seen", "assessed_at"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for a in export["agents"]:
        row = dict(a)
        for k in ("flags", "platforms", "sources"):
            row[k] = ";".join(row.get(k) or [])
        w.writerow(row)
    return buf.getvalue()


def render(export: dict[str, Any], fmt: str) -> str:
    if fmt == "html":
        return html_snapshot(export)
    if fmt == "json":
        return json.dumps(export, indent=2, default=str)
    if fmt in ("md", "markdown"):
        return markdown(export)
    if fmt == "csv":
        return csv_table(export)
    raise ValueError(f"unknown format {fmt!r}; use html, json, md or csv")
