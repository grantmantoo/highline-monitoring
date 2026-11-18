"""
Highline Tech -- Honeywell T6 thermostat simulator
=================================================
Emits realistic Z-Wave JS climate events and honors the control services the
monitor calls back (set_hvac_mode / set_temperature), so freeze-protection can be
verified end to end: a cold snap with the thermostat off, a tampered setpoint, a
heat climb, and an offline drop.

    python honeywell_t6_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA
from thermostat import THERMOSTAT


def build_sim() -> SimulatedHA:
    """Seed the thermostat heating-idle at a comfortable 21 C, target 21 C."""
    ha = SimulatedHA()
    ha.seed(THERMOSTAT, "heat",
            {"current_temperature": 21.0, "temperature": 21.0, "hvac_action": "idle",
             "friendly_name": "Living Room"})

    async def set_hvac_mode(data):
        e = data["entity_id"]
        st = await ha.get_state(e) or {"attributes": {}}
        await ha.set_state(e, data["hvac_mode"], dict(st.get("attributes", {})))

    async def set_temperature(data):
        e = data["entity_id"]
        st = await ha.get_state(e)
        attrs = dict(st["attributes"])
        attrs["temperature"] = float(data["temperature"])
        await ha.set_state(e, st["state"], attrs)

    ha.register_service("climate", "set_hvac_mode", set_hvac_mode)
    ha.register_service("climate", "set_temperature", set_temperature)
    return ha


async def _emit(ha: SimulatedHA, **changes) -> None:
    st = await ha.get_state(THERMOSTAT)
    state = changes.pop("hvac_mode", st["state"])
    attrs = dict(st["attributes"])
    attrs.update(changes)
    await ha.set_state(THERMOSTAT, state, attrs)


async def set_current(ha: SimulatedHA, temp_c: float) -> None:
    await _emit(ha, current_temperature=temp_c)


async def set_setpoint(ha: SimulatedHA, temp_c: float) -> None:
    await _emit(ha, temperature=temp_c)


async def set_mode(ha: SimulatedHA, mode: str) -> None:
    await _emit(ha, hvac_mode=mode)


async def go_offline(ha: SimulatedHA) -> None:
    await ha.set_state(THERMOSTAT, "unavailable", {})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from thermostat import ThermostatMonitor

    ha = build_sim()
    m = ThermostatMonitor()
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Furnace fails: thermostat off, room slides to 12 C for 16 minutes:")
    await set_mode(ha, "off")
    await set_current(ha, 12.0)
    clk["t"] += 16 * 60
    await m.check_timeouts(ha)
    st = await ha.get_state(THERMOSTAT)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")
    print(f"  thermostat now: mode={st['state']} target={st['attributes']['temperature']} C")


if __name__ == "__main__":
    asyncio.run(_demo())
