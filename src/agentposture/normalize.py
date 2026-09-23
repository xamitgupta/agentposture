"""Map whatever a source reports onto AgentPosture's normalized attribute vocabulary.

Every connector funnels its output through :func:`normalize_attributes`, so the
risk engine only ever sees one consistent shape.
"""

from __future__ import annotations

import re
from typing import Any

from .models import AUTONOMY, BUSINESS_IMPACT, DATA_SENSITIVITY, EXPOSURE, LIFECYCLE, PRIVILEGE_LEVEL

_ALIASES: dict[str, dict[str, str]] = {
    "autonomy": {
        "readonly": "read_only", "read-only": "read_only", "read": "read_only", "none": "read_only",
        "advisory": "recommend", "suggest": "recommend", "copilot": "recommend",
        "human_in_the_loop": "act_with_approval", "hitl": "act_with_approval",
        "supervised": "act_with_approval", "approval": "act_with_approval",
        "full": "autonomous", "fully_autonomous": "autonomous", "auto": "autonomous",
        "unsupervised": "autonomous",
    },
    "exposure": {
        "internal_only": "internal", "employee": "internal", "employees": "internal",
        "b2b": "partner", "vendor": "partner", "external": "customer", "customers": "customer",
        "internet": "public", "anonymous": "public", "open": "public",
    },
    "data_sensitivity": {
        "low": "internal", "general": "internal", "sensitive": "confidential",
        "secret": "restricted", "highly_confidential": "restricted", "high": "restricted",
    },
    "business_impact": {"minor": "low", "moderate": "medium", "major": "high", "severe": "critical"},
    "lifecycle": {"dev": "development", "prod": "production", "live": "production",
                  "test": "staging", "retired": "deprecated", "sunset": "deprecated"},
}
_SCALES = {"autonomy": AUTONOMY, "exposure": EXPOSURE, "data_sensitivity": DATA_SENSITIVITY,
           "business_impact": BUSINESS_IMPACT, "lifecycle": LIFECYCLE,
           "privilege_level": PRIVILEGE_LEVEL}

_IRREVERSIBLE = re.compile(
    r"(delete|drop|destroy|terminate|purge|wipe|refund|transfer|payout|pay_|payment|wire|"
    r"send_money|charge|revoke|deprovision|deploy|publish|execute|exec|shell|run_command|"
    r"grant|disable_user|rotate)", re.I)
_WRITE = re.compile(r"(create|update|write|post|send|modify|insert|put|patch|edit|upload|"
                    r"comment|assign|approve|book|schedule|email|message|notify)", re.I)
_ADMIN_PRIV = re.compile(r"(^\*$|:\*$|\*:\*|admin|owner|fullaccess|full_access|"
                         r"\.readwrite\.all|directory\.|root|superuser)", re.I)
_WRITE_PRIV = re.compile(r"(write|put|post|delete|create|update|modify|readwrite|manage)", re.I)


def _enum(key: str, value: Any) -> Any:
    if value is None:
        return None
    v = str(value).strip().lower().replace(" ", "_")
    v = _ALIASES.get(key, {}).get(v, v)
    return v if v in _SCALES[key] else f"unknown:{v}"


def classify_tool_action(name: str, declared: str | None = None) -> str:
    if declared in ("read", "write", "irreversible"):
        return declared
    if _IRREVERSIBLE.search(name):
        return "irreversible"
    if _WRITE.search(name):
        return "write"
    return "read"


