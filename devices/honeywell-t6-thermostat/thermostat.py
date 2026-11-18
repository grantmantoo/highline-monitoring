"""
Highline Tech -- Honeywell T6 Pro thermostat monitor + safe-minimum hold
=======================================================================
The T6 Pro joins Z-Wave JS and exposes a single `climate.<name>` entity whose
state is the hvac_mode (heat/cool/auto/off) and whose attributes carry
current_temperature, temperature (target setpoint), and hvac_action
(heating/idle). This adds the elder-care safety layer on top:

  * freeze protection -- if the room sits at/below a safe minimum past a grace
    window, ACT: force heat mode and restore a safe setpoint, then alert. A
    heating failure or an accidental "off" becomes a self-correcting event.
  * too hot          -- alert if it climbs past a safe maximum
  * setpoint tamper  -- alert if the target setpoint is changed to something
    outside a sane band (someone fat-fingered the dial / a bad schedule)
  * thermostat offline -- 'unavailable' means we have lost HVAC visibility and
    control; alert

The grace timer uses an injectable clock so it is deterministic under test; run()
also polls it so a temperature that simply stays cold (no new event) still trips.

Entity (Z-Wave JS, assigned to the main living-space Area):
    climate.<name>   state = hvac_mode; attrs: current_temperature, temperature,
                     hvac_action, fan_mode
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

log = logging.getLogger("honeywell-t6")

THERMOSTAT = os.environ.get("THERMOSTAT_ENTITY", "climate.living_room")
SAFE_MIN_C = float(os.environ.get("THERMOSTAT_SAFE_MIN_C", "15.0"))   # ~59 F
SAFE_HOLD_C = float(os.environ.get("THERMOSTAT_SAFE_HOLD_C", "18.0"))  # restore target
SAFE_MAX_C = float(os.environ.get("THERMOSTAT_SAFE_MAX_C", "30.0"))
COLD_GRACE_SECONDS = float(os.environ.get("THERMOSTAT_COLD_GRACE_SECONDS", str(15 * 60)))
SETPOINT_MIN_C = float(os.environ.get("THERMOSTAT_SETPOINT_MIN_C", "10.0"))
SETPOINT_MAX_C = float(os.environ.get("THERMOSTAT_SETPOINT_MAX_C", "29.0"))

_UNKNOWN = (None, "unknown", "unavailable")


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ThermostatMonitor:
    def __init__(self, entity: str = THERMOSTAT):
        self.entity = entity
        self.alerts: list[dict] = []
        self._mode = None
        self._current = None
        self._target = None
        self._prev_target = None
        self._below_since: float | None = None
        self._cold_alerted = False
        self._hot_alerted = False
        self._offline = False
        self._clock = time.monotonic   # injectable for tests

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Thermostat")

    async def handle_event(self, event: dict, ha) -> None:
        if event["entity_id"] != self.entity:
            return
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})

        if state in _UNKNOWN:
            if not self._offline:
                self._offline = True
                await self._alert(ha, "warning", "thermostat_offline",
                                  f"{self.entity} is unavailable -- lost HVAC visibility "
                                  f"and control. Check the C-wire / Z-Wave link.")
            return
        self._offline = False

        self._mode = state
        self._current = _as_float(attrs.get("current_temperature"))
        new_target = _as_float(attrs.get("temperature"))

        # Setpoint tamper: alert when the target moves outside the sane band.
        if new_target is not None and new_target != self._target:
            if (self._prev_target is not None
                    and (new_target < SETPOINT_MIN_C or new_target > SETPOINT_MAX_C)):
                await self._alert(ha, "warning", "setpoint_tamper",
                                  f"Setpoint changed to {new_target:.0f} C -- outside the "
                                  f"{SETPOINT_MIN_C:.0f}-{SETPOINT_MAX_C:.0f} C safe band.")
            self._prev_target = new_target
        self._target = new_target

        await self._evaluate(ha, self._clock())

    async def _evaluate(self, ha, now: float) -> None:
        cur = self._current
        if cur is None:
            return

        # Cold: hold a safe minimum.
        if cur <= SAFE_MIN_C:
            if self._below_since is None:
                self._below_since = now
            if now - self._below_since >= COLD_GRACE_SECONDS and not self._cold_alerted:
                self._cold_alerted = True
                mins = (now - self._below_since) / 60
                await self._alert(ha, "critical", "too_cold",
                                  f"{self.entity} at {cur:.1f} C for {mins:.0f} min "
                                  f"(<= {SAFE_MIN_C:.0f} C) -- possible heating failure.")
                await self._freeze_protect(ha)
        else:
            self._below_since = None
            if cur >= SAFE_MIN_C + 1.0:
                self._cold_alerted = False

        # Hot.
        if cur >= SAFE_MAX_C and not self._hot_alerted:
            self._hot_alerted = True
            await self._alert(ha, "warning", "too_hot",
                              f"{self.entity} at {cur:.1f} C (>= {SAFE_MAX_C:.0f} C).")
        elif cur <= SAFE_MAX_C - 1.0:
            self._hot_alerted = False

    async def _freeze_protect(self, ha) -> None:
        """Force heat at a safe setpoint if the thermostat is off or set too low."""
        if self._mode == "off" or self._target is None or self._target < SAFE_HOLD_C:
            await ha.call_service("climate", "set_hvac_mode",
                                  {"entity_id": self.entity, "hvac_mode": "heat"})
            await ha.call_service("climate", "set_temperature",
                                  {"entity_id": self.entity, "temperature": SAFE_HOLD_C})
            await self._alert(ha, "info", "freeze_protect_engaged",
                              f"Forced heat and restored setpoint to {SAFE_HOLD_C:.0f} C.")

    async def check_timeouts(self, ha, now: float | None = None) -> None:
        await self._evaluate(ha, now if now is not None else self._clock())


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = ThermostatMonitor()

    async def poller():
        while True:
            await asyncio.sleep(60)
            await monitor.check_timeouts(ha)

    task = asyncio.create_task(poller())
    log.info("Watching %s (safe min %.0f C)", monitor.entity, SAFE_MIN_C)
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        task.cancel()
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
