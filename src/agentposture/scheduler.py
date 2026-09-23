"""A tiny cron scheduler so AgentPosture has no external scheduling dependency.

Supports standard 5-field cron (minute hour day-of-month month day-of-week) with
``*``, ``*/n``, ``a-b``, ``a-b/n`` and comma lists, plus the shortcuts
``@hourly``, ``@daily``, ``@weekly``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

log = logging.getLogger("agentposture.scheduler")

_SHORTCUTS = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@weekly": "0 0 * * 0",
              "@monthly": "0 0 1 * *"}
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]


class CronSchedule:
    def __init__(self, expr: str):
        self.expr = expr.strip()
        text = _SHORTCUTS.get(self.expr, self.expr)
        parts = text.split()
        if len(parts) != 5:
            raise ValueError(f"cron expression {expr!r} needs 5 fields "
                             "(minute hour day month weekday), e.g. '0 */6 * * *'.")
        self.fields = [self._parse(p, lo, hi, n) for p, (lo, hi), n in zip(parts, _RANGES, _NAMES, strict=True)]
        self._dom_any = parts[2] == "*"
        self._dow_any = parts[4] == "*"

    @staticmethod
    def _parse(part: str, lo: int, hi: int, name: str) -> set[int]:
        values: set[int] = set()
        for chunk in part.split(","):
            step = 1
            if "/" in chunk:
                chunk, step_s = chunk.split("/", 1)
                if not step_s.isdigit() or int(step_s) == 0:
                    raise ValueError(f"bad step in {name} field: {part!r}")
                step = int(step_s)
            if chunk == "*":
                start, end = lo, hi
            elif "-" in chunk:
                a, b = chunk.split("-", 1)
                if not (a.isdigit() and b.isdigit()):
                    raise ValueError(f"bad range in {name} field: {part!r}")
                start, end = int(a), int(b)
            elif chunk.isdigit():
                start = end = int(chunk)
            else:
                raise ValueError(f"bad value in {name} field: {part!r}")
            if start < lo or end > hi or start > end:
                raise ValueError(f"{name} field {part!r} is outside {lo}-{hi}")
            values.update(range(start, end + 1, step))
        if name == "day-of-week":
            values = {v % 7 for v in values}  # both 0 and 7 mean Sunday
        return values

    def matches(self, dt: datetime) -> bool:
        minute, hour, dom, month, dow = self.fields
        if dt.minute not in minute or dt.hour not in hour or dt.month not in month:
            return False
        cron_dow = (dt.weekday() + 1) % 7  # cron: Sunday=0
        dom_ok, dow_ok = dt.day in dom, cron_dow in dow
        if self._dom_any or self._dow_any:
            return dom_ok and dow_ok
        return dom_ok or dow_ok  # standard cron semantics when both are restricted

    def next_after(self, dt: datetime) -> datetime:
        t = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 366 * 2):
            if self.matches(t):
                return t
            t += timedelta(minutes=1)
        raise ValueError(f"cron expression {self.expr!r} never fires")


class Scheduler:
    """Runs ``job(source_name)`` for every source whose cron schedule is due."""

    def __init__(self, schedules: dict[str, str], job: Callable[[str], object],
                 tick_seconds: float = 20.0):
        self.schedules = {name: CronSchedule(expr) for name, expr in schedules.items()}
        self.job = job
        self.tick = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        now = datetime.now(timezone.utc)
        self.next_run = {name: s.next_after(now) for name, s in self.schedules.items()}

    def run_pending(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        ran = []
        for name, due in list(self.next_run.items()):
            if now >= due:
                try:
                    self.job(name)
                except Exception:  # never let one broken source stop the others
                    log.exception("scheduled scan of %s failed", name)
                ran.append(name)
                self.next_run[name] = self.schedules[name].next_after(now)
        return ran

    def start(self) -> None:
        if not self.schedules:
            return
        def loop() -> None:
            while not self._stop.wait(self.tick):
                self.run_pending()
        self._thread = threading.Thread(target=loop, name="agentposture-scheduler", daemon=True)
        self._thread.start()
        log.info("scheduler started for %s", ", ".join(self.schedules))

    def stop(self) -> None:
        self._stop.set()
