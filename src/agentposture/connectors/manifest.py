"""Declared agents: ``agent.yaml`` manifests committed next to agent code.

This is the primary way owners tell AgentPosture what the infrastructure cannot:
business impact, data sensitivity, intended autonomy, and which controls exist.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from ..models import Evidence
from ..normalize import link_fingerprints
from ._files import repo_root, repo_slug, walk
from .base import Connector, ConnectorError, register

DEFAULT_PATTERNS = ["agent.yaml", "agent.yml", "*.agent.yaml", "*.agent.yml", "agents.yaml"]


def parse_manifest_docs(text: str, origin: str) -> list[dict[str, Any]]:
    """A manifest file may hold one agent, a multi-document stream, or an ``agents:`` list."""
    try:
        docs = [d for d in yaml.safe_load_all(text) if d]
    except yaml.YAMLError as exc:
        raise ConnectorError(f"{origin}: invalid YAML: {exc}") from exc
    agents: list[dict[str, Any]] = []
    for d in docs:
        if not isinstance(d, dict):
            raise ConnectorError(f"{origin}: expected a mapping at the top level")
        if isinstance(d.get("agents"), list):
            agents.extend(a for a in d["agents"] if isinstance(a, dict))
        elif d.get("kind", "Agent") == "Agent":
            agents.append(d)
    for a in agents:
        if not a.get("id") and not a.get("name"):
            raise ConnectorError(f"{origin}: every agent needs an `id` (or at least a `name`)")
    return agents


@register
class ManifestConnector(Connector):
    type_name = "manifest"
    evidence_kind = "declared"
    description = "Agents declared by their owners in agent.yaml files."
    options = {"paths": "Directories to search (default: current directory).",
               "patterns": f"File name patterns (default: {DEFAULT_PATTERNS})."}

    def discover(self) -> Iterable[Evidence]:
        patterns = self.option("patterns", DEFAULT_PATTERNS)
        files: list[Path] = []
        for p in self.option("paths", ["."]):
            root = Path(p).expanduser()
            if not root.is_absolute() and self.base_dir:
                root = Path(self.base_dir) / root
            if root.is_file():
                files.append(root)
                continue
            if not root.exists():
                raise ConnectorError(f"path {root} does not exist")
            files += [f for f in walk(root) if any(fnmatch.fnmatch(f.name, pat) for pat in patterns)]

        per_repo: dict[str, int] = {}
        parsed: list[tuple[Path, dict[str, Any], str | None]] = []
        for f in sorted(set(files)):
            root = repo_root(f.parent)
            slug = repo_slug(root) if root else None
            for doc in parse_manifest_docs(f.read_text(), str(f)):
                parsed.append((f, doc, slug))
                if slug:
                    per_repo[slug] = per_repo.get(slug, 0) + 1

        for _f, doc, slug in parsed:
            links = dict(doc.get("links") or {})
            # A repo that holds exactly one declared agent is linked to that agent
            # automatically, so code-scan findings for the repo join the declaration.
            if slug and per_repo.get(slug) == 1:
                links.setdefault("repo", slug)
            attrs = dict(doc)
            attrs.pop("links", None)
            attrs.setdefault("repo", links.get("repo"))
            ext_id = str(doc.get("id") or doc.get("name"))
            yield self.evidence(ext_id, attrs, link_fingerprints(links))
