"""The connector contract.

A connector has one job: yield :class:`~agentposture.models.Evidence` for every
agent it can see. It does not score, store, or deduplicate; the registry and the
risk engine do that. That keeps a new connector to roughly 50 lines.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar

from ..models import Evidence

if TYPE_CHECKING:
    from ..config import SourceConfig

registry: dict[str, type[Connector]] = {}


class ConnectorError(RuntimeError):
    """Raised when a connector cannot reach or read its source. The message is shown to users."""


class Connector:
    #: The value used in ``type:`` in agentposture.yaml.
    type_name: ClassVar[str] = ""
    #: "declared" for sources where owners describe agents, "observed" for discovery.
    evidence_kind: ClassVar[str] = "observed"
    #: One-line description shown by ``agentposture connectors``.
    description: ClassVar[str] = ""
    #: Option names this connector understands (for docs and validation messages).
    options: ClassVar[dict[str, str]] = {}

    def __init__(self, source: SourceConfig, base_dir: Any = None):
        self.source = source
        self.base_dir = base_dir

    # -- helpers ------------------------------------------------------------
    def option(self, key: str, default: Any = None, secret: bool = False) -> Any:
        return self.source.option(key, default, secret=secret)

    def evidence(self, external_id: str, attributes: dict[str, Any],
                 fingerprints: list[str] | None = None, kind: str | None = None) -> Evidence:
        from ..normalize import normalize_attributes
        attrs = normalize_attributes(attributes)
        attrs.setdefault("platform", self.type_name)
        return Evidence(source=self.source.name, source_type=self.type_name,
                        external_id=str(external_id), kind=kind or self.evidence_kind,
                        attributes=attrs, fingerprints=list(fingerprints or []))

    # -- contract -----------------------------------------------------------
    def discover(self) -> Iterable[Evidence]:
        raise NotImplementedError

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Return True if an inbound webhook is authentic. Default: shared-secret HMAC-SHA256."""
        import hashlib
        import hmac
        secret = self.source.webhook_secret
        if not secret:
            return False
        from ..config import resolve_secret
        key = str(resolve_secret(secret, f"sources.{self.source.name}.webhook_secret")).encode()
        expected = "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()
        lower = {k.lower(): v for k, v in headers.items()}
        got = lower.get("x-hub-signature-256") or lower.get("x-agentposture-signature") or ""
        return hmac.compare_digest(expected, got)


def register(cls: type[Connector]) -> type[Connector]:
    if not cls.type_name:
        raise ValueError(f"{cls.__name__} must set type_name")
    registry[cls.type_name] = cls
    return cls
