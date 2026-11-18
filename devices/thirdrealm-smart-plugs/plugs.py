"""
Highline Tech -- THIRDREALITY smart-plug monitor (energy + activity)
===================================================================
Gen3 mains plugs join ZHA as switchable, energy-metering outlets (and as mesh
routers). This turns their per-outlet power readings into signals:

  * appliance used   -- power crosses up from ~0; an activity-of-daily-living
    signal (the coffee maker each morning confirms routine). Logged, not alerted.
  * high load left on -- a plug drawing a heater-sized load continuously past a
    grace window (space heater left running); SAFETY alert.
  * routine missed   -- a routine appliance not used in too long; WELLNESS alert
    (e.g. the morning coffee never got made).
  * plug offline     -- the outlet's power sensor goes 'unavailable'; since these
    are mesh routers, that can also mean a dropped Zigbee path.

Timers use an injectable clock so they are deterministic under test; run() polls
them on an interval in production.

Entities (ZHA, one device per plug, named for its load):
    switch.<name>          on/off control
    sensor.<name>_power    instantaneous W  (drives the logic here)
    sensor.<name>_energy   kWh total        (tracked by HA history)
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

log = logging.getLogger("thirdrealm-plugs")

ON_THRESHOLD_W = float(os.environ.get("PLUG_ON_THRESHOLD_W", "5.0"))
HIGH_LOAD_W = float(os.environ.get("PLUG_HIGH_LOAD_W", "800.0"))
HIGH_LOAD_MAX_SECONDS = float(os.environ.get("PLUG_HIGH_LOAD_MAX_SECONDS", str(3 * 3600)))
ROUTINE_PLUGS = set(p for p in os.environ.get("PLUG_ROUTINE", "coffee_maker").split(",") if p)
ROUTINE_MAX_SECONDS = float(os.environ.get("PLUG_ROUTINE_MAX_SECONDS", str(26 * 3600)))

_UNKNOWN = (None, "unknown", "unavailable")


def plug_of(entity_id: str) -> str:
    name = entity_id.split(".", 1)[-1]
    for suffix in ("_power", "_energy"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


class PlugMonitor:
    def __init__(self, routine_plugs=None):
        self.routine_plugs = set(routine_plugs) if routine_plugs is not None else set(ROUTINE_PLUGS)
        self.alerts: list[dict] = []
        self.activity: list[dict] = []
        self._on: set[str] = set()
        self._on_since: dict[str, float] = {}
        self._watts: dict[str, float] = {}
        self._last_used: dict[str, float] = {}
        self._high_alerted: set[str] = set()
        self._routine_alerted: set[str] = set()
        self._offline: set[str] = set()
        self._clock = time.monotonic   # injectable for tests
        self._start = self._clock()

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Smart plug")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})
        if not (entity.endswith("_power") or attrs.get("device_class") == "power"):
            return

        plug = plug_of(entity)
        where = attrs.get("friendly_name", plug)
        if state in _UNKNOWN:
            if plug not in self._offline:
                self._offline.add(plug)
                await self._alert(ha, "warning", "plug_offline",
                                  f"{where} power sensor is unavailable -- outlet may have "
                                  f"dropped off the Zigbee mesh (also a router path).")
            return
        self._offline.discard(plug)

        try:
            watts = float(state)
        except (TypeError, ValueError):
            return
        self._watts[plug] = watts
        now = self._clock()
        on = watts >= ON_THRESHOLD_W
        was_on = plug in self._on

        if on and not was_on:
            self._on.add(plug)
            self._on_since[plug] = now
            self._last_used[plug] = now
            self._high_alerted.discard(plug)
            self._routine_alerted.discard(plug)
            self.activity.append({"plug": plug, "watts": watts})
            log.info("Appliance used: %s (%.0f W)", where, watts)
        elif not on and was_on:
            self._on.discard(plug)
            self._on_since.pop(plug, None)

    async def check_timeouts(self, ha, now: float | None = None) -> None:
        now = now if now is not None else self._clock()

        # High load left on (e.g. a space heater).
        for plug in list(self._on):
            if (self._watts.get(plug, 0.0) >= HIGH_LOAD_W
                    and now - self._on_since.get(plug, now) >= HIGH_LOAD_MAX_SECONDS
                    and plug not in self._high_alerted):
                self._high_alerted.add(plug)
                hrs = (now - self._on_since[plug]) / 3600
                await self._alert(ha, "warning", "high_load_left_on",
                                  f"{plug} drawing {self._watts[plug]:.0f} W for {hrs:.1f} h "
                                  f"-- heater/large load left on?")

        # Routine appliance not used in too long (wellness).
        for plug in self.routine_plugs:
            last = self._last_used.get(plug, self._start)
            if now - last >= ROUTINE_MAX_SECONDS and plug not in self._routine_alerted:
                self._routine_alerted.add(plug)
                hrs = (now - last) / 3600
                await self._alert(ha, "warning", "routine_missed",
                                  f"{plug} has not been used in {hrs:.0f} h -- routine "
                                  f"activity check.")


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = PlugMonitor()

    async def poller():
        while True:
            await asyncio.sleep(60)
            await monitor.check_timeouts(ha)

    task = asyncio.create_task(poller())
    log.info("Watching plug power; routine=%s", sorted(monitor.routine_plugs))
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        task.cancel()
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
