"""Loading and validating ``agentposture.yaml``.

Design goal: one small file, sensible defaults for everything, and error
messages that tell you exactly which line to fix.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import TIERS

DEFAULT_CONFIG_NAMES = ("agentposture.yaml", "agentposture.yml", ".agentposture.yaml")


class ConfigError(ValueError):
    """Raised for any problem in the configuration file."""


_DURATION = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(value: Any, where: str = "duration") -> int:
    """Parse '30s', '15m', '6h', '7d', '2w' (or a plain int of seconds) into seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    m = _DURATION.match(str(value))
    if not m:
        raise ConfigError(f"{where}: {value!r} is not a duration. Use forms like 15m, 6h, 7d.")
    return int(m.group(1)) * _UNITS[m.group(2)]


def resolve_secret(value: Any, where: str = "value") -> Any:
    """Resolve ``env:NAME`` and ``file:/path`` references so secrets never live in the config."""
    if not isinstance(value, str):
        return value
    if value.startswith("env:"):
        name = value[4:]
        if name not in os.environ:
            raise ConfigError(f"{where}: environment variable {name} is not set.")
        return os.environ[name]
    if value.startswith("file:"):
        path = Path(value[5:]).expanduser()
        if not path.is_file():
            raise ConfigError(f"{where}: secret file {path} does not exist.")
        return path.read_text().strip()
    return value


@dataclass
class SourceConfig:
    name: str
    type: str
    enabled: bool = True
    schedule: str | None = None       # cron expression, e.g. "0 */6 * * *"
    trigger: str | None = None        # "webhook" to scan on inbound events
    webhook_secret: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: Any = None, secret: bool = False) -> Any:
        value = self.options.get(key, default)
        return resolve_secret(value, f"sources.{self.name}.{key}") if secret else value


@dataclass
class Config:
    organization: str = "My organization"
    storage_path: str = "agentposture.db"
    host: str = "127.0.0.1"
    port: int = 8484
    api_token: str | None = None
    protect_reads: bool = False
    policy: str = "default"
    sources: list[SourceConfig] = field(default_factory=list)
    on_change: bool = True
    max_age_by_tier: dict[str, int] = field(default_factory=lambda: {
        "critical": 86400, "high": 7 * 86400, "medium": 30 * 86400, "low": 90 * 86400})
    stale_after: int = 14 * 86400
    dashboard_refresh: int | None = None   # seconds; None means on-demand only
    history_days: int = 180
    base_dir: Path = field(default_factory=Path.cwd)

    def source(self, name: str) -> SourceConfig:
        for s in self.sources:
            if s.name == name:
                return s
        raise ConfigError(f"No source named {name!r}. Configured: {[s.name for s in self.sources]}")

    def resolve_path(self, p: str) -> Path:
        path = Path(p).expanduser()
        return path if path.is_absolute() else (self.base_dir / path)


_SOURCE_KEYS = {"name", "type", "enabled", "schedule", "trigger", "webhook_secret"}


def _validate_cron(expr: str, where: str) -> None:
    from .scheduler import CronSchedule  # local import avoids a cycle
    try:
        CronSchedule(expr)
    except ValueError as exc:
        raise ConfigError(f"{where}: {exc}") from exc


def load_config(path: str | Path | None = None) -> Config:
    """Load config from ``path`` or the first default file name found in cwd."""
    if path is None:
        for name in DEFAULT_CONFIG_NAMES:
            if Path(name).is_file():
                path = name
                break
        else:
            raise ConfigError("No agentposture.yaml found. Run `agentposture init` to create one.")
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file {path} does not exist.")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_config(raw, base_dir=path.resolve().parent)


