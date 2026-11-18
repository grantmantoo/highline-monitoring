"""
Highline Tech -- Reolink camera-bundle monitor (HA integration glue)
===================================================================
Sits on the built-in Reolink integration's entities (the camera's own AI), not
the raw RTSP pipeline in devices/cameras/ (that one captures/stitches clips). This
turns the per-camera detection binary_sensors into routed notifications and
watches camera availability:

  * person / vehicle detected -- notify (elder-care cares about comings/goings),
    de-duplicated by a per-camera, per-type cooldown so a person lingering in
    frame does not fire every second
  * motion        -- logged as activity (high frequency, no notification)
  * camera offline -- camera.<name> goes 'unavailable' (PoE/uplink/IP change)

Cooldown uses an injectable clock so it is deterministic under test.

Entities (Reolink integration):
    camera.<name>                      live stream; 'unavailable' = camera down
    binary_sensor.<name>_person        AI person detection
    binary_sensor.<name>_vehicle       AI vehicle detection
    binary_sensor.<name>_motion        motion detection
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import HAClient
from notifier import emit_alert

log = logging.getLogger("reolink-cameras")

COOLDOWN_SECONDS = float(os.environ.get("CAMERA_COOLDOWN_SECONDS", "30"))
NOTIFY_KINDS = {"person", "vehicle"}
_DETECTION_SUFFIXES = ("_person", "_vehicle", "_motion")
_UNAVAILABLE = (None, "unknown", "unavailable")


def parse_detection(entity_id: str):
    """('binary_sensor.front_door_person') -> ('front_door', 'person') or None."""
    if not entity_id.startswith("binary_sensor."):
        return None
    name = entity_id.split(".", 1)[1]
    for suffix in _DETECTION_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)], suffix[1:]
    return None


class CameraMonitor:
    def __init__(self, cooldown: float = COOLDOWN_SECONDS):
        self.cooldown = cooldown
        self.alerts: list[dict] = []
        self.activity: list[dict] = []
        self._last_fired: dict[tuple[str, str], float] = {}
        self._offline: set[str] = set()
        self._clock = time.monotonic   # injectable for tests

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Camera")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})

        if entity.startswith("camera."):
            await self._handle_camera(ha, entity, state, attrs)
            return

        parsed = parse_detection(entity)
        if parsed is None or state != "on":
            return
        camera, kind = parsed
        await self._handle_detection(ha, camera, kind, attrs)

    async def _handle_camera(self, ha, entity, state, attrs) -> None:
        where = attrs.get("friendly_name", entity)
        if state in _UNAVAILABLE:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "camera_offline",
                                  f"{where} is offline -- check PoE / uplink / its static IP.")
        else:
            self._offline.discard(entity)

    async def _handle_detection(self, ha, camera, kind, attrs) -> None:
        now = self._clock()
        key = (camera, kind)
        last = self._last_fired.get(key)
        if last is not None and now - last < self.cooldown:
            return   # within cooldown, suppress
        self._last_fired[key] = now

        # Use the camera location, not the detection sensor's name (which would
        # read "... at Front Door Person").
        where = camera.replace("_", " ").title()
        if kind in NOTIFY_KINDS:
            await self._alert(ha, "info", f"{kind}_detected",
                              f"{kind.capitalize()} detected at {where}.")
        else:
            self.activity.append({"camera": camera, "kind": kind})
            log.info("motion at %s", where)


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = CameraMonitor()
    log.info("Watching Reolink detections + camera availability")
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
