# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-09-23

### Fixed
- Dashboard charts (fleet strip, tier mix, legends, control coverage) did not render when served by
  `agentposture serve` or `demo`, because the Content-Security-Policy blocked inline style attributes.

## [1.0.0] - 2026-09-23

### Added
- Connectors: `manifest`, `code_scan`, `github`, `aws_bedrock`, `entra_id`, `http_json`, `csv`,
  `demo`, plus entry-point plugins for third-party connectors.
- Registry with fingerprint-based joining, risk-conservative merge, drift and shadow-agent
  detection, stale-agent tracking.
- Risk engine with a YAML policy: six weighted dimensions, controls-based residual risk, tier
  overrides, 16 findings with remediation, NIST AI RMF, OWASP LLM Top 10 (2025) and CWE mappings,
  and tier-if-fixed for each finding.
- Reassessment on change, on policy change, and by tier maximum age.
- Per-source cron schedules, signed webhooks, and on-demand scans.
- Dashboard (posture, agents, sources, agent detail) with no build step, and static HTML snapshots.
- REST API, Markdown/CSV/JSON reports, `agentposture check` CI gate and a GitHub Action.
- Docker image, docker compose demo, Kubernetes and systemd deployment files.
