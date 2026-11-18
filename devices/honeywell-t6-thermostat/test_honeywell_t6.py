"""
Highline Tech -- Honeywell T6 thermostat automation tests
========================================================
    python test_honeywell_t6.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from honeywell_t6_sim import (
    THERMOSTAT,
    build_sim,
    go_offline,
    set_current,
    set_mode,
    set_setpoint,
)
from thermostat import ThermostatMonitor


def _wire(ha, start=1000.0):
    m = ThermostatMonitor()
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_freeze_protection_acts():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_mode(ha, "off")
    await set_current(ha, 12.0)         # below safe min
    clk["t"] += 16 * 60                 # past the 15-min grace
    await m.check_timeouts(ha)

    codes = [a["code"] for a in m.alerts]
    assert "too_cold" in codes, codes
    assert "freeze_protect_engaged" in codes, codes
    st = await ha.get_state(THERMOSTAT)
    assert st["state"] == "heat", "should have forced heat mode"
    assert st["attributes"]["temperature"] == 18.0, "should have restored safe setpoint"


async def test_cold_within_grace_no_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_mode(ha, "off")
    await set_current(ha, 12.0)
    clk["t"] += 5 * 60                  # only 5 minutes
    await m.check_timeouts(ha)
    assert not any(a["code"] == "too_cold" for a in m.alerts), "alerted before grace elapsed"


async def test_setpoint_tamper():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_current(ha, 21.0)         # establish a baseline target (21)
    await set_setpoint(ha, 5.0)         # someone drops it to 5 C
    assert any(a["code"] == "setpoint_tamper" for a in m.alerts)


async def test_normal_setpoint_change_no_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_current(ha, 21.0)
    await set_setpoint(ha, 20.0)        # reasonable adjustment, within band
    assert not any(a["code"] == "setpoint_tamper" for a in m.alerts)


async def test_too_hot():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_current(ha, 31.0)
    assert any(a["code"] == "too_hot" for a in m.alerts)


async def test_offline():
    ha = build_sim()
    m, clk = _wire(ha)
    await go_offline(ha)
    assert any(a["code"] == "thermostat_offline" for a in m.alerts)


TESTS = [
    test_freeze_protection_acts,
    test_cold_within_grace_no_alert,
    test_setpoint_tamper,
    test_normal_setpoint_change_no_alert,
    test_too_hot,
    test_offline,
]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            asyncio.run(t())
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
