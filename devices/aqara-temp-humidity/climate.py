"""
Highline Tech -- Aqara temp/humidity room-climate monitor
========================================================
Aqara WSDCGQ11LM sensors (one per room) join ZHA and expose temperature,
humidity, and pressure entities plus a battery sensor. For the elder-care use
case an abnormally cold or hot room is a safety signal (heating failure, a
window left open, a heat event) -- not just a comfort metric -- so this watches
every room sensor and alerts on:

  * cold room      -- temp <= low threshold (heating failure / open window)
  * hot room       -- temp >= high threshold
  * damp room      -- humidity >= high threshold (mold / condensation risk)
  * sensor offline -- state goes 'unavailable' (the Aqara picky-router drop-off)
  * low battery    -- a dead CR2032 is a silent failure

All thresholds are hysteretic (alert on cross-in, clear on cross-out) and tracked
per entity, so one room hovering at a threshold does not spam. Thresholds are in
degrees C (the sim drives C); if HA is configured for F, set the *_F overrides.

Entities (ZHA, one device per room, assigned to its Area):
    sensor.<room>_temperature   device_class temperature
    sensor.<room>_humidity       device_class humidity, %
    sensor.<room>_pressure       device_class pressure, hPa (tracked, no alert)
    sensor.<room>_battery        device_class battery, %

Run against a live HA:
    HA_URL=... HA_TOKEN=... python climate.py
"""

from __future__ import annotations

import asyncio
import logging
import os

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import HAClient
from notifier import emit_alert

log = logging.getLogger("aqara-climate")

TEMP_LOW_C = float(os.environ.get("ROOM_TEMP_LOW_C", "12.0"))
TEMP_LOW_CLEAR_C = float(os.environ.get("ROOM_TEMP_LOW_CLEAR_C", "14.0"))
TEMP_HIGH_C = float(os.environ.get("ROOM_TEMP_HIGH_C", "30.0"))
TEMP_HIGH_CLEAR_C = float(os.environ.get("ROOM_TEMP_HIGH_CLEAR_C", "28.0"))
HUMIDITY_HIGH = float(os.environ.get("ROOM_HUMIDITY_HIGH", "70.0"))
HUMIDITY_CLEAR = float(os.environ.get("ROOM_HUMIDITY_CLEAR", "65.0"))
LOW_BATTERY_PCT = float(os.environ.get("ROOM_LOW_BATTERY_PCT", "15"))

_UNKNOWN = (None, "unknown", "unavailable")


def room_of(entity_id: str) -> str:
    """'sensor.bedroom_temperature' -> 'bedroom' (the room a sensor belongs to)."""
    name = entity_id.split(".", 1)[-1]
    for suffix in ("_temperature", "_humidity", "_pressure", "_battery"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


class ClimateMonitor:
    def __init__(self, rooms=None):
        # Optional roster of room names (e.g. ["bedroom", "living_room"]). When set,
        # only those rooms' sensors are watched, so a non-room temperature entity --
        # like the water main's own sensor.water_main_valve_temperature -- is NOT
        # misread as a freezing "room". None/empty = watch every room sensor (the
        # standalone default, unchanged).
        self.rooms = set(rooms) if rooms else None
        self.alerts: list[dict] = []
        self._cold: set[str] = set()
        self._hot: set[str] = set()
        self._humid: set[str] = set()
        self._offline: set[str] = set()
        self._low_battery: set[str] = set()

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Room climate")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})
        dc = attrs.get("device_class")

        is_temp = dc == "temperature" or entity.endswith("_temperature")
        is_humidity = dc == "humidity" or entity.endswith("_humidity")
        is_battery = dc == "battery" or entity.endswith("_battery")
        if not (is_temp or is_humidity or is_battery):
            return   # pressure (and anything else) is recorded by HA history only.
        if self.rooms is not None and room_of(entity) not in self.rooms:
            return   # not a watched room sensor (e.g. the water-main valve temp).

        if is_temp:
            await self._temperature(ha, entity, state, attrs)
        elif is_humidity:
            await self._humidity(ha, entity, state, attrs)
        elif is_battery:
            await self._battery(ha, entity, state, attrs)

    async def _temperature(self, ha, entity, state, attrs) -> None:
        where = attrs.get("friendly_name", entity)
        if state in _UNKNOWN:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "sensor_offline",
                                  f"{where} is unavailable -- sensor may have dropped "
                                  f"off the Zigbee mesh (re-pair nearer the coordinator).")
            return
        if entity in self._offline:
            self._offline.discard(entity)
            log.info("%s back online", where)

        try:
            temp = float(state)
        except (TypeError, ValueError):
            return   # a garbage reading must not crash the shared event loop
        if temp <= TEMP_LOW_C and entity not in self._cold:
            self._cold.add(entity)
            await self._alert(ha, "warning", "room_cold",
                              f"{where} is {temp:.1f} C (<= {TEMP_LOW_C:.0f} C) -- "
                              f"possible heating failure or open window.")
        elif temp >= TEMP_LOW_CLEAR_C:
            self._cold.discard(entity)

        if temp >= TEMP_HIGH_C and entity not in self._hot:
            self._hot.add(entity)
            await self._alert(ha, "warning", "room_hot",
                              f"{where} is {temp:.1f} C (>= {TEMP_HIGH_C:.0f} C).")
        elif temp <= TEMP_HIGH_CLEAR_C:
            self._hot.discard(entity)

    async def _humidity(self, ha, entity, state, attrs) -> None:
        if state in _UNKNOWN:
            return
        where = attrs.get("friendly_name", entity)
        try:
            rh = float(state)
        except (TypeError, ValueError):
            return
        if rh >= HUMIDITY_HIGH and entity not in self._humid:
            self._humid.add(entity)
            await self._alert(ha, "info", "room_humid",
                              f"{where} humidity {rh:.0f}% (>= {HUMIDITY_HIGH:.0f}%) -- "
                              f"watch for condensation / mold.")
        elif rh <= HUMIDITY_CLEAR:
            self._humid.discard(entity)

    async def _battery(self, ha, entity, state, attrs) -> None:
        if state in _UNKNOWN:
            return
        try:
            level = float(state)
        except (TypeError, ValueError):
            return
        where = attrs.get("friendly_name", entity)
        if level <= LOW_BATTERY_PCT and entity not in self._low_battery:
            self._low_battery.add(entity)
            await self._alert(ha, "warning", "sensor_low_battery",
                              f"{where} battery at {level:.0f}% -- replace the CR2032.")
        elif level > LOW_BATTERY_PCT:
            self._low_battery.discard(entity)


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = ClimateMonitor()
    log.info("Watching room climate sensors")
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
