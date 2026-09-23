"""Turn a pile of evidence into one record per agent.

Two rules make the result trustworthy:

1. **Join on shared fingerprints.** Evidence that shares any join key (an agent id,
   an identity principal, a repository, a cloud resource) describes the same agent.
2. **Merge conservatively.** For every risk attribute the effective value is the
   riskier of what the owner declared and what we observed. Where observation
   exceeds the declaration, that gap is recorded as *drift*.
"""

from __future__ import annotations

import re
from typing import Any

from .models import DECLARED_AUTHORITATIVE, ORDINALS, Agent, Evidence, ordinal, stable_hash
from .normalize import privilege_level

RISK_ORDINALS = ("data_sensitivity", "exposure", "autonomy", "privilege_level")
UNION_LISTS = ("data_types", "privileges", "frameworks")


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def group_evidence(evidence: list[Evidence]) -> list[list[Evidence]]:
    uf = _UnionFind(len(evidence))
    owner: dict[str, int] = {}
    for i, ev in enumerate(evidence):
        for fp in ev.fingerprints:
            if fp in owner:
                uf.union(owner[fp], i)
            else:
                owner[fp] = i
    groups: dict[int, list[Evidence]] = {}
    for i, ev in enumerate(evidence):
        groups.setdefault(uf.find(i), []).append(ev)
    return list(groups.values())


def _merge_tools(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"read": 0, "write": 1, "irreversible": 2}
    best: dict[str, dict[str, Any]] = {}
    for tools in lists:
        for t in tools or []:
            cur = best.get(t["name"])
            if cur is None:
                best[t["name"]] = dict(t)
            else:
                if rank[t["action"]] > rank[cur["action"]]:
                    cur["action"] = t["action"]
                cur["requires_approval"] = cur.get("requires_approval") or t.get("requires_approval")
                cur["system"] = cur.get("system") or t.get("system")
    return sorted(best.values(), key=lambda t: t["name"])


def _fold(items: list[Evidence]) -> dict[str, Any]:
    """Combine evidence of the same kind: newest scalar wins, lists union, controls OR."""
    out: dict[str, Any] = {}
    for ev in sorted(items, key=lambda e: e.observed_at):
        for k, v in ev.attributes.items():
            if v in (None, "", [], {}):
                continue
            if k == "tools":
                out["tools"] = _merge_tools(out.get("tools", []), v)
            elif k in UNION_LISTS:
                out[k] = sorted(set(out.get(k, [])) | set(v))
            elif k == "controls":
                c = dict(out.get("controls", {}))
                for ck, cv in v.items():
                    if ck == "human_approval":
                        c[ck] = sorted(set(c.get(ck, [])) | set(cv))
                    else:
                        c[ck] = bool(c.get(ck)) or bool(cv)
                out["controls"] = c
            elif k == "irreversible_actions":
                out[k] = bool(out.get(k)) or bool(v)
            elif k == "extra":
                out.setdefault("extra", {}).update(v)
            elif k in ORDINALS and str(v).startswith("unknown:") and k in out:
                continue
            else:
                out[k] = v
    return out


def _riskier(attr: str, a: Any, b: Any) -> Any:
    oa, ob = ordinal(attr, a), ordinal(attr, b)
    if oa is None:
        return b if ob is not None else (a or b)
    if ob is None:
        return a
    return a if oa >= ob else b


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "agent"


def build_agent(group: list[Evidence]) -> Agent:
    declared_ev = [e for e in group if e.kind == "declared"]
    observed_ev = [e for e in group if e.kind == "observed"]
    declared = _fold(declared_ev)
    observed = _fold(observed_ev)

    eff: dict[str, Any] = {}
    for k in set(declared) | set(observed):
        d, o = declared.get(k), observed.get(k)
        if k in DECLARED_AUTHORITATIVE:
            eff[k] = d if d not in (None, "") else o
        elif k in RISK_ORDINALS:
            eff[k] = _riskier(k, d, o)
        elif k == "tools":
            eff[k] = _merge_tools(d or [], o or [])
        elif k in UNION_LISTS:
            eff[k] = sorted(set(d or []) | set(o or []))
        elif k == "controls":
            c = dict(d or {})
            for ck, cv in (o or {}).items():  # an observed control is a fact, not a claim
                c[ck] = sorted(set(c.get(ck, [])) | set(cv)) if ck == "human_approval" else cv
            eff[k] = c
        elif k == "irreversible_actions":
            eff[k] = bool(d) or bool(o)
        elif k == "extra":
            eff[k] = {**(d or {}), **(o or {})}
        else:
            eff[k] = o if o not in (None, "") else d
    if eff.get("tools") or eff.get("privileges"):
        derived = privilege_level(eff.get("privileges", []), eff.get("tools", []))
        eff["privilege_level"] = _riskier("privilege_level", eff.get("privilege_level"), derived)
        eff["irreversible_actions"] = bool(eff.get("irreversible_actions")) or any(
            t["action"] == "irreversible" for t in eff.get("tools", []))

    drift: list[dict[str, Any]] = []
    if declared and observed:
        for k in RISK_ORDINALS:
            od, oo = ordinal(k, declared.get(k)), ordinal(k, observed.get(k))
            if od is not None and oo is not None and oo > od:
                drift.append({"attribute": k, "declared": declared[k], "observed": observed[k]})
        dtools = {t["name"] for t in declared.get("tools", [])}
        extra_tools = sorted(t["name"] for t in observed.get("tools", []) if t["name"] not in dtools)
        if dtools and extra_tools:
            drift.append({"attribute": "tools", "declared": sorted(dtools), "observed": extra_tools})
        dpriv = ordinal("privilege_level", privilege_level(declared.get("privileges", []),
                                                           declared.get("tools", [])))
        opriv = ordinal("privilege_level", privilege_level(observed.get("privileges", []),
                                                           observed.get("tools", [])))
        if observed.get("privileges") and opriv is not None and dpriv is not None and opriv > dpriv \
                and not any(x["attribute"] == "privilege_level" for x in drift):
            drift.append({"attribute": "privileges", "declared": declared.get("privileges", []),
                          "observed": observed["privileges"]})

    ids = sorted(str(e.attributes["id"]) for e in declared_ev if e.attributes.get("id"))
    fingerprints = sorted({fp for e in group for fp in e.fingerprints})
    if ids:
        agent_id = ids[0]
    else:
        agent_id = f"{_slug(str(eff.get('name') or group[0].external_id))}-{stable_hash(fingerprints[0])[:6]}"
    eff.setdefault("name", group[0].external_id)
    eff["platforms"] = sorted({e.attributes.get("platform", e.source_type) for e in group})

    return Agent(
        id=agent_id, attributes=eff, declared=declared, observed=observed,
        sources=sorted({e.source for e in group}), fingerprints=fingerprints, drift=drift,
        first_seen=min(e.observed_at for e in group), last_seen=max(e.observed_at for e in group),
    )


def merge_evidence(evidence: list[Evidence]) -> list[Agent]:
    agents = [build_agent(g) for g in group_evidence(evidence)]
    # guarantee unique ids even if two unrelated groups share a declared id
    seen: dict[str, int] = {}
    for a in sorted(agents, key=lambda a: a.first_seen):
        if a.id in seen:
            seen[a.id] += 1
            a.id = f"{a.id}-{seen[a.id]}"
        else:
            seen[a.id] = 1
    return sorted(agents, key=lambda a: a.id)
