"""
Highline Tech -- house monitoring runner
========================================
The orchestrator: the custom software layer this business sells. It reads the
house config, instantiates every configured device's monitor against ONE shared
Home Assistant connection, and runs them all on one event bus so cross-device
automations work (an Aqara leak closes the Zooz valve because both monitors see
the same events and share the same HA). Every monitor's alerts funnel through one
unified Notifier (the elder-care notification path).

Usage:
    python run.py [house.yaml]            # run against a live HA (HA_URL/HA_TOKEN)
    python run.py [house.yaml] --dry-run  # load config, print the wired system, exit
                                          # (no HA connection -- safe with no hardware)

Diagnostics that are not always-on HA monitors -- cat6-cabling (linkcheck.py) and
ainope-usb-extension (placement.py) -- are run on demand, not by this runner.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Bootstrap the shared core (same mechanism the device modules use).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from ha import HAClient                      # noqa: E402
from house_config import load_config         # noqa: E402
from loader import load_module               # noqa: E402
from notifier import Notifier                # noqa: E402

log = logging.getLogger("run")

DEVICES_DIR = Path(__file__).resolve().parent
POLL_SECONDS = float(os.environ.get("HIGHLINE_POLL_SECONDS", "30"))

# device type -> (folder, module basename, monitor class). These are the always-on
# event-driven monitors; the two passive-hardware diagnostics are intentionally absent.
REGISTRY: dict[str, tuple[str, str, str]] = {
    "zooz-valve-actuator": ("zooz-valve-actuator", "valve", "ValveController"),
    "aqara-water-leak": ("aqara-water-leak", "leak", "LeakMonitor"),
    "aqara-temp-humidity": ("aqara-temp-humidity", "climate", "ClimateMonitor"),
    "aqara-door-window": ("aqara-door-window", "doorwindow", "DoorWindowMonitor"),
    "aqara-fp1e-presence": ("aqara-fp1e-presence", "presence", "PresenceMonitor"),
    "honeywell-t6-thermostat": ("honeywell-t6-thermostat", "thermostat", "ThermostatMonitor"),
    "thirdrealm-smart-plugs": ("thirdrealm-smart-plugs", "plugs", "PlugMonitor"),
    "sonoff-zigbee-dongle": ("sonoff-zigbee-dongle", "zigbee_health", "ZigbeeMeshMonitor"),
    "netgear-poe-switch": ("netgear-poe-switch", "poe_health", "PoEHealthMonitor"),
    "reolink-camera-bundle": ("reolink-camera-bundle", "camera_monitor", "CameraMonitor"),
}


def _load_class(device_type: str):
    folder, module, cls_name = REGISTRY[device_type]
    mod = load_module(DEVICES_DIR / folder / f"{module}.py", f"hl_{module}")
    return getattr(mod, cls_name)


class System:
    """The wired set of monitors plus their one shared notifier."""

    def __init__(self, notifier: Notifier):
        self.notifier = notifier
        self.monitors: list[tuple[str, str | None, object]] = []

    def add(self, device_type: str, area: str | None, monitor) -> None:
        # Monitors emit; the notifier decides delivery. Inject which device/area
        # produced the alert so monitors stay ignorant of their place in the house.
        monitor.notifier = self.notifier.sink_for(device_type, area)
        self.monitors.append((device_type, area, monitor))

    def attach(self, ha) -> None:
        """Wire every monitor onto a SimulatedHA bus (deterministic, for tests)."""
        for _, _, m in self.monitors:
            ha.add_listener(lambda ev, m=m: m.handle_event(ev, ha))

    async def dispatch(self, event: dict, ha) -> None:
        # Isolate each monitor: one raising (a failed control call, a bad parse)
        # must never stop the others or kill the run() event loop.
        for dtype, _, m in self.monitors:
            try:
                await m.handle_event(event, ha)
            except Exception:  # noqa: BLE001 -- keep the rest of the house monitored
                log.exception("monitor %s failed handling %s",
                              dtype, event.get("entity_id"))

    async def run_checks(self, ha, now: float | None = None) -> None:
        """Drive each monitor's periodic timer (left-open, wellness, freeze grace).

        Each check is isolated: one monitor raising must not stop the rest nor kill
        the poller's `while True` -- a dead poller silently stops every timer-based
        safety check (no_activity, opening_left_open, freeze grace, ...).
        """
        for dtype, _, m in self.monitors:
            if hasattr(m, "check_timeouts"):
                try:
                    await m.check_timeouts(ha, now)
                except Exception:  # noqa: BLE001
                    log.exception("monitor %s check_timeouts failed", dtype)
            if hasattr(m, "check_wellness"):
                try:
                    await m.check_wellness(ha, now)
                except Exception:  # noqa: BLE001
                    log.exception("monitor %s check_wellness failed", dtype)

    def describe(self) -> str:
        lines = [f"{len(self.monitors)} device monitor(s) wired to one notifier:"]
        for dtype, area, m in self.monitors:
            lines.append(f"  - {dtype:<26} area={area or '-':<14} {type(m).__name__}")
        return "\n".join(lines)


def build_system(config: dict, notifier: Notifier | None = None) -> System:
    """Instantiate a monitor for every enabled device and wire it to the notifier."""
    notifier = notifier or Notifier(config.get("notify", {}))
    system = System(notifier)
    for dev in config.get("devices", []):
        if not dev.get("enabled", True):
            continue
        dtype = dev.get("type")
        if dtype not in REGISTRY:
            log.warning("skipping device type %r (not an always-on monitor)", dtype)
            continue
        cls = _load_class(dtype)
        monitor = cls(**(dev.get("config") or {}))
        system.add(dtype, dev.get("area"), monitor)
        log.info("started %s (%s)", dtype, dev.get("area") or "no area")
    return system


async def run(config_path: str) -> None:
    """Production entry point: one HAClient, all monitors, one event bus."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
    config = load_config(config_path)
    system = build_system(config)
    ha = HAClient()

    async def poller():
        while True:
            await asyncio.sleep(POLL_SECONDS)
            await system.run_checks(ha, time.monotonic())

    log.info("\n%s", system.describe())
    task = asyncio.create_task(poller())
    try:
        async for event in ha.events():
            await system.dispatch(event, ha)
    finally:
        task.cancel()
        await ha.close()


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    config_path = args[0] if args else str(DEVICES_DIR / "house.example.yaml")

    if "--dry-run" in flags:
        logging.basicConfig(level=logging.WARNING)
        system = build_system(load_config(config_path))
        print(f"Config: {config_path}")
        print(system.describe())
        return 0

    asyncio.run(run(config_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
