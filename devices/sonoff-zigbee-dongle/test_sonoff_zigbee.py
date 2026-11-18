"""
Highline Tech -- SONOFF Zigbee mesh-health tests
===============================================
    python test_sonoff_zigbee.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from sonoff_zigbee_sim import build_sim, set_available, set_lqi
from zigbee_health import ZigbeeMeshMonitor


def _wire(ha, mass_threshold=3):
    m = ZigbeeMeshMonitor(mass_threshold=mass_threshold)
    ha.add_listener(lambda ev: m.handle_event(ev, ha))
    return m


async def test_single_drop_alerts_no_mass():
    ha = build_sim()
    m = _wire(ha)
    await set_available(ha, "binary_sensor.front_door", False)
    assert any(a["code"] == "device_dropped" for a in m.alerts)
    assert not any(a["code"] == "mesh_mass_outage" for a in m.alerts)


async def test_recovery_clears():
    ha = build_sim()
    m = _wire(ha)
    await set_available(ha, "binary_sensor.front_door", False)
    await set_available(ha, "binary_sensor.front_door", True)
    assert "binary_sensor.front_door" not in m._offline


async def test_mass_outage_critical():
    ha = build_sim()
    m = _wire(ha, mass_threshold=3)
    for e in ["binary_sensor.water_heater_water", "sensor.bedroom_temperature",
              "switch.coffee_maker", "binary_sensor.living_room_occupancy"]:
        await set_available(ha, e, False)
    mass = [a for a in m.alerts if a["code"] == "mesh_mass_outage"]
    assert len(mass) == 1, f"expected 1 mass-outage alert, got {len(mass)}"
    assert mass[0]["level"] == "critical"


async def test_weak_lqi_alert():
    ha = build_sim()
    m = _wire(ha)
    await set_lqi(ha, "sensor.bedroom_temperature", 18)
    assert any(a["code"] == "weak_link" for a in m.alerts)
    # Recovers above the clear point, then drops again -> re-alert.
    await set_lqi(ha, "sensor.bedroom_temperature", 90)
    await set_lqi(ha, "sensor.bedroom_temperature", 12)
    weak = [a for a in m.alerts if a["code"] == "weak_link"]
    assert len(weak) == 2, f"expected re-alert, got {len(weak)}"


TESTS = [
    test_single_drop_alerts_no_mass,
    test_recovery_clears,
    test_mass_outage_critical,
    test_weak_lqi_alert,
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
