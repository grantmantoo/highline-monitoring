"""
Highline Tech -- SONOFF Zigbee mesh simulator
============================================
Emits ZHA roster events: individual nodes dropping/recovering, a coordinator-style
mass outage (many nodes unavailable at once), and LQI changes.

    python sonoff_zigbee_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# A representative slice of the mesh roster (entity -> friendly name).
ROSTER = {
    "binary_sensor.water_heater_water": "Water Heater Leak",
    "sensor.bedroom_temperature": "Bedroom Temp",
    "binary_sensor.front_door": "Front Door",
    "switch.coffee_maker": "Coffee Maker",
    "binary_sensor.living_room_occupancy": "Living Room Presence",
}


def build_sim() -> SimulatedHA:
    """Seed every roster node available with a healthy LQI."""
    ha = SimulatedHA()
    for entity, name in ROSTER.items():
        ha.seed(entity, "off" if entity.startswith("binary_sensor.") else "on",
                {"friendly_name": name})
        lqi = "sensor." + entity.split(".", 1)[1] + "_lqi"
        ha.seed(lqi, "120",
                {"device_class": "signal_strength", "unit_of_measurement": "lqi",
                 "friendly_name": name})
    return ha


async def set_available(ha: SimulatedHA, entity: str, available: bool) -> None:
    name = ROSTER.get(entity, entity)
    if not available:
        await ha.set_state(entity, "unavailable", {"friendly_name": name})
    else:
        rest = "off" if entity.startswith("binary_sensor.") else "on"
        await ha.set_state(entity, rest, {"friendly_name": name})


async def set_lqi(ha: SimulatedHA, entity: str, lqi: int) -> None:
    name = ROSTER.get(entity, entity)
    lqi_entity = "sensor." + entity.split(".", 1)[1] + "_lqi"
    await ha.set_state(lqi_entity, str(lqi),
                       {"device_class": "signal_strength", "unit_of_measurement": "lqi",
                        "friendly_name": name})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from zigbee_health import ZigbeeMeshMonitor

    ha = build_sim()
    m = ZigbeeMeshMonitor()
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("One node drops, then recovers:")
    await set_available(ha, "binary_sensor.front_door", False)
    await set_available(ha, "binary_sensor.front_door", True)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nCoordinator hiccup: four nodes go unavailable at once:")
    for e in ["binary_sensor.water_heater_water", "sensor.bedroom_temperature",
              "switch.coffee_maker", "binary_sensor.living_room_occupancy"]:
        await set_available(ha, e, False)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
