"""
Zone presence tracking for the hallway camera.

The camera looks down a hallway with rooms opening off it, so someone who walks
into a room leaves frame entirely. That makes "where was she last seen before
she vanished" the signal that matters, not just "where is she now".

Two kinds of region, set by "type" in config:

  dwell   -- somewhere she is visible while staying put (the chair). Entering
             it logs straight away.
  doorway -- a threshold she passes through (bathroom, bedroom). Logged only
             once she vanishes while last seen there, because walking *past* a
             door is not the same as walking *through* it.

Vanishing anywhere else falls through to the configured exit zone ("Gone"),
which for this hallway means the dining table or kitchen off the far end.

Polygons are normalized 0-1 image coordinates so they survive a resolution or
stream change. A person's floor position is the bottom-centre of the bounding
box -- their feet -- not the box centre, which rides up as they near the camera.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

DWELL = "dwell"
DOORWAY = "doorway"


def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting. poly is [(x, y), ...] in the same units as x/y."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


class ZoneTracker:
    """One per camera. update() is called from the detector thread every
    inference frame, including frames with nobody in them -- that is what
    drives the vanish timer."""

    def __init__(self, config: dict, base_dir: Path, camera_id: str, clock=time.time):
        z = config.get("zones", {})
        self.camera_id = camera_id
        self.enabled = z.get("enabled", True)
        self.vanish_seconds = float(z.get("vanish_seconds", 8.0))
        self.exit_zone = z.get("exit_zone", "Gone")
        self.transit_zone = z.get("transit_zone", "Hallway")
        self.regions = [
            (r["name"], r.get("type", DWELL),
             [(float(p[0]), float(p[1])) for p in r["polygon"]])
            for r in z.get("regions", [])
        ]
        self.log_path = base_dir / z.get("log_file", "presence.jsonl")
        self._clock = clock
        self._lock = threading.Lock()
        self._state: str | None = None
        self._since = clock()
        self._last_seen = 0.0
        self._last_doorway: str | None = None

    def zone_for(self, points):
        """First region containing any given point -> (name, type)."""
        for name, kind, poly in self.regions:
            for x, y in points:
                if point_in_polygon(x, y, poly):
                    return name, kind
        return None, None

    def update(self, points):
        """points: normalized (x, y) floor positions of people in this frame."""
        if not self.enabled:
            return
        now = self._clock()

        if points:
            self._last_seen = now
            name, kind = self.zone_for(points)
            if kind == DOORWAY:
                # At the threshold but still visible -- remember it, and wait
                # to see whether she actually goes through.
                self._last_doorway = name
                self._set(self.transit_zone, now)
            else:
                self._last_doorway = None
                self._set(name or self.transit_zone, now)
        elif self._last_seen and (now - self._last_seen) >= self.vanish_seconds:
            self._set(self._last_doorway or self.exit_zone, now)

    def _set(self, name: str, now: float):
        with self._lock:
            if name == self._state:
                return
            prev, held = self._state, now - self._since
            self._state, self._since = name, now
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "camera": self.camera_id,
            "zone": name,
            "previous": prev,
            "held_seconds": round(held, 1) if prev is not None else None,
        }
        log.info("[%s] Zone: %s -> %s", self.camera_id, prev or "(start)", name)
        self._append(record)

    def _append(self, record: dict):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as exc:
            # A failed write must never take the detector down.
            log.warning("[%s] Could not append to %s: %s", self.camera_id, self.log_path, exc)

    @property
    def state(self) -> str | None:
        return self._state
