"""The orchestration layer: scan sources, keep the registry current, reassess, summarize.

The CLI, the web server and the scheduler all call into :class:`PostureService`;
none of them contain business logic of their own.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import __repo__, __version__
from .config import Config
from .connectors import ConnectorError, get_connector
from .engine import Policy, assess, load_policy
from .merge import merge_evidence
from .models import TIERS, parse_ts, utcnow
from .normalize import link_fingerprints
from .store import Store

log = logging.getLogger("agentposture")

API_SOURCE = "api"


@dataclass
class ScanReport:
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    agents: int = 0
    reassessed: int = 0
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return all(s["status"] == "ok" for s in self.sources.values())

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "sources": self.sources, "agents": self.agents,
                "reassessed": self.reassessed, "duration_s": round(self.duration_s, 2)}


class PostureService:
    def __init__(self, config: Config, store: Store | None = None, policy: Policy | None = None):
        self.config = config
        self.store = store or Store(config.resolve_path(config.storage_path))
        self.policy = policy or load_policy(config.policy, config.base_dir)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ scan
    def scan(self, source: str | None = None, trigger: str = "manual") -> ScanReport:
        started = time.monotonic()
        report = ScanReport()
        targets = [self.config.source(source)] if source else [s for s in self.config.sources if s.enabled]
        with self._lock:
            for src in targets:
                run_id = self.store.start_run(src.name, trigger)
                try:
                    connector = get_connector(src.type)(src, base_dir=self.config.base_dir)
                    items = list(connector.discover())
                    self.store.upsert_evidence(items)
                    self.store.finish_run(run_id, "ok", len(items))
                    report.sources[src.name] = {"status": "ok", "found": len(items)}
                    log.info("scanned %s: %d agent records", src.name, len(items))
                except ConnectorError as exc:
                    self.store.finish_run(run_id, "error", 0, str(exc))
                    report.sources[src.name] = {"status": "error", "error": str(exc)}
                    log.warning("scan of %s failed: %s", src.name, exc)
                except Exception as exc:  # a connector bug must not stop the other sources
                    log.exception("scan of %s crashed", src.name)
                    self.store.finish_run(run_id, "error", 0, f"{type(exc).__name__}: {exc}")
                    report.sources[src.name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            report.agents, report.reassessed = self.reconcile()
        report.duration_s = time.monotonic() - started
        return report

    def register(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Declare an agent through the API (for CI/CD pipelines and internal portals)."""
        import yaml

        from .connectors.manifest import parse_manifest_docs
        docs = parse_manifest_docs(yaml.safe_dump(manifest), "request body")
        from .config import SourceConfig
        from .connectors.base import Connector

        class _Api(Connector):
            type_name = API_SOURCE
            evidence_kind = "declared"

        conn = _Api(SourceConfig(name=API_SOURCE, type=API_SOURCE))
        items = []
        for doc in docs:
            attrs = {k: v for k, v in doc.items() if k != "links"}
            items.append(conn.evidence(str(doc.get("id") or doc["name"]), attrs,
                                       link_fingerprints(doc.get("links"))))
        with self._lock:
            self.store.upsert_evidence(items)
            self.reconcile()
        ids = {e.external_id for e in items}
        return {"registered": sorted(ids)}

    def unregister(self, agent_id: str) -> bool:
        with self._lock:
            removed = self.store.delete_evidence(API_SOURCE, agent_id)
            if removed:
                self.reconcile()
            return bool(removed)

    # ------------------------------------------------------------- reconcile
    def reconcile(self, force: bool = False) -> tuple[int, int]:
        """Rebuild the registry from evidence and reassess whatever is due."""
        with self._lock:
            retention = max(self.config.stale_after * 3, 30 * 86400)
            self.store.purge_evidence(retention)
            configured = {s.name for s in self.config.sources} | {API_SOURCE}
            evidence = [e for e in self.store.all_evidence() if e.source in configured]
            agents = merge_evidence(evidence)
            now = datetime.now(timezone.utc)
            previous_first = self.store.agent_first_seen()
            for a in agents:
                seen = parse_ts(a.last_seen)
                if seen and (now - seen).total_seconds() > self.config.stale_after:
                    a.status = "stale"
                if a.id in previous_first:
                    a.first_seen = min(a.first_seen, previous_first[a.id])
            self.store.replace_agents(agents)

            latest = self.store.latest_assessments()
            policy_changed = self.store.get_meta("policy_hash") != self.policy.hash
            reassessed = 0
            for a in agents:
                prev = latest.get(a.id)
                due = force or prev is None or policy_changed
                if not due and self.config.on_change and prev.get("_attr_hash") != a.attr_hash:
                    due = True
                if not due:
                    age = now - (parse_ts(prev.get("assessed_at")) or now)
                    due = age.total_seconds() >= self.config.max_age_by_tier.get(prev["tier"], 86400)
                if due:
                    self.store.save_assessment(assess(a, self.policy, now).to_dict(), a.attr_hash)
                    reassessed += 1
            self.store.set_meta("policy_hash", self.policy.hash)
            self.store.set_meta("last_reconcile", utcnow())
            self.store.prune_assessments()
            self.store.add_snapshot(self._snapshot())
            return len(agents), reassessed

    # --------------------------------------------------------------- queries
    def agents_view(self, tier: str | None = None, team: str | None = None,
                    q: str | None = None, flag: str | None = None) -> list[dict[str, Any]]:
        latest = self.store.latest_assessments()
        out = []
        for a in self.store.agents():
            asmt = latest.get(a["id"])
            if not asmt:
                continue
            row = _row(a, asmt)
            if tier and row["tier"] != tier:
                continue
            if team and (row["team"] or "unassigned") != team:
                continue
            if flag and flag not in row["flags"]:
                continue
            if q and q.lower() not in f"{row['id']} {row['name']} {row['owner']} {row['team']}".lower():
                continue
            out.append(row)
        out.sort(key=lambda r: (-TIERS.index(r["tier"]), -r["score"], r["name"].lower()))
        return out

    def agent_detail(self, agent_id: str) -> dict[str, Any] | None:
        a = self.store.agent(agent_id)
        if not a:
            return None
        asmt = self.store.latest_assessments().get(agent_id)
        if asmt:
            asmt.pop("_attr_hash", None)
        return {"agent": a, "assessment": asmt, "history": self.store.assessment_history(agent_id),
                "row": _row(a, asmt) if asmt else None}

    def sources_view(self) -> list[dict[str, Any]]:
        from .scheduler import CronSchedule
        runs = self.store.last_runs()
        now = datetime.now(timezone.utc)
        out = []
        for s in self.config.sources:
            r = runs.get(s.name, {})
            out.append({
                "name": s.name, "type": s.type, "enabled": s.enabled,
                "schedule": s.schedule, "trigger": s.trigger or ("schedule" if s.schedule else "manual"),
                "next_run": CronSchedule(s.schedule).next_after(now).isoformat() if s.schedule else None,
                "last_status": r.get("status"), "last_run": r.get("finished_at") or r.get("started_at"),
                "last_success": r.get("last_success"), "found": r.get("found"), "error": r.get("error"),
            })
        return out

    def summary(self) -> dict[str, Any]:
        rows = self.agents_view()
        latest = self.store.latest_assessments()
        by_tier = Counter(r["tier"] for r in rows)
        teams: dict[str, dict[str, Any]] = defaultdict(lambda: {"agents": 0, **{t: 0 for t in TIERS},
                                                                 "open_urgent": 0, "score_sum": 0.0})
        platforms: Counter[str] = Counter()
        rules: dict[str, dict[str, Any]] = {}
        controls: dict[str, dict[str, int]] = defaultdict(lambda: {"applies": 0, "in_place": 0})
        for r in rows:
            t = teams[r["team"] or "unassigned"]
            t["agents"] += 1
            t[r["tier"]] += 1
            t["open_urgent"] += r["urgent_findings"]
            t["score_sum"] += r["score"]
            for p in r["platforms"]:
                platforms[p] += 1
            asmt = latest[r["id"]]
            for f in asmt.get("findings", []):
                e = rules.setdefault(f["rule_id"], {"rule_id": f["rule_id"], "title": f["title"],
                                                    "severity": f["severity"], "agents": 0})
                e["agents"] += 1
            for c, v in (asmt.get("controls") or {}).items():
                controls[c]["applies"] += int(v["applies"])
                controls[c]["in_place"] += int(v["in_place"])
        team_rows = []
        for name, t in teams.items():
            avg = t.pop("score_sum") / t["agents"] if t["agents"] else 0
            team_rows.append({"team": name, **t, "avg_score": round(avg, 1)})
        team_rows.sort(key=lambda t: (-t["critical"], -t["high"], -t["avg_score"]))
        sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        total = len(rows)
        complete = sum(1 for r in rows if "incomplete" not in r["flags"] and "shadow" not in r["flags"])
        return {
            "organization": self.config.organization,
            "generated_at": utcnow(),
            "version": __version__,
            "repo_url": __repo__,
            "policy": {"name": self.policy.name, "hash": self.policy.hash},
            "last_reconcile": self.store.get_meta("last_reconcile"),
            "refresh_seconds": self.config.dashboard_refresh,
            "totals": {
                "agents": total,
                "by_tier": {t: by_tier.get(t, 0) for t in TIERS},
                "declared": sum(1 for r in rows if "shadow" not in r["flags"]),
                "shadow": sum(1 for r in rows if "shadow" in r["flags"]),
                "unowned": sum(1 for r in rows if "unowned" in r["flags"]),
                "drift": sum(1 for r in rows if "drift" in r["flags"]),
                "stale": sum(1 for r in rows if "stale" in r["flags"]),
                "needs_action": sum(1 for r in rows if r["urgent_findings"]),
                "record_completeness": round(100 * complete / total) if total else 100,
            },
            "attention": [r for r in rows if r["urgent_findings"]][:10],
            "teams": team_rows,
            "platforms": [{"platform": p, "agents": n} for p, n in platforms.most_common()],
            "top_findings": sorted(rules.values(), key=lambda e: (sev[e["severity"]], -e["agents"])),
            "controls": [{"control": c, **v} for c, v in sorted(controls.items()) if v["applies"]],
            "sources": self.sources_view(),
            "trend": self.store.snapshots(self.config.history_days),
        }

    def _snapshot(self) -> dict[str, Any]:
        rows = self.agents_view()
        c = Counter(r["tier"] for r in rows)
        return {"total": len(rows), "by_tier": {t: c.get(t, 0) for t in TIERS},
                "shadow": sum(1 for r in rows if "shadow" in r["flags"]),
                "needs_action": sum(1 for r in rows if r["urgent_findings"])}

    def export(self) -> dict[str, Any]:
        """Everything the dashboard needs, in one document (used for static reports)."""
        agents = self.agents_view()
        details = {r["id"]: self.agent_detail(r["id"]) for r in agents}
        return {"summary": self.summary(), "agents": agents, "details": details}


