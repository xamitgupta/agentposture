"""Declared agents from a spreadsheet export: the fastest way to bootstrap an inventory."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from ..models import Evidence
from ..normalize import link_fingerprints
from .base import Connector, ConnectorError, register

LIST_COLUMNS = {"data_types", "tools", "privileges", "human_approval"}
BOOL_COLUMNS = {"kill_switch", "audit_logging", "input_guardrails", "output_guardrails",
                "rate_limit", "sandboxed"}
LINK_PREFIX = "link_"


def _split(v: str) -> list[str]:
    return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "y")


@register
class CsvConnector(Connector):
    type_name = "csv"
    evidence_kind = "declared"
    description = "Agents listed in a CSV file (one row per agent)."
    options = {"path": "Path to the CSV file."}

    def discover(self) -> Iterable[Evidence]:
        path = Path(str(self.option("path", "agents.csv"))).expanduser()
        if not path.is_absolute() and self.base_dir:
            path = Path(self.base_dir) / path
        if not path.is_file():
            raise ConnectorError(f"CSV file {path} does not exist")
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=2):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                if not row.get("id") and not row.get("name"):
                    raise ConnectorError(f"{path}:{i}: each row needs an id or name")
                attrs: dict = {}
                controls: dict = {}
                links: dict = {}
                for k, v in row.items():
                    if v == "":
                        continue
                    if k.startswith(LINK_PREFIX):
                        links[k[len(LINK_PREFIX):]] = v
                    elif k in BOOL_COLUMNS:
                        controls[k] = _bool(v)
                    elif k == "human_approval":
                        controls[k] = _split(v)
                    elif k in LIST_COLUMNS:
                        attrs[k] = _split(v)
                    else:
                        attrs[k] = v
                if controls:
                    attrs["controls"] = controls
                yield self.evidence(row.get("id") or row["name"], attrs, link_fingerprints(links))
