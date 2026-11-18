"""
Highline Tech -- Reolink camera-bundle simulator
===============================================
Emits realistic Reolink-integration events: AI person/vehicle/motion detections
(including a repeat inside the cooldown window) and a camera going offline.

    python reolink_camera_sim.py
"""

from __future__ import annotations

import asyncio

# Bootstrap the shared core (single source of truth for HAClient/SimulatedHA).
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "core"))

from ha import SimulatedHA

# 2x bullet + 2x dome.
CAMERAS = {
    "front_door": "Front Door",
    "driveway": "Driveway",
    "porch": "Porch",
    "back_yard": "Back Yard",
}


def build_sim() -> SimulatedHA:
    """Seed each camera idle with all detections clear."""
    ha = SimulatedHA()
    for cam, name in CAMERAS.items():
        ha.seed(f"camera.{cam}", "idle", {"friendly_name": name})
        for kind in ("person", "vehicle", "motion"):
            ha.seed(f"binary_sensor.{cam}_{kind}", "off",
                    {"device_class": kind if kind != "person" else "motion",
                     "friendly_name": f"{name} {kind.capitalize()}"})
    return ha


async def detect(ha: SimulatedHA, camera: str, kind: str, active: bool = True) -> None:
    name = CAMERAS.get(camera, camera)
    await ha.set_state(f"binary_sensor.{camera}_{kind}", "on" if active else "off",
                       {"friendly_name": f"{name} {kind.capitalize()}"})


async def set_camera_online(ha: SimulatedHA, camera: str, online: bool) -> None:
    name = CAMERAS.get(camera, camera)
    await ha.set_state(f"camera.{camera}", "idle" if online else "unavailable",
                       {"friendly_name": name})


# --- standalone demo ---------------------------------------------------------

async def _demo() -> None:
    from camera_monitor import CameraMonitor

    ha = build_sim()
    m = CameraMonitor()
    clk = {"t": 1000.0}
    m._clock = lambda: clk["t"]
    ha.add_listener(lambda ev: m.handle_event(ev, ha))

    print("Person at the front door, then again 5s later (within cooldown):")
    await detect(ha, "front_door", "person", True)
    await detect(ha, "front_door", "person", False)
    clk["t"] += 5
    await detect(ha, "front_door", "person", True)
    print(f"  alerts: {[a['code'] for a in m.alerts]}  (one, deduped)")

    print("\nVehicle in the driveway:")
    await detect(ha, "driveway", "vehicle", True)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")

    print("\nPorch camera goes offline:")
    await set_camera_online(ha, "porch", False)
    print(f"  alerts: {[a['code'] for a in m.alerts]}")


if __name__ == "__main__":
    asyncio.run(_demo())
