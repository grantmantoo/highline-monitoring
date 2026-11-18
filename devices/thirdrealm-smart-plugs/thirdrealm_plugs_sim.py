"""
Highline Tech -- THIRDREALITY smart-plug simulator
=================================================
Emits realistic ZHA power-metering events for a 4-pack of plugs: a coffee maker's
morning cycle, a space heater left running, an idle routine appliance, and a plug
dropping off the mesh.

    python thirdrealm_plugs_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# plug name -> friendly label
PLUGS = {
    "coffee_maker": "Coffee Maker",
    "kitchen_lamp": "Kitchen Lamp",
    "space_heater": "Space Heater",
    "tv": "TV",
}


def build_sim() -> SimulatedHA:
    """Seed each plug on (switch) at ~0 W idle with fresh energy totals."""
    ha = SimulatedHA()
    for plug, label in PLUGS.items():
        ha.seed(f"switch.{plug}", "on", {"friendly_name": label})
        ha.seed(f"sensor.{plug}_power", "0.0",
                {"device_class": "power", "unit_of_measurement": "W", "friendly_name": label})
        ha.seed(f"sensor.{plug}_energy", "0.0",
                {"device_class": "energy", "unit_of_measurement": "kWh", "friendly_name": label})
    return ha


async def power(ha: SimulatedHA, plug: str, watts: float) -> None:
    await ha.set_state(f"sensor.{plug}_power", f"{watts:.1f}",
                       {"device_class": "power", "unit_of_measurement": "W",
                        "friendly_name": PLUGS.get(plug, plug)})


async def go_offline(ha: SimulatedHA, plug: str) -> None:
    await ha.set_state(f"sensor.{plug}_power", "unavailable",
                       {"device_class": "power", "friendly_name": PLUGS.get(plug, plug)})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from plugs import PlugMonitor

    ha = build_sim()
    m = PlugMonitor()
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    m._start = clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Morning: coffee maker runs, then finishes:")
    await power(ha, "coffee_maker", 900.0)
    await power(ha, "coffee_maker", 0.0)
    print(f"  activity: {[a['plug'] for a in m.activity]}")

    print("\nSpace heater switched on and left running 3+ hours:")
    await power(ha, "space_heater", 1200.0)
    clk["t"] += 3.5 * 3600
    await m.check_timeouts(ha)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
