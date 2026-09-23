from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentposture.config import Config, SourceConfig
from agentposture.service import PostureService
from agentposture.store import Store


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


@pytest.fixture
def make_service(tmp_path):
    def _make(sources: list[SourceConfig], **kw) -> PostureService:
        cfg = Config(organization="Test Org", storage_path=str(tmp_path / "t.db"), sources=sources,
                     base_dir=tmp_path, **kw)
        return PostureService(cfg, Store(cfg.storage_path))
    return _make


@pytest.fixture
def demo_service(make_service):
    svc = make_service([SourceConfig(name="demo", type="demo")])
    svc.scan()
    return svc
