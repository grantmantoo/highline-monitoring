"""
Highline Tech -- Zooz valve automation tests
============================================
Runs valve.ValveController against the simulator and asserts the real control
path behaves. No hardware, no live HA.

    python test_zooz_valve.py        # prints PASS/FAIL per case, exits nonzero on failure
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from valve import ValveController
from zooz_valve_sim import (
    VALVE_SWITCH,
    build_sim,
    drift_temperature,
    make_stall,
    probe_leak,
)


def _attach(ha, controller):
    ha.add_listener(lambda ev: controller.handle_event(ev, ha))


async def test_freeze_alert_with_hysteresis():
    ha = build_sim()
    c = ValveController()
    _attach(ha, c)

    # Drift down through the alert threshold (4.0 C): one alert, not one per reading.
    await drift_temperature(ha, [12.0, 8.0, 5.0, 3.5, 2.0])
    freeze = [a for a in c.alerts if a["code"] == "valve_freeze_risk"]
    assert len(freeze) == 1, f"expected 1 freeze alert, got {len(freeze)}"

    # Recover above the clear threshold (6.0 C), then drop again -> a second alert.
    await drift_temperature(ha, [7.0])
    await drift_temperature(ha, [1.0])
    freeze = [a for a in c.alerts if a["code"] == "valve_freeze_risk"]
    assert len(freeze) == 2, f"expected 2 freeze alerts after re-arm, got {len(freeze)}"


async def test_onboard_probe_closes_valve():
    ha = build_sim()
    c = ValveController()
    _attach(ha, c)

    assert (await ha.get_state(VALVE_SWITCH))["state"] == "on"  # starts open
    await probe_leak(ha, wet=True)

    valve = (await ha.get_state(VALVE_SWITCH))["state"]
    assert valve == "off", f"valve should be CLOSED after probe leak, is '{valve}'"
    codes = [a["code"] for a in c.alerts]
    assert "valve_probe_leak" in codes, codes
    # The alert was also surfaced into HA.
    assert ha.calls("persistent_notification", "create"), "no HA notification fired"


async def test_motor_stall_is_flagged():
    ha = build_sim()
    make_stall(ha)            # commanded close will not seat
    c = ValveController()
    _attach(ha, c)

    await probe_leak(ha, wet=True)

    valve = (await ha.get_state(VALVE_SWITCH))["state"]
    assert valve == "on", f"stall test expects valve stuck open, is '{valve}'"
    codes = [a["code"] for a in c.alerts]
    assert "valve_close_failed" in codes, f"stall not flagged: {codes}"


TESTS = [
    test_freeze_alert_with_hysteresis,
    test_onboard_probe_closes_valve,
    test_motor_stall_is_flagged,
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
