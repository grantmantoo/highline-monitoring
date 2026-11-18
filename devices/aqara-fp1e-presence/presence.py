"""
Highline Tech -- Aqara FP1E mmWave presence monitor
==================================================
The cornerstone elder-care sensor. FP1E radar holds occupancy `on` for a person
who is sitting or sleeping still (PIR cannot), and is USB-powered so it never
sleeps. This builds the wellness logic on top of the per-room occupancy entities:

  * no activity anywhere -- no presence in ANY room for > N hours (a wellness
    check: someone may have left, fallen out of range, or be in trouble)
  * prolonged presence in a concern room -- continuous occupancy in e.g. the
    bathroom past a threshold (a possible fall / someone down)
  * occupancy-driven lights that do NOT time out on a motionless occupant
    (light.<room> follows presence)
  * sensor offline -- 'unavailable' means we are blind in that room; alert

The wellness/linger timers use an injectable clock so they are deterministic
under test; run() polls them on an interval in production.

Entities (ZHA, one FP1E per room, assigned to its Area):
    binary_sensor.<room>_occupancy   device_class occupancy, on = person present
    light.<room>                     driven on/off by presence (optional)
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

log = logging.getLogger("aqara-fp1e")

NO_ACTIVITY_SECONDS = float(os.environ.get("PRESENCE_NO_ACTIVITY_SECONDS", str(6 * 3600)))
LINGER_SECONDS = float(os.environ.get("PRESENCE_LINGER_SECONDS", str(30 * 60)))
CONCERN_ROOMS = set(os.environ.get("PRESENCE_CONCERN_ROOMS", "bathroom").split(","))
CONTROL_LIGHTS = os.environ.get("PRESENCE_CONTROL_LIGHTS", "1") == "1"

_PRESENCE_CLASSES = {"occupancy", "presence", "motion"}
_UNKNOWN = (None, "unknown", "unavailable")


def room_of(entity_id: str) -> str:
    name = entity_id.split(".", 1)[-1]
    for suffix in ("_occupancy", "_presence", "_motion"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def is_presence(entity_id: str, attrs: dict) -> bool:
    return entity_id.startswith("binary_sensor.") and (
        attrs.get("device_class") in _PRESENCE_CLASSES
        or entity_id.endswith(("_occupancy", "_presence"))
    )


class PresenceMonitor:
    def __init__(self, concern_rooms=None, no_activity_seconds: float = NO_ACTIVITY_SECONDS,
                 linger_seconds: float = LINGER_SECONDS, control_lights: bool = CONTROL_LIGHTS):
        self.concern_rooms = set(concern_rooms) if concern_rooms is not None else set(CONCERN_ROOMS)
        self.no_activity_seconds = no_activity_seconds
        self.linger_seconds = linger_seconds
        self.control_lights = control_lights
        self.alerts: list[dict] = []
        self._present: set[str] = set()
        self._present_since: dict[str, float] = {}
        self._last_activity: float = time.monotonic()
        self._no_activity_alerted = False
        self._linger_alerted: set[str] = set()
        self._offline: set[str] = set()
        self._clock = time.monotonic   # injectable for tests

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Presence")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})
        if not is_presence(entity, attrs):
            return

        room = room_of(entity)
        if state in _UNKNOWN:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "presence_offline",
                                  f"{room} presence sensor is unavailable -- no occupancy "
                                  f"coverage in that room until it returns.")
            # A dead sensor must not read as occupied (that would false-fire
            # prolonged_presence). Drop the room from presence and let _offline mark
            # it UNKNOWN coverage -- check_wellness treats that as "not vacant".
            self._present.discard(room)
            self._present_since.pop(room, None)
            self._linger_alerted.discard(room)
            return
        self._offline.discard(entity)

        now = self._clock()
        self._last_activity = now
        if state == "on":
            self._present.add(room)
            self._present_since.setdefault(room, now)
            self._no_activity_alerted = False
            if self.control_lights:
                await ha.call_service("light", "turn_on", {"entity_id": f"light.{room}"})
        else:  # cleared
            self._present.discard(room)
            self._present_since.pop(room, None)
            self._linger_alerted.discard(room)
            if self.control_lights:
                await ha.call_service("light", "turn_off", {"entity_id": f"light.{room}"})

    async def check_wellness(self, ha, now: float | None = None) -> None:
        now = now if now is not None else self._clock()

        # No presence anywhere for too long. An offline room is UNKNOWN coverage,
        # not confirmed vacancy -- never declare the house quiet while blind in any
        # room (the presence_offline alert already flags the gap to fix).
        if (not self._present and not self._offline and not self._no_activity_alerted
                and now - self._last_activity >= self.no_activity_seconds):
            self._no_activity_alerted = True
            hours = (now - self._last_activity) / 3600
            await self._alert(ha, "critical", "no_activity",
                              f"No presence detected anywhere for {hours:.1f} h -- "
                              f"wellness check recommended.")

        # Prolonged presence in a concern room (possible fall).
        for room in self.concern_rooms & self._present:
            since = self._present_since.get(room, now)
            if now - since >= self.linger_seconds and room not in self._linger_alerted:
                self._linger_alerted.add(room)
                mins = (now - since) / 60
                await self._alert(ha, "warning", "prolonged_presence",
                                  f"Continuous presence in {room} for {mins:.0f} min -- "
                                  f"check on the occupant.")


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = PresenceMonitor()

    async def poller():
        while True:
            await asyncio.sleep(60)
            await monitor.check_wellness(ha)

    task = asyncio.create_task(poller())
    log.info("Watching presence; concern rooms=%s", sorted(monitor.concern_rooms))
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        task.cancel()
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
