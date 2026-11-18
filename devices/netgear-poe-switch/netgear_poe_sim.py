"""
Highline Tech -- NETGEAR PoE switch / camera-reachability simulator
==================================================================
Emits camera availability events that stand in for switch/PoE health: one camera
dropping, all cameras dropping together (switch/uplink/power), and a single camera
flapping (reboot loop from an overtaxed power budget).

    python netgear_poe_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# 2x bullet + 2x dome, all PoE off the GS108LP.
CAMERAS = {
    "camera.front_door": "Front Door (bullet)",
    "camera.driveway": "Driveway (bullet)",
    "camera.porch": "Porch (dome)",
    "camera.back_yard": "Back Yard (dome)",
}


def build_sim() -> SimulatedHA:
    ha = SimulatedHA()
    for entity, name in CAMERAS.items():
        ha.seed(entity, "idle", {"friendly_name": name})
    return ha


async def set_reachable(ha: SimulatedHA, entity: str, reachable: bool) -> None:
    name = CAMERAS.get(entity, entity)
    await ha.set_state(entity, "idle" if reachable else "unavailable", {"friendly_name": name})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from poe_health import PoEHealthMonitor

    ha = build_sim()
    m = PoEHealthMonitor(roster=set(CAMERAS))
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("One camera drops (its run/port):")
    await set_reachable(ha, "camera.porch", False)
    await set_reachable(ha, "camera.porch", True)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nAll four cameras drop at once (switch/uplink/power):")
    ha2 = build_sim()
    m2 = PoEHealthMonitor(roster=set(CAMERAS))
    ha2.add_listener(lambda ev: m2.handle_event(ev, ha2))
    for e in CAMERAS:
        await set_reachable(ha2, e, False)
    print(f"  alerts: {[a['code'] for a in m2.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
