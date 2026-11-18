"""
Highline Tech -- Reolink camera-bundle automation tests
======================================================
    python test_reolink_camera.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from camera_monitor import CameraMonitor
from reolink_camera_sim import build_sim, detect, set_camera_online


def _wire(ha, start=1000.0, cooldown=30.0):
    m = CameraMonitor(cooldown=cooldown)
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_person_detection_alerts():
    ha = build_sim()
    m, clk = _wire(ha)
    await detect(ha, "front_door", "person", True)
    assert any(a["code"] == "person_detected" for a in m.alerts)


async def test_detection_cooldown_dedupes():
    ha = build_sim()
    m, clk = _wire(ha)
    await detect(ha, "front_door", "person", True)
    await detect(ha, "front_door", "person", False)
    clk["t"] += 5                      # within 30s cooldown
    await detect(ha, "front_door", "person", True)
    person = [a for a in m.alerts if a["code"] == "person_detected"]
    assert len(person) == 1, f"cooldown should dedupe, got {len(person)}"

    clk["t"] += 60                     # past cooldown -> fires again
    await detect(ha, "front_door", "person", True)
    person = [a for a in m.alerts if a["code"] == "person_detected"]
    assert len(person) == 2, f"expected re-alert after cooldown, got {len(person)}"


async def test_vehicle_detection_alerts():
    ha = build_sim()
    m, clk = _wire(ha)
    await detect(ha, "driveway", "vehicle", True)
    assert any(a["code"] == "vehicle_detected" for a in m.alerts)


async def test_motion_is_activity_not_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await detect(ha, "back_yard", "motion", True)
    assert not m.alerts, "motion should not raise a notification"
    assert any(a["kind"] == "motion" for a in m.activity), "motion not logged as activity"


async def test_camera_offline_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_camera_online(ha, "porch", False)
    assert any(a["code"] == "camera_offline" for a in m.alerts)
    # Recover, drop again -> re-alert.
    await set_camera_online(ha, "porch", True)
    await set_camera_online(ha, "porch", False)
    offline = [a for a in m.alerts if a["code"] == "camera_offline"]
    assert len(offline) == 2, f"expected re-alert after recovery, got {len(offline)}"


TESTS = [
    test_person_detection_alerts,
    test_detection_cooldown_dedupes,
    test_vehicle_detection_alerts,
    test_motion_is_activity_not_alert,
    test_camera_offline_alert,
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
