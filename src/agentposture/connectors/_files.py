"""Shared helpers for connectors that read the local filesystem."""

from __future__ import annotations

import configparser
import os
import re
from collections.abc import Iterator
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".tox", ".mypy_cache", ".pytest_cache", "site-packages", ".next", "target"}


def walk(root: Path, max_files: int = 200_000) -> Iterator[Path]:
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                       or d in (".github",)]
        for f in filenames:
            count += 1
            if count > max_files:
                return
            yield Path(dirpath) / f


_REMOTE = re.compile(r"(?:github\.com|gitlab\.com|bitbucket\.org)[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def repo_root(path: Path) -> Path | None:
    for p in [path, *path.parents]:
        if (p / ".git").exists():
            return p
    return None


def repo_slug(root: Path) -> str:
    """Return 'owner/name' from the git remote if possible, else the directory name."""
    cfg = root / ".git" / "config"
    if cfg.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(cfg)
            for section in parser.sections():
                if section.startswith("remote"):
                    m = _REMOTE.search(parser[section].get("url", ""))
                    if m:
                        return m.group(1).lower()
        except configparser.Error:
            pass
    return root.name.lower()
