"""GitHub organization scan: declared manifests plus code-level agent discovery, via the REST API.

Needs a token with read access to repository contents (a fine-grained token with
"Contents: read" and "Metadata: read" is enough).
"""

from __future__ import annotations

import fnmatch
import urllib.parse
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from ..models import Evidence
from ..normalize import link_fingerprints
from . import _http
from .base import Connector, ConnectorError, register
from .code_scan import DEP_FILES, MAX_FILE_BYTES, MCP_FILES, SOURCE_EXT, ScanResult
from .manifest import DEFAULT_PATTERNS, parse_manifest_docs

SKIP_PARTS = {"node_modules", "vendor", "dist", "build", ".venv", "venv", "test", "tests",
              "__tests__", "examples", "docs"}


@register
class GitHubConnector(Connector):
    type_name = "github"
    evidence_kind = "observed"
    description = "Scans a GitHub organization's repositories for manifests and agent code."
    options = {"org": "Organization (or user) to scan.",
               "repos": "Optional list of repo names to limit the scan.",
               "token": "API token, e.g. env:GITHUB_TOKEN.",
               "api_url": "GitHub Enterprise API URL (default https://api.github.com).",
               "max_files_per_repo": "Cap on files fetched per repo (default 400).",
               "include_archived": "Scan archived repositories too (default false)."}

    def __init__(self, source: Any, base_dir: Any = None):
        super().__init__(source, base_dir)
        self.api = str(self.option("api_url", "https://api.github.com")).rstrip("/")
        token = self.option("token", None, secret=True)
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path_or_url: str, raw: bool = False) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.api}{path_or_url}"
        headers = dict(self.headers)
        if raw:
            headers["Accept"] = "application/vnd.github.raw"
        return _http.request(url, headers=headers, raw=raw)

    def _paged(self, path: str) -> Iterable[dict[str, Any]]:
        url: str | None = f"{self.api}{path}{'&' if '?' in path else '?'}per_page=100"
        while url:
            page, link = _http.request(url, headers=self.headers, with_link=True)
            yield from page
            url = _http.next_link(link)

    def repos(self) -> list[dict[str, Any]]:
        org = self.option("org")
        if not org:
            raise ConnectorError("github source needs `org`")
        wanted = set(self.option("repos", []) or [])
        try:
            items = list(self._paged(f"/orgs/{org}/repos?type=all"))
        except ConnectorError:
            items = list(self._paged(f"/users/{org}/repos?type=owner"))
        keep_archived = bool(self.option("include_archived", False))
        return [r for r in items if (not wanted or r["name"] in wanted)
                and (keep_archived or not r.get("archived"))]

    def discover(self) -> Iterable[Evidence]:
        cap = int(self.option("max_files_per_repo", 400))
        for repo in self.repos():
            full = repo["full_name"]
            slug = full.lower()
            branch = repo.get("default_branch") or "main"
            try:
                tree = self._get(f"/repos/{full}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
            except ConnectorError:
                continue  # empty repository
            blobs = [t for t in tree.get("tree", []) if t.get("type") == "blob"]

            manifests = [b for b in blobs
                         if any(fnmatch.fnmatch(PurePosixPath(b["path"]).name, p) for p in DEFAULT_PATTERNS)]
            for b in manifests:
                text = self._get(f"/repos/{full}/contents/{urllib.parse.quote(b['path'])}", raw=True)
                docs = parse_manifest_docs(text.decode(errors="ignore"), f"{full}/{b['path']}")
                for doc in docs:
                    links = dict(doc.get("links") or {})
                    if len(docs) == 1 and len(manifests) == 1:
                        links.setdefault("repo", slug)
                    attrs = {k: v for k, v in doc.items() if k != "links"}
                    attrs.setdefault("repo", slug)
                    yield self.evidence(f"{slug}:{doc.get('id') or doc.get('name')}", attrs,
                                        link_fingerprints(links), kind="declared")

            candidates = []
            for b in blobs:
                p = PurePosixPath(b["path"])
                if any(part in SKIP_PARTS for part in p.parts[:-1]):
                    continue
                if (p.suffix in SOURCE_EXT or p.name in DEP_FILES or p.name in MCP_FILES
                        or p.name.startswith("requirements")) and b.get("size", 0) <= MAX_FILE_BYTES:
                    candidates.append(b)
            # dependency and MCP files first: they are the cheapest strong signals
            candidates.sort(key=lambda b: (PurePosixPath(b["path"]).name not in DEP_FILES | MCP_FILES,
                                           b["path"].count("/")))
            res = ScanResult()
            for b in candidates[:cap]:
                try:
                    text = self._get(f"/repos/{full}/contents/{urllib.parse.quote(b['path'])}", raw=True)
                except ConnectorError:
                    continue
                res.scan_text(PurePosixPath(b["path"]).name, b["path"], text.decode(errors="ignore"))
            if res.is_agent:
                attrs = res.attributes(slug)
                attrs["repo"] = slug
                attrs["extra"]["html_url"] = repo.get("html_url")
                if repo.get("visibility") == "public":
                    attrs["extra"]["public_repository"] = True
                yield self.evidence(f"repo:{slug}", attrs, [f"repo:{slug}"])
