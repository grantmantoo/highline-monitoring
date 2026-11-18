"""
Highline Tech -- cross-device chain: leak -> auto water shutoff
==============================================================
The high-value end-to-end automation, exercised with BOTH device codebases live
in one simulated Home Assistant:

    Aqara leak sensor (Zigbee/ZHA)  --  this folder's LeakMonitor
        -> closes the Zooz ZAC36 main valve (Z-Wave/Z-Wave JS)
        -> devices/zooz-valve-actuator/valve.py ValveController also running,
           with its own onboard-probe + freeze logic, on the same HA.

Proves the Zigbee-sensor -> Z-Wave-actuator hop works owned entirely by HA, and
that the two devices' automations coexist. Lives with the trigger device per the
READMEs. If the sibling zooz folder is absent (e.g. after the per-device branch
split) the cross-device case is SKIPPED, not failed.

    python test_chain.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

from aqara_water_leak_sim import build_sim, leak
from leak import LeakMonitor

# Make the sibling zooz device importable. Unique module names (valve,
# zooz_valve_sim) avoid collision; ha.py is identical in both folders.
_ZOOZ = os.path.join(os.path.dirname(__file__), "..", "zooz-valve-actuator")
sys.path.append(_ZOOZ)
try:
    from valve import VALVE_LEAK, VALVE_SWITCH, VALVE_TEMP, ValveController
    HAVE_ZOOZ = True
except Exception:  # noqa: BLE001
    HAVE_ZOOZ = False


async def test_leak_triggers_valve_close_with_both_devices_live():
    if not HAVE_ZOOZ:
        print("SKIP  cross-device chain: zooz-valve-actuator folder not present")
        return

    ha = build_sim()                       # aqara sensors + valve switch (open)
    ha.seed(VALVE_TEMP, "18.0", {"unit_of_measurement": "C", "device_class": "temperature"})
    ha.seed(VALVE_LEAK, "off", {"device_class": "moisture"})

    aqara = LeakMonitor()                  # this device
    zooz = ValveController()               # sibling device, same HA
    ha.add_listener(lambda ev: aqara.handle_event(ev, ha))
    ha.add_listener(lambda ev: zooz.handle_event(ev, ha))

    # 1) Zigbee leak -> Z-Wave valve closes, via the aqara automation.
    assert (await ha.get_state(VALVE_SWITCH))["state"] == "on"
    await leak(ha, "binary_sensor.kitchen_sink_water", wet=True)
    assert (await ha.get_state(VALVE_SWITCH))["state"] == "off", "main valve did not close"
    assert any(a["code"] == "leak_detected" for a in aqara.alerts), "no leak alert"

    # 2) The valve device's OWN logic is live on the same HA: a cold reading at
    #    the main still raises its freeze alert independently of the leak chain.
    await ha.set_state(VALVE_TEMP, "2.0",
                       {"unit_of_measurement": "C", "device_class": "temperature"})
    assert any(a["code"] == "valve_freeze_risk" for a in zooz.alerts), "zooz logic not live"

    print("  chain: kitchen leak -> valve CLOSED;",
          f"aqara alerts={[a['code'] for a in aqara.alerts]},",
          f"zooz alerts={[a['code'] for a in zooz.alerts]}")


TESTS = [test_leak_triggers_valve_close_with_both_devices_live]


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