def _row(agent: dict[str, Any], asmt: dict[str, Any]) -> dict[str, Any]:
    attrs = agent["attributes"]
    findings = asmt.get("findings", [])
    flags = []
    if not agent.get("is_declared"):
        flags.append("shadow")
    if not attrs.get("owner"):
        flags.append("unowned")
    if agent.get("drift"):
        flags.append("drift")
    if agent.get("status") == "stale":
        flags.append("stale")
    if any(f["rule_id"] == "AP-014" for f in findings):
        flags.append("incomplete")
    return {
        "id": agent["id"], "name": attrs.get("name") or agent["id"],
        "owner": attrs.get("owner"), "team": attrs.get("team"),
        "lifecycle": attrs.get("lifecycle"), "autonomy": attrs.get("autonomy"),
        "exposure": attrs.get("exposure"), "data_sensitivity": attrs.get("data_sensitivity"),
        "platforms": attrs.get("platforms", []), "sources": agent.get("sources", []),
        "tier": asmt["tier"], "score": asmt["score"], "inherent_score": asmt.get("inherent_score"),
        "target_tier": asmt.get("target_tier"),
        "findings": len(findings),
        "urgent_findings": sum(1 for f in findings if f["severity"] in ("critical", "high")),
        "top_finding": findings[0]["title"] if findings else None,
        "flags": flags, "status": agent.get("status"),
        "last_seen": agent.get("last_seen"), "assessed_at": asmt.get("assessed_at"),
    }
