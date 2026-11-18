"""
Highline Tech -- Aqara door/window contact monitor
==================================================
Aqara MCCGQ11LM contact sensors (one per monitored opening) join ZHA and expose
`binary_sensor.<name>` (device_class door/window, on = open) plus a battery
sensor. This drives the "is the house buttoned up?" logic:

  * opening left open    -- open for > N minutes (security + heat loss)
  * open while heating   -- an opening is open while the thermostat is heating
                            (reads the climate entity's hvac_action from HA;
                            ties into devices/honeywell-t6-thermostat)
  * sensor offline       -- state goes 'unavailable' (Aqara mesh drop-off); a
                            contact stuck "closed" on a dead cell is a silent gap
  * low battery          -- CR1632 getting low

The open-too-long timer uses an injectable clock so it is deterministic under
test; in production run() polls it on an interval.

Not every binary_sensor with a door/window device_class is a real contact: a
Schlage BE469ZP exposes its own door-position sensor, which depends on strike
alignment and can report OPEN permanently. Pass `exclude` (or OPENING_EXCLUDE)
to keep those out.

Entities (ZHA, each assigned to its Area):
    binary_sensor.front_door        device_class door, on = open
    binary_sensor.kitchen_window    device_class window, on = open
    sensor.<name>_battery           device_class battery, %
Read for the heating cross-check (Z-Wave JS):
    climate.<area>                  attribute hvac_action == 'heating'
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

log = logging.getLogger("aqara-doorwindow")

OPEN_WARN_SECONDS = float(os.environ.get("OPENING_WARN_SECONDS", "600"))   # 10 min
LOW_BATTERY_PCT = float(os.environ.get("OPENING_LOW_BATTERY_PCT", "15"))
CLIMATE_ENTITY = os.environ.get("OPENING_CLIMATE_ENTITY", "climate.living_room")

# Entities to ignore even though they look like openings. Comma-separated.
EXCLUDE = {e.strip() for e in os.environ.get("OPENING_EXCLUDE", "").split(",") if e.strip()}

_OPENING_CLASSES = {"door", "window", "opening", "garage_door"}
_UNKNOWN = (None, "unknown", "unavailable")


def is_opening(entity_id: str, attrs: dict) -> bool:
    return entity_id.startswith("binary_sensor.") and (
        attrs.get("device_class") in _OPENING_CLASSES
        or entity_id.endswith(("_door", "_window"))
    )


class DoorWindowMonitor:
    def __init__(self, climate_entity: str = CLIMATE_ENTITY,
                 warn_seconds: float = OPEN_WARN_SECONDS,
                 exclude: list[str] | set[str] | None = None):
        self.climate_entity = climate_entity
        self.warn_seconds = warn_seconds
        # Entities that look like openings but must not be monitored.
        #
        # Discovery is by device_class, which is right for real contacts and
        # wrong for locks that ship their own door-position sensor. A Schlage
        # BE469ZP exposes binary_sensor.<lock>_current_status_of_the_door with
        # device_class "door"; it depends on strike alignment and reported OPEN
        # continuously on a shut door (2026-09-01), on a door that already had a
        # real magnetic contact. Adopted unfiltered it raises opening_left_open
        # forever, which is the false positive that teaches people to ignore
        # alerts. Disabling the entity in HA also works, but it has to be
        # remembered at every install; this does not.
        self.exclude = set(exclude) if exclude else set(EXCLUDE)
        self.alerts: list[dict] = []
        self._open_since: dict[str, float] = {}
        self._open_alerted: set[str] = set()
        self._offline: set[str] = set()
        self._low_battery: set[str] = set()
        self._clock = time.monotonic   # injectable for tests

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Opening")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})

        # Checked before anything else, including the battery branch: an excluded
        # entity should be invisible to this monitor, not merely un-alerted.
        if entity in self.exclude:
            return

        if is_opening(entity, attrs):
            await self._handle_opening(ha, entity, state, attrs)
        elif attrs.get("device_class") == "battery" or entity.endswith("_battery"):
            await self._handle_battery(ha, entity, state, attrs)

    async def _handle_opening(self, ha, entity, state, attrs) -> None:
        where = attrs.get("friendly_name", entity)
        if state in _UNKNOWN:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "contact_offline",
                                  f"{where} contact is unavailable -- check the sensor "
                                  f"(dead cell reads as a permanently closed/open gap).")
            # A dead contact's true open/closed state is unknown -- stop the
            # open-too-long timer so check_timeouts cannot fire opening_left_open
            # for a sensor that is no longer reporting.
            self._open_since.pop(entity, None)
            self._open_alerted.discard(entity)
            return
        if entity in self._offline:
            self._offline.discard(entity)

        if state == "on":
            self._open_since[entity] = self._clock()
            self._open_alerted.discard(entity)
            log.info("%s opened", where)
            await self._check_heating(ha, where)
        else:  # closed
            self._open_since.pop(entity, None)
            self._open_alerted.discard(entity)
            log.info("%s closed", where)

    async def _check_heating(self, ha, where) -> None:
        climate = await ha.get_state(self.climate_entity)
        if climate and climate.get("attributes", {}).get("hvac_action") == "heating":
            await self._alert(ha, "info", "open_while_heating",
                              f"{where} is open while the furnace is running -- heat loss.")

    async def _handle_battery(self, ha, entity, state, attrs) -> None:
        if state in _UNKNOWN:
            return
        level = float(state)
        where = attrs.get("friendly_name", entity)
        if level <= LOW_BATTERY_PCT and entity not in self._low_battery:
            self._low_battery.add(entity)
            await self._alert(ha, "warning", "contact_low_battery",
                              f"{where} battery at {level:.0f}% -- replace the CR1632.")
        elif level > LOW_BATTERY_PCT:
            self._low_battery.discard(entity)

    async def check_timeouts(self, ha, now: float | None = None) -> None:
        """Alert on any opening that has been open longer than the threshold."""
        now = now if now is not None else self._clock()
        for entity, opened_at in list(self._open_since.items()):
            if now - opened_at >= self.warn_seconds and entity not in self._open_alerted:
                self._open_alerted.add(entity)
                state = await ha.get_state(entity)
                where = (state or {}).get("attributes", {}).get("friendly_name", entity)
                mins = (now - opened_at) / 60
                await self._alert(ha, "warning", "opening_left_open",
                                  f"{where} has been open for {mins:.0f} min.")


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = DoorWindowMonitor()

    async def timeout_poller():
        while True:
            await asyncio.sleep(30)
            await monitor.check_timeouts(ha)

    poller = asyncio.create_task(timeout_poller())
    log.info("Watching openings; heat cross-check against %s", monitor.climate_entity)
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        poller.cancel()
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
