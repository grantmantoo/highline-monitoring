"""
Highline Tech -- THIRDREALITY smart-plug automation tests
========================================================
    python test_thirdrealm_plugs.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from plugs import PlugMonitor
from thirdrealm_plugs_sim import build_sim, go_offline, power


def _wire(ha, start=1000.0, routine=("coffee_maker",)):
    m = PlugMonitor(routine_plugs=set(routine))
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    m._start = start
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_appliance_used_activity():
    ha = build_sim()
    m, clk = _wire(ha)
    await power(ha, "kitchen_lamp", 40.0)
    assert any(a["plug"] == "kitchen_lamp" for a in m.activity), "no activity logged"


async def test_standby_below_threshold_no_activity():
    ha = build_sim()
    m, clk = _wire(ha)
    await power(ha, "tv", 2.0)        # vampire draw, below the on-threshold
    assert not m.activity, "standby draw counted as activity"


async def test_high_load_left_on_alerts():
    ha = build_sim()
    m, clk = _wire(ha)
    await power(ha, "space_heater", 1200.0)
    clk["t"] += 3.5 * 3600
    await m.check_timeouts(ha)
    await m.check_timeouts(ha)        # must not double-alert
    high = [a for a in m.alerts if a["code"] == "high_load_left_on"]
    assert len(high) == 1, f"expected 1 high-load alert, got {len(high)}"


async def test_high_load_within_grace_no_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await power(ha, "space_heater", 1200.0)
    clk["t"] += 1 * 3600             # only an hour
    await m.check_timeouts(ha)
    assert not any(a["code"] == "high_load_left_on" for a in m.alerts)


async def test_routine_missed_alerts():
    ha = build_sim()
    m, clk = _wire(ha)
    clk["t"] += 27 * 3600            # a day-plus with no coffee
    await m.check_timeouts(ha)
    assert any(a["code"] == "routine_missed" for a in m.alerts), "no routine wellness alert"


async def test_routine_used_recently_no_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await power(ha, "coffee_maker", 900.0)   # used now
    await power(ha, "coffee_maker", 0.0)
    clk["t"] += 10 * 3600            # only 10h since
    await m.check_timeouts(ha)
    assert not any(a["code"] == "routine_missed" for a in m.alerts)


async def test_offline_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await go_offline(ha, "tv")
    assert any(a["code"] == "plug_offline" for a in m.alerts)


TESTS = [
    test_appliance_used_activity,
    test_standby_below_threshold_no_activity,
    test_high_load_left_on_alerts,
    test_high_load_within_grace_no_alert,
    test_routine_missed_alerts,
    test_routine_used_recently_no_alert,
    test_offline_alert,
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
