"""
Highline Tech -- Aqara temp/humidity simulator
==============================================
Emits realistic ZHA climate events for a 3-pack of Aqara sensors (one per room):
temperature drift (cold snap / heat), a humidity rise after a shower, a sensor
dropping to 'unavailable', barometric pressure, and slow battery decay.

    python aqara_temp_humidity_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

ROOMS = ["bedroom", "living_room", "bathroom"]


def _name(room: str) -> str:
    return room.replace("_", " ").title()


def build_sim() -> SimulatedHA:
    """Seed each room at comfortable, fresh-battery resting values."""
    ha = SimulatedHA()
    for room in ROOMS:
        n = _name(room)
        ha.seed(f"sensor.{room}_temperature", "21.0",
                {"device_class": "temperature", "unit_of_measurement": "C", "friendly_name": n})
        ha.seed(f"sensor.{room}_humidity", "45",
                {"device_class": "humidity", "unit_of_measurement": "%", "friendly_name": n})
        ha.seed(f"sensor.{room}_pressure", "1013",
                {"device_class": "pressure", "unit_of_measurement": "hPa", "friendly_name": n})
        ha.seed(f"sensor.{room}_battery", "100",
                {"device_class": "battery", "unit_of_measurement": "%", "friendly_name": n})
    return ha


async def temperature(ha: SimulatedHA, room: str, readings) -> None:
    n = _name(room)
    for value in readings:
        await ha.set_state(f"sensor.{room}_temperature", f"{value:.1f}",
                           {"device_class": "temperature", "unit_of_measurement": "C",
                            "friendly_name": n})


async def humidity(ha: SimulatedHA, room: str, readings) -> None:
    n = _name(room)
    for value in readings:
        await ha.set_state(f"sensor.{room}_humidity", str(value),
                           {"device_class": "humidity", "unit_of_measurement": "%",
                            "friendly_name": n})


async def go_offline(ha: SimulatedHA, room: str) -> None:
    n = _name(room)
    await ha.set_state(f"sensor.{room}_temperature", "unavailable",
                       {"device_class": "temperature", "friendly_name": n})


async def drain_battery(ha: SimulatedHA, room: str, levels) -> None:
    n = _name(room)
    for level in levels:
        await ha.set_state(f"sensor.{room}_battery", str(level),
                           {"device_class": "battery", "unit_of_measurement": "%",
                            "friendly_name": n})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from climate import ClimateMonitor

    ha = build_sim()
    m = ClimateMonitor()
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Bedroom heating fails overnight (cold snap):")
    await temperature(ha, "bedroom", [18.0, 15.0, 11.5, 9.0])
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nBathroom humidity after a shower:")
    await humidity(ha, "bathroom", [55, 68, 78])
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nLiving room sensor drops off the mesh:")
    await go_offline(ha, "living_room")
    print(f"  alerts: {[a['code'] for a in m.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
