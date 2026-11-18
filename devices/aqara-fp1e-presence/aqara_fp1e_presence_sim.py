"""
Highline Tech -- Aqara FP1E presence simulator
=============================================
Emits realistic mmWave occupancy events: a person entering/leaving a room (with
the light following), a long quiet stretch with nobody home, a prolonged stay in
the bathroom, and the sensor dropping offline.

    python aqara_fp1e_presence_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

ROOMS = ["living_room", "bedroom", "bathroom"]


def build_sim() -> SimulatedHA:
    """Seed every room empty with its light off; wire up light services."""
    ha = SimulatedHA()
    for room in ROOMS:
        ha.seed(f"binary_sensor.{room}_occupancy",
                "off", {"device_class": "occupancy", "friendly_name": f"{room} Presence"})
        ha.seed(f"light.{room}", "off", {"friendly_name": f"{room} Light"})

    async def light_on(data):
        await ha.set_state(data["entity_id"], "on")

    async def light_off(data):
        await ha.set_state(data["entity_id"], "off")

    ha.register_service("light", "turn_on", light_on)
    ha.register_service("light", "turn_off", light_off)
    return ha


async def presence(ha: SimulatedHA, room: str, present: bool) -> None:
    await ha.set_state(f"binary_sensor.{room}_occupancy",
                       "on" if present else "off",
                       {"device_class": "occupancy", "friendly_name": f"{room} Presence"})


async def go_offline(ha: SimulatedHA, room: str) -> None:
    await ha.set_state(f"binary_sensor.{room}_occupancy",
                       "unavailable", {"device_class": "occupancy", "friendly_name": f"{room} Presence"})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from presence import PresenceMonitor

    ha = build_sim()
    m = PresenceMonitor()
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    m._last_activity = clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Someone sits down in the living room (still, but detected):")
    await presence(ha, "living_room", True)
    print(f"  light.living_room -> {(await ha.get_state('light.living_room'))['state']}")

    print("\nThey leave; the house is quiet for 6.5 hours:")
    await presence(ha, "living_room", False)
    clk["t"] += 6.5 * 3600
    await m.check_wellness(ha)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nLater, prolonged presence in the bathroom (possible fall):")
    m2 = PresenceMonitor()
    clk2 = {"t": 0.0}
    m2._clock = lambda: clk2["t"]
    ha2 = build_sim()
    ha2.add_listener(lambda ev: m2.handle_event(ev, ha2))
    await presence(ha2, "bathroom", True)
    clk2["t"] += 35 * 60
    await m2.check_wellness(ha2)
    print(f"  alerts: {[a['code'] for a in m2.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
