"""
Highline Tech -- Aqara door/window automation tests
==================================================
    python test_aqara_door_window.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from aqara_door_window_sim import (
    build_sim,
    drain_battery,
    go_offline,
    opening,
    set_furnace,
)
from doorwindow import DoorWindowMonitor


def _wire(ha, start=1000.0):
    m = DoorWindowMonitor()
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_open_then_close_no_timeout():
    ha = build_sim()
    m, clk = _wire(ha)
    await opening(ha, "binary_sensor.front_door", True)
    clk["t"] += 60          # 1 minute
    await opening(ha, "binary_sensor.front_door", False)
    clk["t"] += 3600        # an hour later
    await m.check_timeouts(ha)
    assert not any(a["code"] == "opening_left_open" for a in m.alerts), "closed door alerted"


async def test_left_open_alerts_once():
    ha = build_sim()
    m, clk = _wire(ha)
    await opening(ha, "binary_sensor.kitchen_window", True)
    clk["t"] += 12 * 60     # 12 minutes
    await m.check_timeouts(ha)
    await m.check_timeouts(ha)   # second poll must not re-alert
    left = [a for a in m.alerts if a["code"] == "opening_left_open"]
    assert len(left) == 1, f"expected 1 left-open alert, got {len(left)}"


async def test_open_while_heating():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_furnace(ha, "heating")
    await opening(ha, "binary_sensor.bedroom_window", True)
    assert any(a["code"] == "open_while_heating" for a in m.alerts), "no heat-loss alert"


async def test_open_while_idle_no_heating_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_furnace(ha, "idle")
    await opening(ha, "binary_sensor.bedroom_window", True)
    assert not any(a["code"] == "open_while_heating" for a in m.alerts)


async def test_offline_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await go_offline(ha, "binary_sensor.front_door")
    assert any(a["code"] == "contact_offline" for a in m.alerts)


async def test_low_battery_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await drain_battery(ha, "binary_sensor.front_door", [50, 18, 10])
    low = [a for a in m.alerts if a["code"] == "contact_low_battery"]
    assert len(low) == 1, f"expected 1 low-battery alert, got {len(low)}"


async def test_excluded_entity_is_ignored():
    """A lock's own door-position sensor must not be adopted as an opening.

    The BE469ZP reports device_class "door" and sat at OPEN on a shut door
    (2026-09-01). Without exclusion this monitor raises opening_left_open
    forever on a phantom.
    """
    phantom = "binary_sensor.touchscreen_deadbolt_z_wave_plus_current_status_of_the_door"
    ha = build_sim()
    m = DoorWindowMonitor(exclude=[phantom])
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    await opening(ha, phantom, True)      # phantom "opens" and never closes
    clk["t"] += 24 * 3600                 # a full day
    await m.check_timeouts(ha)
    assert not m.alerts, f"excluded entity produced alerts: {m.alerts}"

    # a real contact alongside it must still work
    await opening(ha, "binary_sensor.front_door", True)
    clk["t"] += 12 * 60
    await m.check_timeouts(ha)
    left = [a for a in m.alerts if a["code"] == "opening_left_open"]
    assert len(left) == 1, f"real opening should still alert, got {m.alerts}"


async def test_offline_while_open_stops_left_open_timer():
    # A contact that dies while "open" has an unknown true state -- check_timeouts
    # must stop counting it toward opening_left_open.
    ha = build_sim()
    m, clk = _wire(ha)
    await opening(ha, "binary_sensor.kitchen_window", True)
    await go_offline(ha, "binary_sensor.kitchen_window")
    clk["t"] += 30 * 60            # well past the 10-min warn window
    await m.check_timeouts(ha)
    assert not any(a["code"] == "opening_left_open" for a in m.alerts), \
        "fired open-too-long for a dead contact"
    assert "binary_sensor.kitchen_window" not in m._open_since


TESTS = [
    test_open_then_close_no_timeout,
    test_left_open_alerts_once,
    test_open_while_heating,
    test_open_while_idle_no_heating_alert,
    test_offline_alert,
    test_low_battery_alert,
    test_offline_while_open_stops_left_open_timer,
    test_excluded_entity_is_ignored,
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
