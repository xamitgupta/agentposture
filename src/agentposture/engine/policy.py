"""Policy loading and the small condition language used by overrides and findings.

A condition is either a predicate or a combinator::

    {attr: autonomy, is: autonomous}
    {attr: exposure, at_least: customer}          # ordinal comparison
    {attr: data_types, contains_any: [pii, phi]}
    {attr: owner, missing: true}
    {attr: tools, not_empty: true}
    {attr: controls.kill_switch, is_not: true}    # dotted paths reach nested values
    {all: [...]}  {any: [...]}  {not: {...}}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from ..models import TIERS, ordinal, stable_hash

DIMENSIONS = ("autonomy", "privilege", "data_sensitivity", "exposure", "business_impact", "ownership")
SEVERITIES = ("low", "medium", "high", "critical")
CONTROLS = ("human_approval", "kill_switch", "audit_logging", "input_guardrails",
            "output_guardrails", "rate_limit", "sandboxed")
_PREDICATES = {"is", "is_not", "in", "at_least", "at_most", "missing", "not_empty", "contains_any"}


class PolicyError(ValueError):
    pass


def get_path(facts: dict[str, Any], path: str) -> Any:
    cur: Any = facts
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def evaluate(cond: Any, facts: dict[str, Any]) -> bool:
    if not isinstance(cond, dict):
        raise PolicyError(f"condition must be a mapping, got {cond!r}")
    if "all" in cond:
        return all(evaluate(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(evaluate(c, facts) for c in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], facts)
    attr = cond.get("attr")
    if not attr:
        raise PolicyError(f"condition needs `attr`, `all`, `any` or `not`: {cond!r}")
    value = get_path(facts, attr)
    base = attr.split(".")[-1]
    for op, expected in cond.items():
        if op == "attr":
            continue
        if op == "is":
            ok = value == expected
        elif op == "is_not":
            ok = value != expected
        elif op == "in":
            ok = value in expected
        elif op in ("at_least", "at_most"):
            ov, oe = ordinal(base, value), ordinal(base, expected)
            if oe is None:
                raise PolicyError(f"{expected!r} is not a known level of {base}")
            ok = ov is not None and (ov >= oe if op == "at_least" else ov <= oe)
        elif op == "missing":
            ok = (value in (None, "", [], {})) == bool(expected)
        elif op == "not_empty":
            ok = bool(value) == bool(expected)
        elif op == "contains_any":
            ok = bool(set(value or []) & set(expected))
        else:
            raise PolicyError(f"unknown operator {op!r} in {cond!r}; use one of {sorted(_PREDICATES)}")
        if not ok:
            return False
    return True


def _check_condition(cond: Any, where: str) -> None:
    if not isinstance(cond, dict):
        raise PolicyError(f"{where}: condition must be a mapping")
    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list):
                raise PolicyError(f"{where}.{key}: must be a list")
            for i, c in enumerate(cond[key]):
                _check_condition(c, f"{where}.{key}[{i}]")
            return
    if "not" in cond:
        _check_condition(cond["not"], f"{where}.not")
        return
    if "attr" not in cond:
        raise PolicyError(f"{where}: needs `attr`, `all`, `any` or `not`")
    unknown = set(cond) - _PREDICATES - {"attr"}
    if unknown:
        raise PolicyError(f"{where}: unknown operator(s) {sorted(unknown)}")


@dataclass
class Policy:
    name: str
    weights: dict[str, float]
    unknown_levels: dict[str, int]
    sensitive_types: dict[str, list[str]]
    thresholds: dict[str, float]
    overrides: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    control_weights: dict[str, float] = field(default_factory=dict)
    max_reduction: float = 0.0
    hash: str = field(default="")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Policy:
        if not isinstance(raw, dict) or raw.get("version", 1) != 1:
            raise PolicyError("policy must be a mapping with version: 1")
        dims = raw.get("dimensions") or {}
        unknown = set(dims) - set(DIMENSIONS)
        if unknown:
            raise PolicyError(f"unknown dimension(s) {sorted(unknown)}; use {list(DIMENSIONS)}")
        weights = {d: float((dims.get(d) or {}).get("weight", 0)) for d in DIMENSIONS}
        if sum(weights.values()) <= 0:
            raise PolicyError("at least one dimension needs a positive weight")
        unknown_levels = {d: int((dims.get(d) or {}).get("unknown_level", 3)) for d in DIMENSIONS}
        tiers = raw.get("tiers") or {}
        thresholds = {t: float(tiers[t]) for t in ("critical", "high", "medium") if t in tiers}
        if not (thresholds.get("critical", 101) >= thresholds.get("high", 0) >= thresholds.get("medium", 0)):
            raise PolicyError("tier thresholds must satisfy critical >= high >= medium")
        overrides = list(raw.get("overrides") or [])
        for i, o in enumerate(overrides):
            if o.get("min_tier") not in TIERS:
                raise PolicyError(f"overrides[{i}] ({o.get('id')}): min_tier must be one of {TIERS}")
            _check_condition(o.get("when"), f"overrides[{i}].when")
        findings = list(raw.get("findings") or [])
        ids = set()
        for i, f in enumerate(findings):
            for key in ("id", "title", "severity", "when", "remediation"):
                if key not in f:
                    raise PolicyError(f"findings[{i}] needs `{key}`")
            if f["severity"] not in SEVERITIES:
                raise PolicyError(f"findings[{i}] ({f['id']}): severity must be one of {SEVERITIES}")
            if f["id"] in ids:
                raise PolicyError(f"duplicate finding id {f['id']}")
            ids.add(f["id"])
            _check_condition(f["when"], f"findings[{i}].when")
        ctrl = raw.get("controls") or {}
        cweights = {k: float(v) for k, v in (ctrl.get("weights") or {}).items()}
        bad = set(cweights) - set(CONTROLS)
        if bad:
            raise PolicyError(f"unknown control(s) {sorted(bad)}; use {list(CONTROLS)}")
        max_red = float(ctrl.get("max_reduction", 0))
        if not 0 <= max_red <= 90:
            raise PolicyError("controls.max_reduction must be between 0 and 90 (percent)")
        return cls(name=str(raw.get("name", "custom policy")), weights=weights,
                   control_weights=cweights, max_reduction=max_red / 100,
                   unknown_levels=unknown_levels,
                   sensitive_types={k: list(v) for k, v in (raw.get("sensitive_data_types") or {}).items()},
                   thresholds=thresholds, overrides=overrides, findings=findings,
                   hash=stable_hash(raw))

    def tier_for(self, score: float) -> str:
        for tier in ("critical", "high", "medium"):
            if tier in self.thresholds and score >= self.thresholds[tier]:
                return tier
        return "low"


def load_policy(ref: str = "default", base_dir: Path | None = None) -> Policy:
    if ref == "default":
        text = resources.files("agentposture.policies").joinpath("default.yaml").read_text()
    else:
        path = Path(ref).expanduser()
        if not path.is_absolute() and base_dir:
            path = base_dir / path
        if not path.is_file():
            raise PolicyError(f"policy file {path} does not exist")
        text = path.read_text()
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy is not valid YAML: {exc}") from exc
    return Policy.from_dict(raw)
