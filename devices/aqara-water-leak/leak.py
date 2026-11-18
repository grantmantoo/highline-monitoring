"""
Highline Tech -- Aqara water leak monitor + auto-shutoff automation
==================================================================
The trigger half of the auto water-shutoff pair. Aqara SJCGQ11LM leak sensors
join ZHA and expose a moisture `binary_sensor.<location>_water` plus a battery
sensor. This module is the cross-radio automation the READMEs describe:

    any binary_sensor.*_water -> 'on'  ==>  close the Zooz ZAC36 main valve
                                            + raise a critical alert
    any leak sensor battery <= threshold ==> low-battery alert
                                            (a dead leak sensor is worse than none)

Zigbee sensor in, Z-Wave valve out, both owned by Home Assistant. Reopen is left
MANUAL on purpose (a human verifies the leak is resolved first), so a leak that
clears does not auto-reopen the valve.

The valve's own local logic (its onboard probe, freeze watch, close verification)
lives in devices/zooz-valve-actuator/valve.py and runs alongside this -- see
test_chain.py for the two exercised together.

Entities (ZHA, one sensor per water-risk point, assigned to its Area):
    binary_sensor.water_heater_water     device_class moisture, on = wet
    binary_sensor.kitchen_sink_water
    binary_sensor.washing_machine_water
    binary_sensor.bathroom_vanity_water
    sensor.<location>_leak_battery        battery %, ZHA power-config cluster
Target valve (Z-Wave JS):
    switch.water_main_valve               off = CLOSED

Run against a live HA:
    HA_URL=http://homeassistant.local:8123 HA_TOKEN=... python leak.py
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

log = logging.getLogger("aqara-leak")

VALVE_SWITCH = os.environ.get("VALVE_SWITCH", "switch.water_main_valve")
LOW_BATTERY_PCT = float(os.environ.get("LEAK_LOW_BATTERY_PCT", "15"))


def is_leak_sensor(entity_id: str, attrs: dict) -> bool:
    return entity_id.startswith("binary_sensor.") and (
        attrs.get("device_class") == "moisture" or entity_id.endswith("_water")
    )


def is_battery_sensor(entity_id: str, attrs: dict) -> bool:
    return entity_id.startswith("sensor.") and (
        attrs.get("device_class") == "battery" or entity_id.endswith("_battery")
    )


class LeakMonitor:
    """Watches every leak sensor and drives the main-valve shutoff."""

    def __init__(self, valve_switch: str = VALVE_SWITCH, low_battery_pct: float = LOW_BATTERY_PCT):
        self.valve_switch = valve_switch
        self.low_battery_pct = low_battery_pct
        self.alerts: list[dict] = []
        self._active_leaks: set[str] = set()
        self._low_battery: set[str] = set()

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Water leak")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})

        if is_leak_sensor(entity, attrs):
            await self._handle_leak(ha, entity, state, attrs)
        elif is_battery_sensor(entity, attrs):
            await self._handle_battery(ha, entity, state, attrs)

    async def _handle_leak(self, ha, entity: str, state: str, attrs: dict) -> None:
        where = attrs.get("friendly_name", entity)
        if state == "on" and entity not in self._active_leaks:
            self._active_leaks.add(entity)
            # The automation that matters: shut the main. Delivering the leak alert
            # matters MORE than the close succeeding, so isolate the service call --
            # a raised/failed close must never suppress the alert below.
            close_error = None
            try:
                await ha.call_service("switch", "turn_off", {"entity_id": self.valve_switch})
            except Exception as exc:  # noqa: BLE001 -- the leak alert must still go out
                close_error = exc
                log.error("Leak shutoff command to %s failed: %s", self.valve_switch, exc)
            await self._alert(ha, "critical", "leak_detected",
                              f"Water detected at {where} -- closing main valve.")
            if close_error is not None:
                await self._alert(ha, "critical", "valve_shutoff_failed",
                                  f"Leak at {where}: the shutoff command to "
                                  f"{self.valve_switch} errored ({close_error}) -- "
                                  f"close the water main by hand NOW.")
            else:
                await self._verify_closed(ha, where)
        elif state == "off" and entity in self._active_leaks:
            self._active_leaks.discard(entity)
            # Reopen is manual on purpose -- do not auto-reopen the valve.
            log.info("Leak at %s cleared. Valve stays CLOSED until reopened by hand.", where)

    async def _verify_closed(self, ha, where: str) -> None:
        """Read the valve back: a commanded close that did not seat (motor stall) is
        the worst failure on the main, so alert -- mirrors ValveController.close()."""
        valve = await ha.get_state(self.valve_switch)
        if valve is None or valve["state"] != "off":
            actual = valve["state"] if valve else "unknown"
            await self._alert(ha, "critical", "valve_close_failed",
                              f"Leak at {where}: commanded {self.valve_switch} CLOSED "
                              f"but it reads '{actual}' -- check for a motor stall.")

    async def _handle_battery(self, ha, entity: str, state: str, attrs: dict) -> None:
        try:
            level = float(state)
        except (TypeError, ValueError):
            return
        if level <= self.low_battery_pct and entity not in self._low_battery:
            self._low_battery.add(entity)
            where = attrs.get("friendly_name", entity)
            await self._alert(ha, "warning", "leak_sensor_low_battery",
                              f"{where} battery at {level:.0f}% -- replace the CR2032 "
                              f"so the leak sensor isn't silently dead.")
        elif level > self.low_battery_pct:
            self._low_battery.discard(entity)


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = LeakMonitor()
    log.info("Watching leak sensors -> %s", monitor.valve_switch)
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
