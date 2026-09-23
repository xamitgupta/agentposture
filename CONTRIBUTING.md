# Contributing

Thank you for helping. The project values simplicity above features: a change that makes
AgentPosture easier to adopt is worth more than one that makes it do more.

## Set up

```bash
git clone https://github.com/xamitgupta/agentposture && cd agentposture
python -m venv .venv && . .venv/bin/activate
make dev          # editable install with test and lint tools
make test lint
make demo         # see your change in the dashboard
```

## Ground rules

- **No new runtime dependencies** without discussion in an issue first. Optional extras are fine
  for connectors that need an SDK.
- **Connectors are read-only** and document their minimum permissions.
- **Tests do not touch the network.** Use fixtures and temporary directories.
- **Scoring changes** update `policies/default.yaml`, `docs/scoring.md`, the tests, and the sample
  dashboard (`make sample`), and explain the reasoning in the pull request.
- **Dashboard** stays dependency-free and build-free: plain HTML, CSS and JavaScript.
- Keep user-facing messages actionable: say what went wrong and how to fix it.

## Good first contributions

- A connector for a platform you use (see `docs/writing-a-connector.md`).
- More framework and tool patterns in `connectors/code_scan.py`, each with a test.
- Framework mappings (ISO/IEC 42001, EU AI Act) as additional `frameworks:` entries in the policy.

## Pull requests

Small and focused. Describe the problem, the change, and how you tested it. CI runs lint and tests
on Python 3.10 to 3.13 and builds the container image.

By contributing you agree that your contributions are licensed under the Apache License 2.0.