def normalize_tools(tools: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools or []:
        if isinstance(t, str):
            t = {"name": t}
        if not isinstance(t, dict) or not t.get("name"):
            continue
        name = str(t["name"])
        action = str(t.get("action", "")).lower() or None
        out.append({
            "name": name,
            "action": classify_tool_action(name, action),
            "system": t.get("system"),
            "requires_approval": bool(t.get("requires_approval", False)),
        })
    # dedupe by name, keeping the riskiest classification
    rank = {"read": 0, "write": 1, "irreversible": 2}
    best: dict[str, dict[str, Any]] = {}
    for t in out:
        cur = best.get(t["name"])
        if cur is None or rank[t["action"]] > rank[cur["action"]]:
            best[t["name"]] = t
    return sorted(best.values(), key=lambda t: t["name"])


def privilege_level(privileges: list[str], tools: list[dict[str, Any]]) -> str:
    level = 0
    if tools:
        level = max(level, 1)
    if any(t["action"] in ("write", "irreversible") for t in tools):
        level = max(level, 2)
    for p in privileges:
        if _ADMIN_PRIV.search(p):
            level = 3
            break
        if _WRITE_PRIV.search(p):
            level = max(level, 2)
        else:
            level = max(level, 1)
    return PRIVILEGE_LEVEL[level]


def normalize_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of ``raw``. Unknown keys are preserved under ``extra``."""
    a: dict[str, Any] = {}
    raw = dict(raw or {})

    # nested manifest shape -> flat
    data = raw.pop("data", None)
    if isinstance(data, dict):
        raw.setdefault("data_sensitivity", data.get("sensitivity"))
        raw.setdefault("data_types", data.get("types"))

    for key in ("id", "name", "description", "owner", "team", "model", "platform", "runtime",
                "repo", "identity", "credential_type", "last_active"):
        if raw.get(key) not in (None, ""):
            a[key] = str(raw[key]).strip()
    if "owner" in a:
        a["owner"] = a["owner"].lower()

    for key in _SCALES:
        if key == "privilege_level":
            continue
        if raw.get(key) not in (None, ""):
            a[key] = _enum(key, raw[key])

    types = raw.get("data_types") or []
    if isinstance(types, str):
        types = [x.strip() for x in types.split(",")]
    a["data_types"] = sorted({str(t).strip().lower() for t in types if str(t).strip()})

    a["tools"] = normalize_tools(raw.get("tools"))
    privs = raw.get("privileges") or []
    if isinstance(privs, str):
        privs = [x.strip() for x in privs.split(",")]
    a["privileges"] = sorted({str(p).strip() for p in privs if str(p).strip()})

    declared_priv = raw.get("privilege_level")
    derived = privilege_level(a["privileges"], a["tools"])
    if declared_priv:
        dp = _enum("privilege_level", declared_priv)
        if not dp.startswith("unknown:") and PRIVILEGE_LEVEL.index(dp) > PRIVILEGE_LEVEL.index(derived):
            derived = dp
    if a["tools"] or a["privileges"] or declared_priv:
        a["privilege_level"] = derived

    irr = raw.get("irreversible_actions")
    if irr is not None:
        a["irreversible_actions"] = bool(irr) or any(t["action"] == "irreversible" for t in a["tools"])
    elif a["tools"]:
        a["irreversible_actions"] = any(t["action"] == "irreversible" for t in a["tools"])

    controls = raw.get("controls") or {}
    if isinstance(controls, dict):
        c: dict[str, Any] = {}
        for k in ("kill_switch", "audit_logging", "input_guardrails", "output_guardrails",
                  "rate_limit", "sandboxed"):
            if k in controls:
                c[k] = bool(controls[k])
        approval = controls.get("human_approval")
        if approval is True:
            c["human_approval"] = ["*"]
        elif isinstance(approval, list):
            c["human_approval"] = sorted(str(x) for x in approval)
        elif approval is False:
            c["human_approval"] = []
        if c:
            a["controls"] = c
    approved = {t["name"] for t in a["tools"] if t["requires_approval"]}
    if approved:
        a.setdefault("controls", {})
        a["controls"]["human_approval"] = sorted(set(a["controls"].get("human_approval", [])) | approved)

    if raw.get("frameworks"):
        a["frameworks"] = sorted({str(f).lower() for f in raw["frameworks"]})

    known = set(a) | {"data", "data_sensitivity", "data_types", "tools", "privileges",
                      "privilege_level", "irreversible_actions", "controls", "links",
                      "apiVersion", "kind", "frameworks"}
    extra = {k: v for k, v in raw.items() if k not in known and v is not None}
    if extra:
        a["extra"] = extra
    return a


def link_fingerprints(links: dict[str, Any] | None) -> list[str]:
    """Turn a manifest's ``links`` block into join keys other connectors emit."""
    fps = []
    for key, value in (links or {}).items():
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v:
                fps.append(f"{key}:{v}")
    return fps
