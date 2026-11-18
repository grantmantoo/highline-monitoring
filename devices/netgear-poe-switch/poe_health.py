"""
Highline Tech -- NETGEAR GS108LP PoE switch health (inferred downstream)
======================================================================
The GS108LP is unmanaged: no entity, no SNMP, no per-port telemetry. Per the
README the only way to watch it is to watch what hangs off it -- the PoE cameras
go 'unavailable' if power or the uplink drops. This infers switch/PoE health from
the camera entities in Home Assistant:

  * device unreachable   -- one camera down: likely that camera's cable / PoE port
  * switch or uplink down -- ALL cameras down at once: the switch, its uplink, or
    power lost (not four cameras failing independently). CRITICAL.
  * unstable PoE          -- a camera flapping (repeated reboots) in a short window:
    the README's "cameras randomly reboot -> suspect the power budget" first.

The flap window uses an injectable clock so it is deterministic under test.

Entities watched (Reolink integration):
    camera.<name>          state 'unavailable' = camera off the network
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

log = logging.getLogger("poe-health")

POE_PREFIX = os.environ.get("POE_ENTITY_PREFIX", "camera.")
FLAP_WINDOW_SECONDS = float(os.environ.get("POE_FLAP_WINDOW_SECONDS", str(10 * 60)))
FLAP_THRESHOLD = int(os.environ.get("POE_FLAP_THRESHOLD", "3"))

_UNAVAILABLE = (None, "unknown", "unavailable")


class PoEHealthMonitor:
    def __init__(self, roster=None, prefix: str = POE_PREFIX,
                 flap_threshold: int = FLAP_THRESHOLD, flap_window: float = FLAP_WINDOW_SECONDS):
        self.prefix = prefix
        self.flap_threshold = flap_threshold
        self.flap_window = flap_window
        self.alerts: list[dict] = []
        # Known PoE roster up front (so "all down" is accurate). Falls back to
        # learning entities from events when not supplied.
        self._roster: set[str] = set(roster) if roster else set()
        self._offline: set[str] = set()
        self._reboots: dict[str, list[float]] = {}
        self._switch_alerted = False
        self._clock = time.monotonic   # injectable for tests

    async def _alert(self, ha, level: str, code: str, message: str) -> None:
        await emit_alert(self, ha, level, code, message, title="PoE switch")

    async def handle_event(self, event: dict, ha) -> None:
        entity = event["entity_id"]
        if not entity.startswith(self.prefix):
            return
        self._roster.add(entity)
        new = event.get("new_state") or {}
        state = new.get("state")
        where = new.get("attributes", {}).get("friendly_name", entity)

        if state in _UNAVAILABLE:
            if entity not in self._offline:
                self._offline.add(entity)
                await self._alert(ha, "warning", "device_unreachable",
                                  f"{where} is unreachable -- check its Cat 6 run / PoE port.")
                await self._check_switch(ha)
        else:
            if entity in self._offline:
                self._offline.discard(entity)
                await self._record_reboot(ha, entity, where)
            if len(self._offline) < len(self._roster):
                self._switch_alerted = False

    async def _check_switch(self, ha) -> None:
        if (len(self._roster) >= 2 and self._offline == self._roster
                and not self._switch_alerted):
            self._switch_alerted = True
            await self._alert(
                ha, "critical", "switch_or_uplink_down",
                f"All {len(self._roster)} PoE cameras went unavailable at once -- "
                f"suspect the GS108LP, its uplink, or lost power (not the cameras).",
            )

    async def _record_reboot(self, ha, entity: str, where: str) -> None:
        now = self._clock()
        history = self._reboots.setdefault(entity, [])
        history.append(now)
        # Keep only recoveries inside the flap window.
        self._reboots[entity] = [t for t in history if now - t <= self.flap_window]
        if len(self._reboots[entity]) >= self.flap_threshold:
            self._reboots[entity] = []   # reset so we alert once per burst
            await self._alert(ha, "warning", "unstable_poe",
                              f"{where} has rebooted {self.flap_threshold}+ times quickly "
                              f"-- suspect the GS108LP ~60W power budget.")


async def run(ha=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    own = ha is None
    ha = ha or HAClient()
    monitor = PoEHealthMonitor()
    log.info("Inferring PoE health from '%s*' entities", monitor.prefix)
    try:
        async for event in ha.events():
            await monitor.handle_event(event, ha)
    finally:
        if own:
            await ha.close()


if __name__ == "__main__":
    asyncio.run(run())
