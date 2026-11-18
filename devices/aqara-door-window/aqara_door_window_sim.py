"""
Highline Tech -- Aqara door/window simulator
============================================
Emits realistic ZHA contact events: front-door open/close, a window left open,
a window opened while the furnace is heating, an offline drop, and battery decay.

    python aqara_door_window_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# (entity, device_class, friendly name)
OPENINGS = [
    ("binary_sensor.front_door", "door", "Front Door"),
    ("binary_sensor.kitchen_window", "window", "Kitchen Window"),
    ("binary_sensor.bedroom_window", "window", "Bedroom Window"),
]


def build_sim() -> SimulatedHA:
    """Seed every opening closed, batteries fresh, furnace idle."""
    ha = SimulatedHA()
    for entity, dc, name in OPENINGS:
        ha.seed(entity, "off", {"device_class": dc, "friendly_name": name})
        batt = entity.replace("binary_sensor.", "sensor.") + "_battery"
        ha.seed(batt, "100", {"device_class": "battery", "unit_of_measurement": "%",
                              "friendly_name": name})
    ha.seed("climate.living_room", "heat",
            {"hvac_action": "idle", "friendly_name": "Living Room"})
    return ha


def _meta(entity):
    for e, dc, name in OPENINGS:
        if e == entity:
            return dc, name
    return "opening", entity


async def opening(ha: SimulatedHA, entity: str, is_open: bool) -> None:
    dc, name = _meta(entity)
    await ha.set_state(entity, "on" if is_open else "off",
                       {"device_class": dc, "friendly_name": name})


async def set_furnace(ha: SimulatedHA, action: str) -> None:
    """action: 'heating' or 'idle'."""
    await ha.set_state("climate.living_room", "heat",
                       {"hvac_action": action, "friendly_name": "Living Room"})


async def go_offline(ha: SimulatedHA, entity: str) -> None:
    dc, name = _meta(entity)
    await ha.set_state(entity, "unavailable", {"device_class": dc, "friendly_name": name})


async def drain_battery(ha: SimulatedHA, entity: str, levels) -> None:
    dc, name = _meta(entity)
    batt = entity.replace("binary_sensor.", "sensor.") + "_battery"
    for level in levels:
        await ha.set_state(batt, str(level),
                           {"device_class": "battery", "unit_of_measurement": "%",
                            "friendly_name": name})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from doorwindow import DoorWindowMonitor

    ha = build_sim()
    m = DoorWindowMonitor()
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Kitchen window opened, then left open 12 minutes:")
    await opening(ha, "binary_sensor.kitchen_window", True)
    clk["t"] += 12 * 60
    await m.check_timeouts(ha)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nBedroom window opened while the furnace is heating:")
    await set_furnace(ha, "heating")
    await opening(ha, "binary_sensor.bedroom_window", True)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
