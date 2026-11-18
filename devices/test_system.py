"""
Highline Tech -- whole-system test
=================================
Boots EVERY configured device monitor from house.example.yaml against ONE
SimulatedHA, wired to one unified Notifier, then drives a realistic scenario and
asserts the right alerts came out the single delivery path:

  1. a leak fires AND closes the main valve (cross-device chain on the shared bus)
  2. a freeze warning at the water main
  3. an elder-care wellness event (prolonged presence in the bathroom)
  4. a Zigbee mesh mass-outage (coordinator-level fault)

No hardware, no live HA. Run:
    python test_system.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback

# Bootstrap the shared core, same as the device modules + runner.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from ha import SimulatedHA          # noqa: E402
from house_config import load_config  # noqa: E402
from notifier import Notifier        # noqa: E402

import run                            # noqa: E402  (devices/run.py)

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "house.example.yaml")
VALVE = "switch.water_main_valve"


def seed_house(ha: SimulatedHA) -> None:
    """Resting baseline for every entity the scenario touches (no events)."""
    ha.seed(VALVE, "on", {"friendly_name": "Water Main Valve"})
    ha.seed("sensor.water_main_valve_temperature", "18.0",
            {"device_class": "temperature", "unit_of_measurement": "C"})
    ha.seed("binary_sensor.water_main_valve_leak", "off", {"device_class": "moisture"})
    ha.seed("binary_sensor.kitchen_sink_water", "off",
            {"device_class": "moisture", "friendly_name": "Kitchen Sink Leak"})
    ha.seed("climate.living_room", "heat",
            {"current_temperature": 21.0, "temperature": 21.0, "hvac_action": "idle",
             "friendly_name": "Living Room"})
    ha.seed("sensor.bedroom_temperature", "21.0",
            {"device_class": "temperature", "unit_of_measurement": "C", "friendly_name": "Bedroom"})
    ha.seed("binary_sensor.front_door", "off",
            {"device_class": "door", "friendly_name": "Front Door"})
    ha.seed("binary_sensor.bathroom_occupancy", "off",
            {"device_class": "occupancy", "friendly_name": "Bathroom Presence"})
    ha.seed("light.bathroom", "off", {"friendly_name": "Bathroom Light"})
    ha.seed("switch.coffee_maker", "on", {"friendly_name": "Coffee Maker"})
    ha.seed("sensor.coffee_maker_power", "0.0",
            {"device_class": "power", "unit_of_measurement": "W", "friendly_name": "Coffee Maker"})


def _inject_clock(system, clk):
    """Put every time-based monitor on one controllable clock."""
    for _, _, m in system.monitors:
        if hasattr(m, "_clock"):
            m._clock = lambda: clk["t"]
        if hasattr(m, "_last_activity"):
            m._last_activity = clk["t"]
        if hasattr(m, "_start"):
            m._start = clk["t"]


async def test_full_house_scenario():
    config = load_config(CONFIG)
    notifier = Notifier({"min_level": "info"})        # no webhook -> records history
    system = run.build_system(config, notifier)
    assert len(system.monitors) == 10, f"expected 10 monitors, got {len(system.monitors)}"

    ha = SimulatedHA()
    seed_house(ha)
    clk = {"t": 1000.0}
    _inject_clock(system, clk)
    system.attach(ha)                                  # all monitors on one bus

    # 1) LEAK -> VALVE CLOSE (cross-device chain).
    await ha.set_state("binary_sensor.kitchen_sink_water", "on",
                       {"device_class": "moisture", "friendly_name": "Kitchen Sink Leak"})
    assert (await ha.get_state(VALVE))["state"] == "off", "leak did not close the main valve"

    # 2) FREEZE warning at the main.
    await ha.set_state("sensor.water_main_valve_temperature", "2.0",
                       {"device_class": "temperature", "unit_of_measurement": "C"})

    # 3) WELLNESS: prolonged presence in the bathroom (possible fall).
    await ha.set_state("binary_sensor.bathroom_occupancy", "on",
                       {"device_class": "occupancy", "friendly_name": "Bathroom Presence"})
    clk["t"] += 35 * 60
    await system.run_checks(ha, clk["t"])

    # 4) Zigbee MESH MASS OUTAGE (coordinator-level fault).
    for entity, attrs in [
        ("binary_sensor.front_door", {"device_class": "door", "friendly_name": "Front Door"}),
        ("sensor.bedroom_temperature", {"device_class": "temperature", "friendly_name": "Bedroom"}),
        ("switch.coffee_maker", {"friendly_name": "Coffee Maker"}),
    ]:
        await ha.set_state(entity, "unavailable", attrs)

    codes = notifier.codes()
    for expected in ("leak_detected", "valve_freeze_risk", "prolonged_presence", "mesh_mass_outage"):
        assert expected in codes, f"missing {expected} in delivered alerts: {codes}"

    # Every delivered notification carries which device/area produced it.
    for p in notifier.history:
        assert p["device"] and p["device"] != "unknown", p
        assert p["area"], p
        assert p["system"] == "highline-tech", p

    print(f"  delivered {len(notifier.history)} notifications; codes include "
          f"{sorted(set(codes) & {'leak_detected','valve_freeze_risk','prolonged_presence','mesh_mass_outage'})}")


async def test_notifier_level_filter():
    n = Notifier({"min_level": "warning"})
    await n.emit({"device": "x", "area": "y", "level": "info", "code": "noise", "message": "m"})
    await n.emit({"device": "x", "area": "y", "level": "critical", "code": "real", "message": "m"})
    assert n.codes() == ["real"], n.codes()


async def test_disabled_device_not_started():
    config = load_config(CONFIG)
    # Disable one device and confirm it is not wired.
    for dev in config["devices"]:
        if dev["type"] == "reolink-camera-bundle":
            dev["enabled"] = False
    system = run.build_system(config, Notifier({}))
    types = [t for t, _, _ in system.monitors]
    assert "reolink-camera-bundle" not in types, types
    assert len(system.monitors) == 9, types


class _BoomMonitor:
    """A monitor whose handlers always raise -- used to prove loop isolation."""

    def __init__(self):
        self.alerts: list[dict] = []

    async def handle_event(self, event, ha):
        raise RuntimeError("boom in handle_event")

    async def check_timeouts(self, ha, now=None):
        raise RuntimeError("boom in check_timeouts")

    async def check_wellness(self, ha, now=None):
        raise RuntimeError("boom in check_wellness")


class _RecordingMonitor:
    """A monitor that just records that it was driven."""

    def __init__(self):
        self.alerts: list[dict] = []
        self.seen: list[str] = []
        self.checks = 0

    async def handle_event(self, event, ha):
        self.seen.append(event["entity_id"])

    async def check_timeouts(self, ha, now=None):
        self.checks += 1

    async def check_wellness(self, ha, now=None):
        self.checks += 1


async def test_dispatch_isolates_a_failing_monitor():
    # One monitor raising on an event must not stop the next monitor (nor the
    # run() event loop). The isolation logs an error; that is expected here.
    logging.getLogger("run").setLevel(logging.CRITICAL)
    system = run.System(Notifier({}))
    good = _RecordingMonitor()
    system.monitors = [("boom", "A", _BoomMonitor()), ("good", "A", good)]
    await system.dispatch({"entity_id": "sensor.x", "new_state": {"state": "1"}},
                          SimulatedHA())
    assert good.seen == ["sensor.x"], "a failing monitor stopped the next one"


async def test_run_checks_isolates_a_failing_monitor():
    # One monitor's periodic check raising must not kill the poller -- a dead poller
    # silently stops every timer-based safety check in the house.
    logging.getLogger("run").setLevel(logging.CRITICAL)
    system = run.System(Notifier({}))
    good = _RecordingMonitor()
    system.monitors = [("boom", "A", _BoomMonitor()), ("good", "A", good)]
    await system.run_checks(SimulatedHA(), now=123.0)   # must not raise
    assert good.checks == 2, "a failing check stopped the others"


TESTS = [
    test_full_house_scenario,
    test_notifier_level_filter,
    test_disabled_device_not_started,
    test_dispatch_isolates_a_failing_monitor,
    test_run_checks_isolates_a_failing_monitor,
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
