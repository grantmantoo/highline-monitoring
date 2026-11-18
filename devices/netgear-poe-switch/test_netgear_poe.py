"""
Highline Tech -- NETGEAR PoE switch-health tests
===============================================
    python test_netgear_poe.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from netgear_poe_sim import CAMERAS, build_sim, set_reachable
from poe_health import PoEHealthMonitor


def _wire(ha, start=1000.0):
    m = PoEHealthMonitor(roster=set(CAMERAS))
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_single_camera_down():
    ha = build_sim()
    m, clk = _wire(ha)
    await set_reachable(ha, "camera.porch", False)
    assert any(a["code"] == "device_unreachable" for a in m.alerts)
    assert not any(a["code"] == "switch_or_uplink_down" for a in m.alerts)


async def test_all_cameras_down_is_switch():
    ha = build_sim()
    m, clk = _wire(ha)
    for e in CAMERAS:
        await set_reachable(ha, e, False)
    sw = [a for a in m.alerts if a["code"] == "switch_or_uplink_down"]
    assert len(sw) == 1, f"expected 1 switch alert, got {len(sw)}"
    assert sw[0]["level"] == "critical"


async def test_flapping_camera_is_power_budget():
    ha = build_sim()
    m, clk = _wire(ha)
    # Three quick down/up cycles within the flap window.
    for _ in range(3):
        await set_reachable(ha, "camera.driveway", False)
        clk["t"] += 30
        await set_reachable(ha, "camera.driveway", True)
        clk["t"] += 30
    assert any(a["code"] == "unstable_poe" for a in m.alerts), "no power-budget alert"


async def test_slow_reconnects_not_flapping():
    ha = build_sim()
    m, clk = _wire(ha)
    # Three down/up cycles, but spread far beyond the 10-min window.
    for _ in range(3):
        await set_reachable(ha, "camera.driveway", False)
        clk["t"] += 30
        await set_reachable(ha, "camera.driveway", True)
        clk["t"] += 20 * 60
    assert not any(a["code"] == "unstable_poe" for a in m.alerts)


TESTS = [
    test_single_camera_down,
    test_all_cameras_down_is_switch,
    test_flapping_camera_is_power_budget,
    test_slow_reconnects_not_flapping,
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
