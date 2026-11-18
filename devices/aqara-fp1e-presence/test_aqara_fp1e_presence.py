"""
Highline Tech -- Aqara FP1E presence automation tests
====================================================
    python test_aqara_fp1e_presence.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from aqara_fp1e_presence_sim import build_sim, go_offline, presence
from presence import PresenceMonitor


def _wire(ha, start=1000.0):
    m = PresenceMonitor()
    clk = {"t": start}
    m._clock = lambda: clk["t"]
    m._last_activity = start
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m, clk


async def test_presence_drives_light():
    ha = build_sim()
    m, clk = _wire(ha)
    await presence(ha, "living_room", True)
    assert (await ha.get_state("light.living_room"))["state"] == "on"
    await presence(ha, "living_room", False)
    assert (await ha.get_state("light.living_room"))["state"] == "off"


async def test_no_activity_wellness_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    # Someone was around, then leaves; house quiet past the 6h threshold.
    await presence(ha, "living_room", True)
    await presence(ha, "living_room", False)
    clk["t"] += 6.5 * 3600
    await m.check_wellness(ha)
    await m.check_wellness(ha)   # must not double-alert
    no_act = [a for a in m.alerts if a["code"] == "no_activity"]
    assert len(no_act) == 1, f"expected 1 no-activity alert, got {len(no_act)}"


async def test_activity_resets_no_activity():
    ha = build_sim()
    m, clk = _wire(ha)
    await presence(ha, "bedroom", True)
    await presence(ha, "bedroom", False)
    clk["t"] += 3 * 3600          # only 3h quiet -> no alert yet
    await m.check_wellness(ha)
    assert not any(a["code"] == "no_activity" for a in m.alerts)


async def test_prolonged_presence_in_bathroom():
    ha = build_sim()
    m, clk = _wire(ha)
    await presence(ha, "bathroom", True)
    clk["t"] += 35 * 60           # 35 minutes continuous
    await m.check_wellness(ha)
    assert any(a["code"] == "prolonged_presence" for a in m.alerts), "no fall/linger alert"
    # Leaving clears it; re-entering and lingering re-alerts.
    await presence(ha, "bathroom", False)
    await presence(ha, "bathroom", True)
    clk["t"] += 35 * 60
    await m.check_wellness(ha)
    linger = [a for a in m.alerts if a["code"] == "prolonged_presence"]
    assert len(linger) == 2, f"expected re-alert after re-entry, got {len(linger)}"


async def test_offline_alert():
    ha = build_sim()
    m, clk = _wire(ha)
    await go_offline(ha, "bedroom")
    assert any(a["code"] == "presence_offline" for a in m.alerts)


async def test_offline_while_present_does_not_false_fire_fall():
    # A sensor dropping off the mesh while showing "on" must NOT keep reading as
    # occupied -- otherwise prolonged_presence ("possible fall") fires from a dead
    # sensor and the room stays stuck "present" forever.
    ha = build_sim()
    m, clk = _wire(ha)
    await presence(ha, "bathroom", True)
    await go_offline(ha, "bathroom")
    clk["t"] += 35 * 60
    await m.check_wellness(ha)
    assert not any(a["code"] == "prolonged_presence" for a in m.alerts), \
        "dead sensor false-fired a fall alert"
    assert "bathroom" not in m._present and "bathroom" not in m._present_since


async def test_offline_room_blocks_then_restores_no_activity():
    # An offline room is UNKNOWN coverage: no_activity must not fire while blind in
    # a room, but must work again once that room reports in.
    ha = build_sim()
    m, clk = _wire(ha)
    await go_offline(ha, "bedroom")
    clk["t"] += 6.5 * 3600
    await m.check_wellness(ha)
    assert not any(a["code"] == "no_activity" for a in m.alerts), \
        "declared the house quiet while blind in a room"
    await presence(ha, "bedroom", False)        # sensor back, reports vacant
    clk["t"] += 6.5 * 3600
    await m.check_wellness(ha)
    assert any(a["code"] == "no_activity" for a in m.alerts), \
        "no-activity never fired after coverage returned"


TESTS = [
    test_presence_drives_light,
    test_no_activity_wellness_alert,
    test_activity_resets_no_activity,
    test_prolonged_presence_in_bathroom,
    test_offline_alert,
    test_offline_while_present_does_not_false_fire_fall,
    test_offline_room_blocks_then_restores_no_activity,
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
