"""Core data model.

Everything that flows through AgentPosture is one of three things:

* ``Evidence``   - a single observation about an agent, produced by one connector.
* ``Agent``      - the merged record for one agent, built from all evidence about it.
* ``Assessment`` - the scored result of running the policy against an agent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# --------------------------------------------------------------------------- #
# Normalized attribute vocabulary. Connectors map whatever they see onto these.
# Ordinal lists run from least to most risky.
# --------------------------------------------------------------------------- #

LIFECYCLE = ["development", "staging", "production", "deprecated"]
DATA_SENSITIVITY = ["public", "internal", "confidential", "restricted"]
EXPOSURE = ["internal", "partner", "customer", "public"]
AUTONOMY = ["read_only", "recommend", "act_with_approval", "autonomous"]
BUSINESS_IMPACT = ["low", "medium", "high", "critical"]
PRIVILEGE_LEVEL = ["none", "read", "write", "admin"]
TOOL_ACTIONS = ["read", "write", "irreversible"]
SENSITIVE_DATA_TYPES = {"pii", "phi", "pci", "credentials", "financial", "biometric"}

ORDINALS: dict[str, list[str]] = {
    "lifecycle": LIFECYCLE,
    "data_sensitivity": DATA_SENSITIVITY,
    "exposure": EXPOSURE,
    "autonomy": AUTONOMY,
    "business_impact": BUSINESS_IMPACT,
    "privilege_level": PRIVILEGE_LEVEL,
}

TIERS = ["low", "medium", "high", "critical"]

# Attributes where the *owner's declaration* is the source of truth.
DECLARED_AUTHORITATIVE = {"owner", "team", "name", "description", "lifecycle", "business_impact"}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ordinal(attr: str, value: Any) -> int | None:
    """Return the 0-based risk position of a value, or None if unknown."""
    scale = ORDINALS.get(attr)
    if scale is None or value is None:
        return None
    try:
        return scale.index(str(value).lower())
    except ValueError:
        return None


@dataclass
class Evidence:
    """One observation of one agent from one source."""

    source: str                      # configured source name, e.g. "aws-prod"
    source_type: str                 # connector type, e.g. "aws_bedrock"
    external_id: str                 # id of the agent inside that source
    kind: str = "observed"           # "declared" (owner told us) or "observed" (we saw it)
    attributes: dict[str, Any] = field(default_factory=dict)
    fingerprints: list[str] = field(default_factory=list)  # join keys across sources
    observed_at: str = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.kind not in ("declared", "observed"):
            raise ValueError(f"evidence kind must be declared|observed, got {self.kind!r}")
        fp = f"{self.source_type}:{self.external_id}"
        if fp not in self.fingerprints:
            self.fingerprints.append(fp)
        agent_id = self.attributes.get("id")
        if agent_id and f"id:{agent_id}" not in self.fingerprints:
            self.fingerprints.append(f"id:{agent_id}")
        self.fingerprints = sorted(set(self.fingerprints))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Agent:
    id: str
    attributes: dict[str, Any]
    declared: dict[str, Any]
    observed: dict[str, Any]
    sources: list[str]
    fingerprints: list[str]
    status: str = "active"           # active | stale
    drift: list[dict[str, Any]] = field(default_factory=list)  # observed exceeds declared
    first_seen: str = field(default_factory=utcnow)
    last_seen: str = field(default_factory=utcnow)

    @property
    def name(self) -> str:
        return str(self.attributes.get("name") or self.id)

    @property
    def is_declared(self) -> bool:
        return bool(self.declared)

    @property
    def attr_hash(self) -> str:
        return stable_hash({"a": self.attributes, "d": self.declared, "o": self.observed,
                            "s": self.status, "x": self.drift})

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["name"] = self.name
        d["is_declared"] = self.is_declared
        return d


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: str
    detail: str
    remediation: str
    frameworks: list[str] = field(default_factory=list)
    tier_if_fixed: str | None = None   # what the tier becomes if only this is fixed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Assessment:
    agent_id: str
    score: float
    tier: str
    dimensions: dict[str, dict[str, Any]]
    findings: list[Finding]
    overrides: list[str]
    policy_hash: str
    inherent_score: float = 0.0          # before controls
    control_reduction: float = 0.0       # percent removed by controls in place
    controls: dict[str, dict[str, bool]] = field(default_factory=dict)
    target_tier: str | None = None       # tier once every finding is fixed
    assessed_at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d
