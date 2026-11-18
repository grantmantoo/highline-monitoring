"""
Highline Tech -- Zooz ZAC36 valve simulator
===========================================
Emits realistic Z-Wave JS events for the valve actuator so valve.py can be run
and verified with no hardware: onboard temperature drift toward freezing, the
ZAC36's attached leak probe going wet, valve open/close acks, and a motor-stall
failure (commanded close that does not seat).

Standalone:
    python zooz_valve_sim.py          # print an event timeline for each scenario
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA
from valve import VALVE_LEAK, VALVE_SWITCH, VALVE_TEMP


def build_sim() -> SimulatedHA:
    """A SimulatedHA seeded with the valve in its normal resting state."""
    ha = SimulatedHA()
    ha.seed(VALVE_SWITCH, "on", {"friendly_name": "Water Main Valve"})       # open
    ha.seed(VALVE_TEMP, "18.5", {"unit_of_measurement": "C", "device_class": "temperature"})
    ha.seed(VALVE_LEAK, "off", {"device_class": "moisture", "friendly_name": "Water Main Probe"})
    return ha


async def drift_temperature(ha: SimulatedHA, readings) -> None:
    """Push a sequence of onboard temperature readings (degrees C)."""
    for value in readings:
        await ha.set_state(VALVE_TEMP, f"{value:.1f}",
                           {"unit_of_measurement": "C", "device_class": "temperature"})


async def probe_leak(ha: SimulatedHA, wet: bool) -> None:
    await ha.set_state(VALVE_LEAK, "on" if wet else "off", {"device_class": "moisture"})


def make_stall(ha: SimulatedHA) -> None:
    """Register a switch.turn_off that does NOT seat -- simulates a motor stall."""
    async def _stalled(data):
        return  # acknowledge the command but leave the valve open
    ha.register_service("switch", "turn_off", _stalled)


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    # Import here so the simulator module has no hard dependency on the logic.
    from valve import ValveController

    def wire(ha):
        c = ValveController()
        ha.add_listener(lambda ev: c.handle_event(ev, ha))
        return c

    print("Scenario: temperature drifts toward freezing")
    ha = build_sim()
    c = wire(ha)
    await drift_temperature(ha, [12.0, 8.0, 5.0, 3.5, 2.0])
    print(f"  alerts: {[a['code'] for a in c.alerts]}")

    print("\nScenario: onboard leak probe goes wet -> valve closes")
    ha = build_sim()
    c = wire(ha)
    await probe_leak(ha, True)
    print(f"  alerts: {[a['code'] for a in c.alerts]}")
    print(f"  valve switch is now: {(await ha.get_state(VALVE_SWITCH))['state']}  (off = closed)")


if __name__ == "__main__":
    asyncio.run(_demo())
