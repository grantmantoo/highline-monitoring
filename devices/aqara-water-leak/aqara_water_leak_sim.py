"""
Highline Tech -- Aqara water leak simulator
===========================================
Emits realistic ZHA events for a 3-pack of Aqara leak sensors placed at the
house's water-risk points, plus their battery sensors: leak on/off transitions
and a slow CR2032 battery decay.

    python aqara_water_leak_sim.py     # print an event timeline + monitor reaction
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# Each leak sensor: (water binary_sensor, battery sensor, friendly location).
SENSORS = [
    ("binary_sensor.water_heater_water", "sensor.water_heater_leak_battery", "Water Heater"),
    ("binary_sensor.kitchen_sink_water", "sensor.kitchen_sink_leak_battery", "Kitchen Sink"),
    ("binary_sensor.washing_machine_water", "sensor.washing_machine_leak_battery", "Washing Machine"),
    ("binary_sensor.bathroom_vanity_water", "sensor.bathroom_vanity_leak_battery", "Bathroom Vanity"),
]


def build_sim() -> SimulatedHA:
    """A SimulatedHA seeded with every leak sensor dry and batteries fresh."""
    ha = SimulatedHA()
    for water, battery, name in SENSORS:
        ha.seed(water, "off", {"device_class": "moisture", "friendly_name": f"{name} Leak"})
        ha.seed(battery, "100",
                {"device_class": "battery", "unit_of_measurement": "%", "friendly_name": f"{name} Leak"})
    # The Zooz valve the leak automation acts on -- seeded open so we can watch it close.
    ha.seed("switch.water_main_valve", "on", {"friendly_name": "Water Main Valve"})
    return ha


def _attrs(name: str) -> dict:
    return {"device_class": "moisture", "friendly_name": f"{name} Leak"}


async def leak(ha: SimulatedHA, water_entity: str, wet: bool) -> None:
    name = next((n for w, _, n in SENSORS if w == water_entity), water_entity)
    await ha.set_state(water_entity, "on" if wet else "off", _attrs(name))


async def drain_battery(ha: SimulatedHA, battery_entity: str, levels) -> None:
    name = next((n for _, b, n in SENSORS if b == battery_entity), battery_entity)
    for level in levels:
        await ha.set_state(battery_entity, str(level),
                           {"device_class": "battery", "unit_of_measurement": "%",
                            "friendly_name": f"{name} Leak"})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from leak import LeakMonitor

    ha = build_sim()
    monitor = LeakMonitor()
    ha.add_listener(lambda ev: monitor.handle_event(ev, ha))

    print("Leak appears under the kitchen sink:")
    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)
    print(f"  valve switch -> {(await ha.get_state('switch.water_main_valve'))['state']}  (off = closed)")
    print(f"  alerts: {[a['code'] for a in monitor.alerts]}")

    print("\nWasher leak sensor battery decays:")
    await drain_battery(ha, "sensor.washing_machine_leak_battery", [60, 40, 20, 12])
    print(f"  alerts: {[a['code'] for a in monitor.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
