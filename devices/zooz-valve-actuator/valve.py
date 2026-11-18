"""
Highline Tech -- Zooz ZAC36 Titan valve monitor + control
=========================================================
The action half of the auto water-shutoff pair. This module owns the valve
device's *local* logic on top of Home Assistant's Z-Wave JS entities:

  * close/open the valve (switch.turn_off / switch.turn_on on the valve switch)
  * verify a commanded close actually seated -- a motor stall that leaves the
    valve open is the worst failure, so we alert if state does not reach closed
  * act on the ZAC36's OWN attached leak probe (a local failsafe that works even
    if the Zigbee mesh / HA automation is down)
  * freeze awareness: the valve reports an onboard temperature; alert when it
    drops toward freezing so a pipe burst at the main is caught early

The cross-radio "leak sensor -> close this valve" automation lives with the
trigger device (devices/aqara-water-leak), per the wiring in the READMEs. Here
we expose close()/handle_event() so that chain -- and the valve's own probe --
both drive the same real control path.

Entities (Z-Wave JS, ZAC36 assigned to Area "Water Main"):
    switch.water_main_valve              on = OPEN (water flowing), off = CLOSED
    sensor.water_main_valve_temperature  onboard temp, degrees C
    binary_sensor.water_main_valve_leak  ZAC36 attached probe, on = wet

Run against a live HA:
    HA_URL=http://homeassistant.local:8123 HA_TOKEN=... python valve.py
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

log = logging.getLogger("zooz-valve")

VALVE_SWITCH = os.environ.get("VALVE_SWITCH", "switch.water_main_valve")
VALVE_TEMP = os.environ.get("VALVE_TEMP", "sensor.water_main_valve_temperature")
VALVE_LEAK = os.environ.get("VALVE_LEAK", "binary_sensor.water_main_valve_leak")

# ZAC36 reports degrees C. Pipes are at risk well above 0; alert with margin and
# clear with hysteresis so a sensor hovering at the threshold does not spam.
FREEZE_ALERT_C = float(os.environ.get("VALVE_FREEZE_ALERT_C", "4.0"))   # ~39 F
FREEZE_CLEAR_C = float(os.environ.get("VALVE_FREEZE_CLEAR_C", "6.0"))   # ~43 F


class ValveController:
    """Local control + monitoring for one ZAC36 valve."""

    def __init__(self, switch=VALVE_SWITCH, temp=VALVE_TEMP, leak=VALVE_LEAK):
        self.switch = switch
        self.temp = temp
        self.leak = leak
        self.alerts: list[dict] = []
        self._freeze_active = False

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Water main")

    # -- control -----------------------------------------------------------
    async def close(self, ha, reason: str) -> bool:
        """Command the valve shut and verify it reached the closed state."""
        log.info("Closing water main valve (%s)", reason)
        await ha.call_service("switch", "turn_off", {"entity_id": self.switch})
        state = await ha.get_state(self.switch)
        seated = state is not None and state["state"] == "off"
        if not seated:
            await self._alert(
                ha, "critical", "valve_close_failed",
                f"Commanded CLOSE ({reason}) but {self.switch} is "
                f"'{state['state'] if state else 'unknown'}' -- check for motor stall.",
            )
        return seated

    async def open(self, ha, reason: str = "manual") -> None:
        log.info("Opening water main valve (%s)", reason)
        await ha.call_service("switch", "turn_on", {"entity_id": self.switch})

    # -- event handling ----------------------------------------------------
    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")

        if entity == self.leak and state == "on":
            # Local failsafe: the valve's own probe is wet. Shut immediately,
            # independent of the Zigbee leak sensors / HA automation.
            await self._alert(ha, "critical", "valve_probe_leak",
                              "ZAC36 onboard leak probe is wet -- closing main.")
            await self.close(ha, "onboard probe")

        elif entity == self.temp and state not in (None, "unknown", "unavailable"):
            try:
                temp_c = float(state)
            except (TypeError, ValueError):
                return   # a garbage reading must not crash the shared event loop
            await self._check_freeze(ha, temp_c)

    async def _check_freeze(self, ha, temp_c: float) -> None:
        if not self._freeze_active and temp_c <= FREEZE_ALERT_C:
            self._freeze_active = True
            await self._alert(
                ha, "warning", "valve_freeze_risk",
                f"Temperature at the water main is {temp_c:.1f} C "
                f"(<= {FREEZE_ALERT_C:.0f} C) -- pipe freeze risk.",
            )
        elif self._freeze_active and temp_c >= FREEZE_CLEAR_C:
            self._freeze_active = False
            log.info("Water main temperature recovered to %.1f C", temp_c)


async def run(ha=None) -> None:
    """Production entry point: stream live events into the controller."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    controller = ValveController()
    log.info("Watching %s / %s / %s", controller.switch, controller.temp, controller.leak)
    try:
        async for event in ha.events():
            await controller.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
