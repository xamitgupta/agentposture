"""Observed agents: scan source code for agent frameworks, tools and MCP servers.

Finds agents that nobody declared ("shadow agents") and pulls out facts the
risk engine cares about: which tools an agent can call, hints about human
approval, hardcoded model keys, and which MCP servers it connects to.
Works on any local checkout; the ``github`` connector reuses the same rules.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import Evidence
from ._files import repo_root, repo_slug, walk
from .base import Connector, ConnectorError, register

# framework -> patterns (import statements or dependency names)
AGENT_FRAMEWORKS: dict[str, list[str]] = {
    "langchain": [r"\bfrom\s+langchain", r"\bimport\s+langchain", r"['\"]@?langchain[/'\"]",
                  r"^langchain\b"],
    "langgraph": [r"\bfrom\s+langgraph", r"['\"]@langchain/langgraph", r"^langgraph\b"],
    "crewai": [r"\bfrom\s+crewai", r"\bimport\s+crewai", r"^crewai\b"],
    "autogen": [r"\bfrom\s+autogen", r"\bimport\s+autogen", r"^(pyautogen|autogen-agentchat)\b"],
    "llamaindex": [r"\bfrom\s+llama_index", r"['\"]llamaindex['\"]", r"^llama-index\b"],
    "openai-agents": [r"\bfrom\s+agents\s+import\s+.*Agent", r"['\"]@openai/agents['\"]",
                      r"^openai-agents\b", r"beta\.assistants"],
    "semantic-kernel": [r"\bimport\s+semantic_kernel", r"\bfrom\s+semantic_kernel",
                        r"^semantic-kernel\b"],
    "pydantic-ai": [r"\bfrom\s+pydantic_ai", r"^pydantic-ai\b"],
    "smolagents": [r"\bfrom\s+smolagents", r"^smolagents\b"],
    "google-adk": [r"\bfrom\s+google\.adk", r"^google-adk\b"],
    "strands": [r"\bfrom\s+strands\b", r"^strands-agents\b"],
    "mastra": [r"['\"]@mastra/core"],
    "vercel-ai": [r"from\s+['\"]ai['\"]"],
    "mcp-server": [r"\bfrom\s+mcp\.server", r"FastMCP\(", r"['\"]@modelcontextprotocol/sdk"],
}
LLM_SDKS: dict[str, list[str]] = {
    "openai": [r"\bimport\s+openai", r"\bfrom\s+openai\s+import", r"from\s+['\"]openai['\"]",
               r"^openai\b"],
    "anthropic": [r"\bimport\s+anthropic", r"\bfrom\s+anthropic\s+import",
                  r"['\"]@anthropic-ai/sdk['\"]", r"^anthropic\b"],
    "bedrock": [r"['\"]bedrock-runtime['\"]", r"['\"]bedrock-agent-runtime['\"]"],
    "vertexai": [r"\bimport\s+vertexai", r"\bfrom\s+vertexai"],
}
TOOL_PATTERNS = [
    re.compile(r"@(?:\w+\.)?(?:tool|function_tool|kernel_function)\b[^\n]*\n(?:\s*@[^\n]*\n)*"
               r"\s*(?:async\s+)?def\s+(\w+)"),
    re.compile(r"\b(?:Tool|StructuredTool|FunctionTool)(?:\.from_function)?\([^)]*?name\s*=\s*['\"]([\w\-]+)"),
    re.compile(r"['\"]type['\"]\s*:\s*['\"]function['\"][\s\S]{0,120}?['\"]name['\"]\s*:\s*['\"]([\w\-]+)"),
    re.compile(r"\btool\(\s*\{[\s\S]{0,200}?name\s*:\s*['\"]([\w\-]+)"),
    re.compile(r"\bserver\.tool\(\s*['\"]([\w\-]+)"),
]
AUTONOMOUS_HINTS = [r"human_input_mode\s*=\s*['\"]NEVER", r"auto_approve\s*=\s*True",
                    r"dangerously[_-]?skip[_-]?permissions", r"--yolo\b", r"allow_delegation\s*=\s*True"]
APPROVAL_HINTS = [r"interrupt_before\s*=", r"\binterrupt\(", r"HumanApprovalCallbackHandler",
                  r"human_input_mode\s*=\s*['\"](ALWAYS|TERMINATE)", r"requires?_approval\s*=\s*True",
                  r"needsApproval\s*:\s*true"]
KEY_PATTERNS = [re.compile(r"['\"](sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{24,})['\"]"),
                re.compile(r"['\"](AKIA[0-9A-Z]{16})['\"]")]
MODEL_PATTERN = re.compile(r"['\"]((?:gpt-[\w.\-]+|o[134](?:-[\w\-]+)?|claude-[\w.\-]+|"
                           r"gemini-[\w.\-]+|llama[\w.\-]*|mistral[\w.\-]*|"
                           r"anthropic\.claude[\w.:\-]*))['\"]")
HIGH_RISK_MCP = {"filesystem", "shell", "terminal", "postgres", "mysql", "sqlite", "kubernetes",
                 "aws", "gcp", "azure", "stripe", "github", "gitlab", "slack", "gmail", "browser",
                 "puppeteer", "playwright", "docker"}
MCP_FILES = {".mcp.json", "mcp.json", "claude_desktop_config.json", "mcp_config.json"}
SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".java", ".cs"}
DEP_FILES = {"requirements.txt", "pyproject.toml", "package.json", "Pipfile", "setup.py",
             "setup.cfg", "go.mod", "pom.xml", "build.gradle"}
MAX_FILE_BYTES = 512_000


def _compile(d: dict[str, list[str]]) -> dict[str, list[re.Pattern[str]]]:
    return {k: [re.compile(p, re.M) for p in v] for k, v in d.items()}


_FW = _compile(AGENT_FRAMEWORKS)
_SDK = _compile(LLM_SDKS)
_AUTO = [re.compile(p) for p in AUTONOMOUS_HINTS]
_APPR = [re.compile(p) for p in APPROVAL_HINTS]


@dataclass
class ScanResult:
    frameworks: set[str] = field(default_factory=set)
    sdks: set[str] = field(default_factory=set)
    tools: set[str] = field(default_factory=set)
    mcp_servers: set[str] = field(default_factory=set)
    models: set[str] = field(default_factory=set)
    autonomous_hint: bool = False
    approval_hint: bool = False
    hardcoded_key_files: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)

    @property
    def is_agent(self) -> bool:
        return bool(self.frameworks or self.mcp_servers or (self.sdks and self.tools))

    def scan_text(self, name: str, rel: str, text: str) -> None:
        suffix = Path(name).suffix
        is_dep = name in DEP_FILES or name.startswith("requirements")
        hit = False
        for fw, pats in _FW.items():
            if any(p.search(text) for p in pats):
                self.frameworks.add(fw)
                hit = True
        for sdk, pats in _SDK.items():
            if any(p.search(text) for p in pats):
                self.sdks.add(sdk)
                hit = True
        if name in MCP_FILES:
            self._scan_mcp(text)
            hit = True
        if suffix in SOURCE_EXT and not is_dep:
            for pat in TOOL_PATTERNS:
                self.tools.update(m.group(1) for m in pat.finditer(text))
            self.models.update(m.group(1) for m in MODEL_PATTERN.finditer(text))
            if any(p.search(text) for p in _AUTO):
                self.autonomous_hint = hit = True
            if any(p.search(text) for p in _APPR):
                self.approval_hint = hit = True
            if any(p.search(text) for p in KEY_PATTERNS):
                self.hardcoded_key_files.add(rel)
        if hit:
            self.files.add(rel)

    def _scan_mcp(self, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return
        servers = data.get("mcpServers") or data.get("servers") or {}
        if isinstance(servers, dict):
            self.mcp_servers.update(str(k) for k in servers)

    def attributes(self, name: str) -> dict[str, Any]:
        tools: list[dict[str, Any]] = [{"name": t} for t in sorted(self.tools)]
        for s in sorted(self.mcp_servers):
            action = "irreversible" if any(h in s.lower() for h in HIGH_RISK_MCP) else None
            tools.append({"name": f"mcp:{s}", "action": action, "system": s} if action
                         else {"name": f"mcp:{s}", "system": s})
        attrs: dict[str, Any] = {
            "name": name,
            "tools": tools,
            "frameworks": sorted(self.frameworks | self.sdks),
            "extra": {"evidence_files": sorted(self.files)[:25]},
        }
        if self.models:
            attrs["model"] = ", ".join(sorted(self.models)[:3])
        if self.autonomous_hint and not self.approval_hint:
            attrs["autonomy"] = "autonomous"
        elif self.approval_hint:
            attrs["autonomy"] = "act_with_approval"
        if self.hardcoded_key_files:
            attrs["credential_type"] = "hardcoded_key"
            attrs["extra"]["hardcoded_key_files"] = sorted(self.hardcoded_key_files)
        return attrs


@register
class CodeScanConnector(Connector):
    type_name = "code_scan"
    evidence_kind = "observed"
    description = "Finds agents in local code by framework imports, tool definitions and MCP configs."
    options = {"paths": "Directories to scan. Each git repository found becomes one agent.",
               "include_llm_apps": "Also report plain LLM SDK usage without tools (default false)."}

    def discover(self) -> Iterable[Evidence]:
        include_llm = bool(self.option("include_llm_apps", False))
        groups: dict[Path, ScanResult] = {}
        for p in self.option("paths", ["."]):
            root = Path(p).expanduser()
            if not root.is_absolute() and self.base_dir:
                root = Path(self.base_dir) / root
            if not root.exists():
                raise ConnectorError(f"path {root} does not exist")
            for f in walk(root):
                if f.suffix not in SOURCE_EXT and f.name not in DEP_FILES \
                        and f.name not in MCP_FILES and not f.name.startswith("requirements"):
                    continue
                try:
                    if f.stat().st_size > MAX_FILE_BYTES:
                        continue
                    text = f.read_text(errors="ignore")
                except OSError:
                    continue
                group = repo_root(f.parent) or root
                res = groups.setdefault(group, ScanResult())
                res.scan_text(f.name, str(f.relative_to(group)), text)

        for group, res in sorted(groups.items()):
            if not (res.is_agent or (include_llm and res.sdks)):
                continue
            slug = repo_slug(group) if (group / ".git").exists() else group.name.lower()
            attrs = res.attributes(slug)
            attrs["repo"] = slug
            yield self.evidence(f"repo:{slug}", attrs, [f"repo:{slug}"])
