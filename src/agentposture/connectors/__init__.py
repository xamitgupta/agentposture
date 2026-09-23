"""Connector registry.

Built-in connectors register themselves with :func:`register`. Third-party
packages can add connectors without forking by exposing an entry point in the
``agentposture.connectors`` group that points at a :class:`Connector` subclass.
"""

from __future__ import annotations

import logging
from importlib import import_module
from importlib.metadata import entry_points

from .base import Connector, ConnectorError, register, registry

log = logging.getLogger("agentposture.connectors")

_BUILTINS = ["manifest", "csv_import", "code_scan", "github", "aws_bedrock", "entra_id",
             "http_json", "demo"]
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    for mod in _BUILTINS:
        import_module(f"{__name__}.{mod}")
    try:
        eps = entry_points(group="agentposture.connectors")
    except TypeError:  # Python < 3.10 signature
        eps = entry_points().get("agentposture.connectors", [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            cls = ep.load()
            register(cls)
        except Exception:
            log.exception("could not load connector plugin %s", ep.name)
    _loaded = True


def available_connectors() -> dict[str, type[Connector]]:
    _load()
    return dict(registry)


def get_connector(type_name: str) -> type[Connector]:
    _load()
    try:
        return registry[type_name]
    except KeyError:
        raise ConnectorError(f"unknown connector type {type_name!r}") from None


__all__ = ["Connector", "ConnectorError", "available_connectors", "get_connector", "register"]
