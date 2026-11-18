"""
Highline Tech -- SONOFF Zigbee coordinator / mesh health monitor
===============================================================
The SONOFF dongle runs the whole Zigbee mesh; every Aqara sensor and THIRDREALITY
plug joins it. The dongle itself exposes no useful per-device alert, so this
watches the mesh as a whole from Home Assistant:

  * device dropped  -- a Zigbee entity goes 'unavailable' (one node off the mesh)
  * mesh mass outage -- several nodes go unavailable at once: that pattern points
    at the COORDINATOR, not the individual devices (USB 3.0 interference, the
    dongle reset, or HA/ZHA down). The README's #1 gotcha. CRITICAL.
  * weak link       -- a node's LQI drops below a floor (add a router / relocate)

This is the network-wide view; each sensor device still owns its own offline
alert. Mass-outage detection is what tells you to suspect the radio, not 8 sensors
all dying at once.

Entities watched (ZHA):
    <any zigbee entity>          state 'unavailable' = node off the mesh
    sensor.<device>_lqi          link quality 0-255 (ZHA diagnostic)
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

log = logging.getLogger("zigbee-health")

MASS_OUTAGE_THRESHOLD = int(os.environ.get("ZIGBEE_MASS_OUTAGE_THRESHOLD", "3"))
LOW_LQI = float(os.environ.get("ZIGBEE_LOW_LQI", "30"))
LQI_CLEAR = float(os.environ.get("ZIGBEE_LQI_CLEAR", "45"))

_ZIGBEE_PREFIXES = ("binary_sensor.", "sensor.", "switch.", "light.", "climate.")
_UNAVAILABLE = (None, "unknown", "unavailable")


class ZigbeeMeshMonitor:
    def __init__(self, mass_threshold: int = MASS_OUTAGE_THRESHOLD):
        self.mass_threshold = mass_threshold
        self.alerts: list[dict] = []
        self._offline: set[str] = set()
        self._low_lqi: set[str] = set()
        self._mass_alerted = False

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="Zigbee mesh")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        new = event.get("new_state") or {}
        state = new.get("state")
        attrs = new.get("attributes", {})

        if entity.endswith("_lqi") or attrs.get("device_class") == "signal_strength":
            await self._handle_lqi(ha, entity, state, attrs)
            return

        if not entity.startswith(_ZIGBEE_PREFIXES):
            return
        await self._handle_availability(ha, entity, state, attrs)

    async def _handle_availability(self, ha, entity, state, attrs) -> None:
        where = attrs.get("friendly_name", entity)
        if state in _UNAVAILABLE:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "device_dropped",
                                  f"{where} dropped off the Zigbee mesh.")
                await self._check_mass(ha)
        else:
            self._offline.discard(entity)
            if len(self._offline) < self.mass_threshold:
                self._mass_alerted = False

    async def _check_mass(self, ha) -> None:
        if len(self._offline) >= self.mass_threshold and not self._mass_alerted:
            self._mass_alerted = True
            await self._alert(
                ha, "critical", "mesh_mass_outage",
                f"{len(self._offline)} Zigbee nodes unavailable at once "
                f"({', '.join(sorted(self._offline))}) -- suspect the coordinator: "
                f"USB 3.0 interference, the dongle, or ZHA down (not the sensors).",
            )

    async def _handle_lqi(self, ha, entity, state, attrs) -> None:
        if state in _UNAVAILABLE:
            return
        try:
            lqi = float(state)
        except (TypeError, ValueError):
            return
        where = attrs.get("friendly_name", entity)
        if lqi < LOW_LQI and entity not in self._low_lqi:
            self._low_lqi.add(entity)
            await self._alert(ha, "warning", "weak_link",
                              f"{where} link quality LQI {lqi:.0f} (< {LOW_LQI:.0f}) -- "
                              f"add a router/plug or relocate the coordinator.")
        elif lqi >= LQI_CLEAR:
            self._low_lqi.discard(entity)


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = ZigbeeMeshMonitor()
    log.info("Watching Zigbee mesh health (mass-outage threshold %d)", monitor.mass_threshold)
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
