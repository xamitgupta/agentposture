"""HTTP API and dashboard, on the standard library.

Read endpoints
  GET  /api/summary                 posture for leadership
  GET  /api/agents?tier=&team=&q=&flag=
  GET  /api/agents/<id>             one agent: attributes, assessment, history
  GET  /api/sources                 connector health and schedule
  GET  /api/runs                    recent scan runs
  GET  /api/status                  whether a scan is running
  GET  /healthz

Write endpoints (need the API token, or a loopback client when no token is set)
  POST   /api/scan                  {"source": "optional-name"}  -> scan now
  POST   /api/agents                agent manifest as JSON        -> declare an agent
  DELETE /api/agents/<id>           remove an API-declared agent
  POST   /api/webhooks/<source>     signed webhook -> rescan that source
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .connectors import ConnectorError, get_connector
from .scheduler import Scheduler
from .service import PostureService

log = logging.getLogger("agentposture.server")
MAX_BODY = 1_000_000


class _State:
    def __init__(self, service: PostureService):
        self.service = service
        self.scanning: str | None = None
        self.last_report: dict[str, Any] | None = None
        self.lock = threading.Lock()

    def scan_async(self, source: str | None, trigger: str) -> bool:
        with self.lock:
            if self.scanning:
                return False
            self.scanning = source or "all"

        def run() -> None:
            try:
                self.last_report = self.service.scan(source, trigger=trigger).to_dict()
            finally:
                self.scanning = None
        threading.Thread(target=run, name="agentposture-scan", daemon=True).start()
        return True


def _static(name: str) -> bytes | None:
    try:
        f = resources.files("agentposture.dashboard").joinpath(name)
        return f.read_bytes() if f.is_file() else None
    except (FileNotFoundError, IsADirectoryError):
        return None


def make_handler(state: _State) -> type[BaseHTTPRequestHandler]:
    service = state.service
    token = service.config.api_token
    protect_reads = bool(token) and bool(getattr(service.config, "protect_reads", False))

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentPosture"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

        # -- helpers --------------------------------------------------------
        def _send(self, status: int, body: Any, ctype: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
                                 "style-src-attr 'unsafe-inline'; "
                                 "font-src https://fonts.gstatic.com; img-src 'self' data:")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _error(self, status: int, message: str) -> None:
            self._send(status, {"error": message})

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("request body too large")
            return self.rfile.read(length) if length else b""

        def _authorized(self) -> bool:
            if token:
                got = self.headers.get("Authorization", "")
                return hmac.compare_digest(got, f"Bearer {token}")
            try:
                return ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                return False

        # -- routes ---------------------------------------------------------
        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            url = urlparse(self.path)
            path = url.path.rstrip("/") or "/"
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}
            if path == "/healthz":
                return self._send(200, {"ok": True})
            if path.startswith("/api/"):
                if protect_reads and not self._authorized():
                    return self._error(401, "missing or wrong API token")
                return self._api_get(path, qs)
            name = "index.html" if path == "/" else path.lstrip("/")
            if "/" in name or name.startswith("."):
                return self._error(404, "not found")
            data = _static(name)
            if data is None:
                return self._error(404, "not found")
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, data, ctype)

        def _api_get(self, path: str, qs: dict[str, str]) -> None:
            if path == "/api/summary":
                return self._send(200, service.summary())
            if path == "/api/agents":
                return self._send(200, service.agents_view(qs.get("tier"), qs.get("team"),
                                                           qs.get("q"), qs.get("flag")))
            if path.startswith("/api/agents/"):
                detail = service.agent_detail(unquote(path[len("/api/agents/"):]))
                return self._send(200, detail) if detail else self._error(404, "no such agent")
            if path == "/api/sources":
                return self._send(200, service.sources_view())
            if path == "/api/runs":
                return self._send(200, service.store.runs(int(qs.get("limit", 50))))
            if path == "/api/status":
                return self._send(200, {"scanning": state.scanning, "last_report": state.last_report,
                                        "write_allowed": self._authorized(),
                                        "token_required": bool(token)})
            self._error(404, "unknown endpoint")

        def do_POST(self) -> None:
            path = urlparse(self.path).path.rstrip("/")
            try:
                body = self._body()
            except ValueError as exc:
                return self._error(413, str(exc))
            if path.startswith("/api/webhooks/"):
                return self._webhook(unquote(path[len("/api/webhooks/"):]), body)
            if not self._authorized():
                return self._error(401, "this action needs the API token (Authorization: Bearer ...)")
            try:
                payload = json.loads(body or b"{}")
            except json.JSONDecodeError:
                return self._error(400, "body must be JSON")
            if path == "/api/scan":
                src = payload.get("source")
                if src and src not in {s.name for s in service.config.sources}:
                    return self._error(404, f"no source named {src}")
                started = state.scan_async(src, "on_demand")
                return self._send(202 if started else 409,
                                  {"started": started, "scanning": state.scanning})
            if path == "/api/agents":
                try:
                    return self._send(201, service.register(payload))
                except (ConnectorError, ValueError, KeyError) as exc:
                    return self._error(400, str(exc))
            self._error(404, "unknown endpoint")

        def do_DELETE(self) -> None:
            path = urlparse(self.path).path.rstrip("/")
            if not self._authorized():
                return self._error(401, "this action needs the API token")
            if path.startswith("/api/agents/"):
                ok = service.unregister(unquote(path[len("/api/agents/"):]))
                return self._send(200 if ok else 404, {"removed": ok})
            self._error(404, "unknown endpoint")

        def _webhook(self, source_name: str, body: bytes) -> None:
            try:
                src = service.config.source(source_name)
            except Exception:
                return self._error(404, "unknown source")
            if src.trigger != "webhook":
                return self._error(403, "webhooks are not enabled for this source")
            connector = get_connector(src.type)(src, base_dir=service.config.base_dir)
            try:
                valid = connector.verify_webhook(dict(self.headers.items()), body)
            except Exception:
                valid = False
            if not valid:
                return self._error(401, "invalid webhook signature")
            started = state.scan_async(source_name, "webhook")
            self._send(202, {"accepted": True, "started": started})

    return Handler


def serve(service: PostureService, host: str | None = None, port: int | None = None,
          scan_on_start: bool = True) -> None:
    cfg = service.config
    host, port = host or cfg.host, port or cfg.port
    state = _State(service)
    schedules = {s.name: s.schedule for s in cfg.sources if s.enabled and s.schedule}
    scheduler = Scheduler(schedules, lambda name: service.scan(name, trigger="schedule"))

    # Tier-based max age must be honored even when no source changes.
    def reassess_loop() -> None:
        while True:
            threading.Event().wait(3600)
            try:
                service.reconcile()
            except Exception:
                log.exception("periodic reassessment failed")

    if scan_on_start:
        state.scan_async(None, "startup")
    scheduler.start()
    threading.Thread(target=reassess_loop, name="agentposture-reassess", daemon=True).start()

    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    log.info("dashboard on http://%s:%d", host, port)
    print(f"AgentPosture dashboard: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        httpd.server_close()