def parse_config(raw: dict[str, Any], base_dir: Path | None = None) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("The config file must be a YAML mapping.")
    version = raw.get("version", 1)
    if version != 1:
        raise ConfigError(f"Unsupported config version {version!r}; this release reads version 1.")

    from .connectors import available_connectors  # registered connector types

    cfg = Config(base_dir=base_dir or Path.cwd())
    cfg.organization = str(raw.get("organization", cfg.organization))

    storage = raw.get("storage") or {}
    cfg.storage_path = str(storage.get("path", cfg.storage_path))

    server = raw.get("server") or {}
    cfg.host = str(server.get("host", cfg.host))
    cfg.port = int(server.get("port", cfg.port))
    if server.get("api_token"):
        cfg.api_token = resolve_secret(server["api_token"], "server.api_token")
    cfg.protect_reads = bool(server.get("protect_reads", False))
    if cfg.protect_reads and not cfg.api_token:
        raise ConfigError("server.protect_reads needs server.api_token to be set.")

    cfg.policy = str(raw.get("policy", cfg.policy))

    types = available_connectors()
    seen: set[str] = set()
    for i, s in enumerate(raw.get("sources") or []):
        where = f"sources[{i}]"
        if not isinstance(s, dict) or "type" not in s:
            raise ConfigError(f"{where}: each source needs at least a `type`.")
        stype = str(s["type"])
        if stype not in types:
            raise ConfigError(f"{where}: unknown source type {stype!r}. "
                              f"Available: {', '.join(sorted(types))}.")
        name = str(s.get("name", stype))
        if name in seen:
            raise ConfigError(f"{where}: duplicate source name {name!r}; give each source a unique name.")
        seen.add(name)
        schedule = s.get("schedule")
        if schedule:
            _validate_cron(str(schedule), f"{where}.schedule")
        trigger = s.get("trigger")
        if trigger not in (None, "webhook", "manual"):
            raise ConfigError(f"{where}.trigger: use `webhook` or `manual`, not {trigger!r}.")
        cfg.sources.append(SourceConfig(
            name=name, type=stype, enabled=bool(s.get("enabled", True)),
            schedule=str(schedule) if schedule else None, trigger=trigger,
            webhook_secret=s.get("webhook_secret"),
            options={k: v for k, v in s.items() if k not in _SOURCE_KEYS},
        ))

    re_cfg = raw.get("reassessment") or {}
    cfg.on_change = bool(re_cfg.get("on_change", True))
    for tier, dur in (re_cfg.get("max_age_by_tier") or {}).items():
        if tier not in TIERS:
            raise ConfigError(f"reassessment.max_age_by_tier: unknown tier {tier!r}; use {TIERS}.")
        cfg.max_age_by_tier[tier] = parse_duration(dur, f"reassessment.max_age_by_tier.{tier}")
    if "stale_after" in re_cfg:
        cfg.stale_after = parse_duration(re_cfg["stale_after"], "reassessment.stale_after")

    dash = raw.get("dashboard") or {}
    refresh = dash.get("refresh", "on_demand")
    cfg.dashboard_refresh = None if refresh in (None, "on_demand", "manual") else \
        parse_duration(refresh, "dashboard.refresh")
    cfg.history_days = int(dash.get("history_days", cfg.history_days))
    return cfg


STARTER_CONFIG = """\
# AgentPosture configuration. Every key is optional except `sources`.
# Docs: docs/configuration.md
version: 1
organization: {organization}

storage:
  path: ./agentposture.db          # a single SQLite file; back it up like any other file

server:
  host: 127.0.0.1                  # use 0.0.0.0 only behind your own auth proxy
  port: 8484
  # api_token: env:AGENTPOSTURE_TOKEN   # required for scan / register / webhook calls

policy: default                    # or a path to your own policy YAML (docs/scoring.md)

sources:
  # Agents your teams declare in an agent.yaml next to their code.
  - name: manifests
    type: manifest
    paths: ["./"]
    schedule: "*/30 * * * *"       # every 30 minutes

  # Agents found by scanning code for agent frameworks and MCP configs.
  - name: code
    type: code_scan
    paths: ["./"]
    schedule: "0 */6 * * *"        # every 6 hours

  # Uncomment the platforms you use. Credentials are read-only and come from env vars.
  # - name: github
  #   type: github
  #   org: your-org
  #   token: env:GITHUB_TOKEN
  #   trigger: webhook
  #   webhook_secret: env:GITHUB_WEBHOOK_SECRET
  #
  # - name: aws-prod
  #   type: aws_bedrock
  #   regions: [us-east-1, us-west-2]
  #   schedule: "0 * * * *"
  #
  # - name: entra
  #   type: entra_id
  #   tenant_id: env:AZURE_TENANT_ID
  #   client_id: env:AZURE_CLIENT_ID
  #   client_secret: env:AZURE_CLIENT_SECRET
  #   schedule: "0 */4 * * *"

reassessment:
  on_change: true                  # rescore an agent the moment its attributes change
  max_age_by_tier:                 # and re-check it at least this often even if nothing changed
    critical: 1d
    high: 7d
    medium: 30d
    low: 90d
  stale_after: 14d                 # flag agents no source has seen for this long

dashboard:
  refresh: on_demand               # or a duration like 5m for auto-refresh
  history_days: 180
"""
