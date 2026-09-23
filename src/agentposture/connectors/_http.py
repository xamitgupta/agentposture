"""A minimal JSON HTTP client on the standard library, so connectors need no extra packages."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import ConnectorError

USER_AGENT = "agentposture/1.0 (+https://github.com/agentposture/agentposture)"


def request(url: str, headers: dict[str, str] | None = None, data: Any = None,
            method: str | None = None, timeout: float = 30.0, raw: bool = False,
            with_link: bool = False) -> Any:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    body = None
    if data is not None:
        if isinstance(data, dict) and hdrs.get("Content-Type") == "application/x-www-form-urlencoded":
            body = urllib.parse.urlencode(data).encode()
        else:
            body = json.dumps(data).encode()
            hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URLs come from config
            payload = resp.read()
            link = resp.headers.get("Link", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="ignore")
        if exc.code in (401, 403):
            raise ConnectorError(f"{url}: access denied ({exc.code}). Check the credential "
                                 f"and its read permissions. {detail}") from exc
        raise ConnectorError(f"{url}: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"{url}: cannot connect ({exc.reason})") from exc
    if raw:
        return payload
    try:
        result = json.loads(payload or b"null")
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"{url}: response is not JSON") from exc
    return (result, link) if with_link else result


def next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None
