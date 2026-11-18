"""
Highline Tech -- Aqara temp/humidity automation tests
====================================================
    python test_aqara_temp_humidity.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from aqara_temp_humidity_sim import (
    build_sim,
    drain_battery,
    go_offline,
    humidity,
    temperature,
)
from climate import ClimateMonitor


def _wire(ha):
    m = ClimateMonitor()
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m


async def test_cold_room_alerts_once_with_hysteresis():
    ha = build_sim()
    m = _wire(ha)
    await temperature(ha, "bedroom", [18.0, 15.0, 11.5, 9.0])
    cold = [a for a in m.alerts if a["code"] == "room_cold"]
    assert len(cold) == 1, f"expected 1 cold alert, got {len(cold)}"

    # Warm back up over the clear point, then drop again -> second alert.
    await temperature(ha, "bedroom", [16.0])
    await temperature(ha, "bedroom", [8.0])
    cold = [a for a in m.alerts if a["code"] == "room_cold"]
    assert len(cold) == 2, f"expected re-alert, got {len(cold)}"


async def test_hot_room_alert():
    ha = build_sim()
    m = _wire(ha)
    await temperature(ha, "living_room", [27.0, 31.0])
    assert any(a["code"] == "room_hot" for a in m.alerts)


async def test_humidity_alert():
    ha = build_sim()
    m = _wire(ha)
    await humidity(ha, "bathroom", [55, 68, 78])
    humid = [a for a in m.alerts if a["code"] == "room_humid"]
    assert len(humid) == 1, f"expected 1 humidity alert, got {len(humid)}"


async def test_offline_then_recover():
    ha = build_sim()
    m = _wire(ha)
    await go_offline(ha, "living_room")
    assert any(a["code"] == "sensor_offline" for a in m.alerts)
    # Recover: a valid reading should clear offline and not double-alert.
    await temperature(ha, "living_room", [20.0])
    await go_offline(ha, "living_room")
    offline = [a for a in m.alerts if a["code"] == "sensor_offline"]
    assert len(offline) == 2, f"expected re-alert after recovery, got {len(offline)}"


async def test_low_battery_alert():
    ha = build_sim()
    m = _wire(ha)
    await drain_battery(ha, "bedroom", [50, 20, 12])
    low = [a for a in m.alerts if a["code"] == "sensor_low_battery"]
    assert len(low) == 1, f"expected 1 low-battery alert, got {len(low)}"


async def test_roster_excludes_non_room_temperature():
    # With a room roster, a non-room temperature entity (the water main's own probe)
    # must NOT be misread as a freezing "room".
    ha = build_sim()
    m = ClimateMonitor(rooms=["bedroom", "living_room", "bathroom"])
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    ha.seed("sensor.water_main_valve_temperature", "18.0",
            {"device_class": "temperature", "unit_of_measurement": "C"})
    await ha.set_state("sensor.water_main_valve_temperature", "2.0",
                       {"device_class": "temperature", "unit_of_measurement": "C"})
    assert not any(a["code"] == "room_cold" for a in m.alerts), \
        "valve temp misread as a freezing room"
    await temperature(ha, "bedroom", [9.0])      # a real room still alerts
    assert any(a["code"] == "room_cold" for a in m.alerts), "real cold room missed"


async def test_non_numeric_reading_is_ignored_not_raised():
    # A garbage reading must be swallowed (not raise) -- with the shared dispatch
    # loop a ValueError would otherwise drop the whole monitor.
    ha = build_sim()
    m = _wire(ha)
    await ha.set_state("sensor.bedroom_temperature", "n/a",
                       {"device_class": "temperature", "unit_of_measurement": "C",
                        "friendly_name": "Bedroom"})
    assert not any(a["code"] == "room_cold" for a in m.alerts)
    await temperature(ha, "bedroom", [9.0])      # monitor still alive
    assert any(a["code"] == "room_cold" for a in m.alerts)


TESTS = [
    test_cold_room_alerts_once_with_hysteresis,
    test_hot_room_alert,
    test_humidity_alert,
    test_offline_then_recover,
    test_low_battery_alert,
    test_roster_excludes_non_room_temperature,
    test_non_numeric_reading_is_ignored_not_raised,
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
