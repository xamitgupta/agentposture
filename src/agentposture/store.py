"""Persistence in a single SQLite file. No database server to run."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import Agent, Evidence, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    source TEXT NOT NULL, external_id TEXT NOT NULL, source_type TEXT NOT NULL,
    kind TEXT NOT NULL, attributes TEXT NOT NULL, fingerprints TEXT NOT NULL,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    PRIMARY KEY (source, external_id));
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY, data TEXT NOT NULL, attr_hash TEXT NOT NULL,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, assessed_at TEXT NOT NULL,
    score REAL NOT NULL, tier TEXT NOT NULL, attr_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
    data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_assess_agent ON assessments(agent_id, id);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, trigger TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, found INTEGER DEFAULT 0,
    error TEXT);
CREATE INDEX IF NOT EXISTS ix_runs_source ON scan_runs(source, id);
CREATE TABLE IF NOT EXISTS snapshots (taken_at TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
SCHEMA_VERSION = "1"


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL") if self.path != ":memory:" else None
            self._conn.executescript(SCHEMA)
            self.set_meta("schema_version", SCHEMA_VERSION)

    def close(self) -> None:
        self._conn.close()

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def _tx(self, statements: list[tuple[str, tuple]]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                for sql, args in statements:
                    self._conn.execute(sql, args)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    # -- meta ---------------------------------------------------------------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        rows = self._q("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def set_meta(self, key: str, value: str) -> None:
        self._q("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))

    # -- evidence -----------------------------------------------------------
    def upsert_evidence(self, items: list[Evidence]) -> None:
        now = utcnow()
        self._tx([(
            """INSERT INTO evidence(source,external_id,source_type,kind,attributes,fingerprints,first_seen,last_seen)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(source,external_id) DO UPDATE SET source_type=excluded.source_type,
               kind=excluded.kind, attributes=excluded.attributes, fingerprints=excluded.fingerprints,
               last_seen=excluded.last_seen""",
            (e.source, e.external_id, e.source_type, e.kind, json.dumps(e.attributes, sort_keys=True),
             json.dumps(e.fingerprints), now, now)) for e in items])

    def all_evidence(self) -> list[Evidence]:
        out = []
        for r in self._q("SELECT * FROM evidence ORDER BY source, external_id"):
            ev = Evidence(source=r["source"], source_type=r["source_type"], external_id=r["external_id"],
                          kind=r["kind"], attributes=json.loads(r["attributes"]),
                          fingerprints=json.loads(r["fingerprints"]), observed_at=r["last_seen"])
            out.append(ev)
        return out

    def delete_evidence(self, source: str, external_id: str | None = None) -> int:
        with self._lock:
            if external_id is None:
                cur = self._conn.execute("DELETE FROM evidence WHERE source=?", (source,))
            else:
                cur = self._conn.execute("DELETE FROM evidence WHERE source=? AND external_id=?",
                                         (source, external_id))
            return cur.rowcount

    def purge_evidence(self, older_than_seconds: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
        with self._lock:
            return self._conn.execute("DELETE FROM evidence WHERE last_seen < ?", (cutoff,)).rowcount

    def evidence_sources(self) -> list[str]:
        return [r["source"] for r in self._q("SELECT DISTINCT source FROM evidence")]

    # -- agents -------------------------------------------------------------
    def replace_agents(self, agents: list[Agent]) -> None:
        stmts: list[tuple[str, tuple]] = [("DELETE FROM agents", ())]
        for a in agents:
            stmts.append(("INSERT INTO agents(id,data,attr_hash,first_seen,last_seen,status) VALUES(?,?,?,?,?,?)",
                          (a.id, json.dumps(a.to_dict(), sort_keys=True), a.attr_hash, a.first_seen,
                           a.last_seen, a.status)))
        self._tx(stmts)

    def agents(self) -> list[dict[str, Any]]:
        return [json.loads(r["data"]) for r in self._q("SELECT data FROM agents ORDER BY id")]

    def agent(self, agent_id: str) -> dict[str, Any] | None:
        rows = self._q("SELECT data FROM agents WHERE id=?", (agent_id,))
        return json.loads(rows[0]["data"]) if rows else None

    def agent_first_seen(self) -> dict[str, str]:
        return {r["id"]: r["first_seen"] for r in self._q("SELECT id, first_seen FROM agents")}

    # -- assessments --------------------------------------------------------
    def save_assessment(self, data: dict[str, Any], attr_hash: str) -> None:
        self._q("""INSERT INTO assessments(agent_id,assessed_at,score,tier,attr_hash,policy_hash,data)
                   VALUES(?,?,?,?,?,?,?)""",
                (data["agent_id"], data["assessed_at"], data["score"], data["tier"], attr_hash,
                 data["policy_hash"], json.dumps(data, sort_keys=True)))

    def latest_assessments(self) -> dict[str, dict[str, Any]]:
        rows = self._q("""SELECT a.agent_id, a.attr_hash, a.data FROM assessments a
                          JOIN (SELECT agent_id, MAX(id) mid FROM assessments GROUP BY agent_id) m
                          ON a.id = m.mid""")
        out = {}
        for r in rows:
            d = json.loads(r["data"])
            d["_attr_hash"] = r["attr_hash"]
            out[r["agent_id"]] = d
        return out

    def assessment_history(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._q("""SELECT assessed_at, score, tier, data FROM assessments WHERE agent_id=?
                          ORDER BY id DESC LIMIT ?""", (agent_id, limit))
        out = []
        for r in rows:
            d = json.loads(r["data"])
            out.append({"assessed_at": r["assessed_at"], "score": r["score"], "tier": r["tier"],
                        "findings": [f["rule_id"] for f in d.get("findings", [])]})
        return out

    def prune_assessments(self, keep_per_agent: int = 200) -> None:
        self._q("""DELETE FROM assessments WHERE id IN (
                     SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY agent_id ORDER BY id DESC) rn
                                     FROM assessments) WHERE rn > ?)""", (keep_per_agent,))

    # -- scan runs ----------------------------------------------------------
    def start_run(self, source: str, trigger: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO scan_runs(source,trigger,started_at,status) VALUES(?,?,?,'running')",
                (source, trigger, utcnow()))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, found: int = 0, error: str | None = None) -> None:
        self._q("UPDATE scan_runs SET finished_at=?, status=?, found=?, error=? WHERE id=?",
                (utcnow(), status, found, error, run_id))

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in self._q("SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (limit,))]

    def last_runs(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in self._q("SELECT * FROM scan_runs ORDER BY id"):
            d = dict(r)
            prev = out.get(d["source"], {})
            d["last_success"] = d["finished_at"] if d["status"] == "ok" else prev.get("last_success")
            out[d["source"]] = d
        return out

    # -- snapshots ----------------------------------------------------------
    def add_snapshot(self, data: dict[str, Any], taken_at: str | None = None) -> None:
        self._q("INSERT OR REPLACE INTO snapshots(taken_at,data) VALUES(?,?)",
                (taken_at or utcnow(), json.dumps(data, sort_keys=True)))

    def snapshots(self, days: int = 180) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self._q("SELECT taken_at, data FROM snapshots WHERE taken_at >= ? ORDER BY taken_at", (cutoff,))
        by_day: dict[str, dict[str, Any]] = {}
        for r in rows:  # keep the last snapshot of each day
            d = json.loads(r["data"])
            d["date"] = r["taken_at"][:10]
            by_day[d["date"]] = d
        return list(by_day.values())
