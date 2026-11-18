"""
Highline Tech -- Aqara water leak automation tests
=================================================
Runs leak.LeakMonitor against the simulator: leak -> valve close, manual-reopen
policy, and low-battery alerting.

    python test_aqara_water_leak.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from aqara_water_leak_sim import build_sim, drain_battery, leak
from leak import LeakMonitor

VALVE = "switch.water_main_valve"


def _wire(ha):
    m = LeakMonitor()
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m


async def test_leak_closes_valve_and_alerts():
    ha = build_sim()
    m = _wire(ha)
    assert (await ha.get_state(VALVE))["state"] == "on"

    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)

    assert (await ha.get_state(VALVE))["state"] == "off", "valve should be closed on leak"
    assert [a["code"] for a in m.alerts] == ["leak_detected"]
    assert "Kitchen Sink" in m.alerts[0]["message"]


async def test_cleared_leak_does_not_reopen_valve():
    ha = build_sim()
    m = _wire(ha)
    await leak(ha, "binary_sensor.water_heater_water", wet=True)
    await leak(ha, "binary_sensor.water_heater_water", wet=False)  # dries out

    # Reopen is manual: valve must stay closed even after the sensor clears.
    assert (await ha.get_state(VALVE))["state"] == "off", "valve must NOT auto-reopen"


async def test_multiple_leaks_each_alert_once():
    ha = build_sim()
    m = _wire(ha)
    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)
    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)   # duplicate report
    await leak(ha, "binary_sensor.washing_machine_water", wet=True)

    leaks = [a for a in m.alerts if a["code"] == "leak_detected"]
    assert len(leaks) == 2, f"expected one alert per distinct sensor, got {len(leaks)}"


async def test_low_battery_alert_with_recovery():
    ha = build_sim()
    m = _wire(ha)
    await drain_battery(ha, "sensor.washing_machine_leak_battery", [60, 40, 20, 12])
    low = [a for a in m.alerts if a["code"] == "leak_sensor_low_battery"]
    assert len(low) == 1, f"expected 1 low-battery alert, got {len(low)}"

    # Fresh cell, then decays again -> a second alert.
    await drain_battery(ha, "sensor.washing_machine_leak_battery", [100, 10])
    low = [a for a in m.alerts if a["code"] == "leak_sensor_low_battery"]
    assert len(low) == 2, f"expected re-alert after battery swap, got {len(low)}"


async def test_failed_close_still_alerts_and_flags_shutoff():
    # If the valve close raises, the leak alert must STILL go out, plus an explicit
    # "shutoff failed" alert -- the detection must never be swallowed by the error.
    ha = build_sim()
    m = _wire(ha)

    async def boom(data):
        raise RuntimeError("valve unreachable")
    ha.register_service("switch", "turn_off", boom)

    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)

    codes = [a["code"] for a in m.alerts]
    assert "leak_detected" in codes, "failed close suppressed the leak alert"
    assert "valve_shutoff_failed" in codes, "no alert that the shutoff command failed"


async def test_unseated_close_flags_motor_stall():
    # The close is accepted but the valve never moves (motor stall): the leak->valve
    # path must read the valve back and flag it, like ValveController.close().
    ha = build_sim()
    m = _wire(ha)

    async def accept_but_dont_move(data):
        pass
    ha.register_service("switch", "turn_off", accept_but_dont_move)

    await leak(ha, "binary_sensor.washing_machine_water", wet=True)

    codes = [a["code"] for a in m.alerts]
    assert "leak_detected" in codes
    assert "valve_close_failed" in codes, "unseated valve (motor stall) not detected"
    assert (await ha.get_state(VALVE))["state"] == "on", "valve never actually closed"


TESTS = [
    test_leak_closes_valve_and_alerts,
    test_cleared_leak_does_not_reopen_valve,
    test_multiple_leaks_each_alert_once,
    test_low_battery_alert_with_recovery,
    test_failed_close_still_alerts_and_flags_shutoff,
    test_unseated_close_flags_motor_stall,
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
