"""
Highline Tech -- unified alert notifier
======================================
One place turns a monitor's alert into an elder-care notification and delivers it.
Monitors EMIT structured alerts (level, code, message); they do not each format
their own delivery. Modeled on devices/cameras/notifier.py: async webhook POST,
graceful failure, easy to extend (email/SMS slot in behind the same emit()).

Wiring:
  * Standalone -- a monitor run on its own has no notifier attached, so
    emit_alert() falls back to posting an HA persistent_notification (what the
    per-device code did before). Nothing about running one device changes.
  * Orchestrated -- devices/run.py builds ONE Notifier and points every monitor's
    `.notifier` at it (injecting the device slug + area), so every alert in the
    house funnels through a single delivery path.

Alert shape (what a monitor emits):  {"level", "code", "message", ...}
Notification payload (what we deliver): adds system/device/area/timestamp.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("notifier")

LEVELS = {"info": 10, "warning": 20, "critical": 30}


async def emit_alert(monitor, ha, level: str, code: str, message: str,
                     *, title: str = "Highline Tech", **extra) -> None:
    """Record an alert on the monitor and route it to the one delivery path.

    Used by every device monitor's _alert(). If the monitor has a `.notifier`
    (the orchestrator wired one), the alert goes there; otherwise it falls back
    to an HA persistent_notification so a standalone device still surfaces alerts.
    """
    rec = {"level": level, "code": code, "message": message}
    if extra:
        rec.update(extra)
    monitor.alerts.append(rec)
    log.warning("[%s] %s", code, message)

    sink = getattr(monitor, "notifier", None)
    if sink is not None:
        await sink(rec)
    elif ha is not None:
        await ha.call_service(
            "persistent_notification", "create",
            {"title": f"{title}: {level}", "message": message},
        )


class Notifier:
    """The single delivery decision point for the whole house.

    emit() takes a structured alert, filters by minimum level, builds the
    elder-care payload, records it (history -- also what the system test asserts
    on), logs it, and delivers via webhook when configured.
    """

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.webhook_url = config.get("webhook_url") or ""
        self.min_level = config.get("min_level", "info")
        self.history: list[dict] = []

    def sink_for(self, device: str, area: str | None = None):
        """Return an async sink a monitor can use as its `.notifier`.

        The sink injects which device/area produced the alert, so monitors stay
        ignorant of their own identity in the house.
        """
        async def sink(rec: dict) -> None:
            await self.emit({**rec, "device": device, "area": area})
        return sink

    async def emit(self, alert: dict) -> dict | None:
        level = alert.get("level", "info")
        if LEVELS.get(level, 0) < LEVELS.get(self.min_level, 0):
            return None
        payload = self._payload(alert)
        self.history.append(payload)
        log.warning("ALERT  %-8s %-20s %-24s %s",
                    level.upper(), payload["device"], payload["code"], payload["message"])
        if self.webhook_url:
            await send_webhook(self.webhook_url, payload)
        return payload

    def _payload(self, alert: dict) -> dict:
        return {
            "system": "highline-tech",
            "device": alert.get("device", "unknown"),
            "area": alert.get("area"),
            "level": alert.get("level", "info"),
            "code": alert.get("code", ""),
            "message": alert.get("message", ""),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def codes(self) -> list[str]:
        """Delivered alert codes, in order -- convenience for tests/inspection."""
        return [p["code"] for p in self.history]


async def send_webhook(url: str, payload: dict) -> None:
    import aiohttp  # lazy: the notifier records + logs with no third-party deps
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status < 300:
                    log.info("Notification delivered (%s)", resp.status)
                else:
                    log.warning("Notifier returned %s", resp.status)
    except Exception as exc:  # noqa: BLE001
        log.warning("Notifier delivery failed: %s", exc)
