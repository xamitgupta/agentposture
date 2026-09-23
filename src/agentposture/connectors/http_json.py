"""Any JSON API or file: plug in an existing internal agent registry, Backstage, a CMDB export.

You describe where the list of agents is and how its fields map onto AgentPosture
attributes. Nothing else is needed.

    - name: internal-registry
      type: http_json
      url: https://registry.internal/api/agents
      headers: {Authorization: env:REGISTRY_TOKEN}
      items_path: data.items            # where the list lives in the response
      next_path: data.next_page_url     # optional pagination link
      id_field: agent_id
      mapping:                          # attribute: dotted.path.in.item
        name: display_name
        owner: owner.email
        autonomy: risk.autonomy
      links:                            # join keys to other sources
        identity: service_principal_id
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..config import resolve_secret
from ..models import Evidence
from . import _http
from .base import Connector, ConnectorError, register


def dig(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit() and int(part) < len(obj):
            obj = obj[int(part)]
        else:
            return None
    return obj


@register
class HttpJsonConnector(Connector):
    type_name = "http_json"
    evidence_kind = "declared"
    description = "Agents from any JSON API or file (internal registries, Backstage, CMDB exports)."
    options = {"url": "Endpoint returning JSON.", "file": "Or a local JSON file.",
               "headers": "Request headers; values may be env: references.",
               "items_path": "Dotted path to the list of agents.",
               "next_path": "Dotted path to the next-page URL.",
               "id_field": "Field holding the agent id (default id).",
               "mapping": "attribute -> dotted path. Unmapped attributes pass through by name.",
               "links": "join key -> dotted path.",
               "kind": "declared (default) or observed."}

    def _pages(self) -> Iterable[Any]:
        if self.option("file"):
            path = Path(str(self.option("file"))).expanduser()
            if not path.is_absolute() and self.base_dir:
                path = Path(self.base_dir) / path
            if not path.is_file():
                raise ConnectorError(f"file {path} does not exist")
            yield json.loads(path.read_text())
            return
        url = self.option("url")
        if not url:
            raise ConnectorError("http_json source needs `url` or `file`")
        headers = {k: str(resolve_secret(v, f"sources.{self.source.name}.headers.{k}"))
                   for k, v in (self.option("headers", {}) or {}).items()}
        pages = 0
        while url and pages < 1000:
            page = _http.request(url, headers=headers)
            yield page
            url = dig(page, self.option("next_path")) if self.option("next_path") else None
            pages += 1

    def discover(self) -> Iterable[Evidence]:
        mapping: dict[str, str] = self.option("mapping", {}) or {}
        links: dict[str, str] = self.option("links", {}) or {}
        id_field = self.option("id_field", "id")
        kind = self.option("kind", "declared")
        for page in self._pages():
            items = dig(page, self.option("items_path"))
            if not isinstance(items, list):
                raise ConnectorError(f"items_path {self.option('items_path')!r} did not point at a list")
            for item in items:
                if not isinstance(item, dict):
                    continue
                ext = dig(item, id_field) or dig(item, mapping.get("name", "name"))
                if not ext:
                    continue
                attrs = {k: v for k, v in item.items() if k not in mapping.values()}
                attrs.update({attr: dig(item, path) for attr, path in mapping.items()})
                attrs.setdefault("id", str(ext))
                fps = [f"{k}:{dig(item, p)}" for k, p in links.items() if dig(item, p)]
                yield self.evidence(str(ext), attrs, fps, kind=kind)
