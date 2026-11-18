"""
Zone tracker tests. Runs against the real config.json when present so the
deployed polygons are what gets exercised, and falls back to
config.example.json (same polygons, placeholder credentials) on a fresh
clone. Uses an injected clock, so no waiting and no camera.

    python test_zones.py
"""

import json
import sys
import tempfile
from pathlib import Path

from zones import ZoneTracker

# Points inside the calibrated regions, taken from measured walk-throughs.
BEDROOM = (0.191, 0.991)   # measured vanish point, near-left door
BATHROOM = (0.514, 0.719)  # measured vanish point, right-hand wall corner
MIDHALL = (0.463, 0.588)   # walking the hall, inside no region
FAR_END = (0.416, 0.355)   # far end of hall -> resolves by elimination


def build():
    path = Path("config.json")
    if not path.exists():
        path = Path("config.example.json")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["zones"]["log_file"] = "t.jsonl"
    tmp = Path(tempfile.mkdtemp())
    clock = {"t": 1000.0}
    tr = ZoneTracker(cfg, tmp, "upstairs_hallway", clock=lambda: clock["t"])

    def step(points, dt=1.0):
        clock["t"] += dt
        tr.update(points)

    return tr, step, tmp


def zones_of(tmp):
    return [json.loads(l)["zone"] for l in (tmp / "t.jsonl").read_text().splitlines()]


def test_walks_into_bedroom():
    tr, step, _ = build()
    step([MIDHALL]); step([BEDROOM]); step([], 4)
    assert tr.state == "Bedroom", tr.state


def test_walks_into_bathroom():
    tr, step, _ = build()
    step([MIDHALL]); step([BATHROOM]); step([], 4)
    assert tr.state == "Bathroom", tr.state


def test_far_end_resolves_by_elimination():
    """Not a doorway, so vanishing there falls through to exit_zone."""
    tr, step, _ = build()
    step([MIDHALL]); step([FAR_END]); step([], 4)
    assert tr.state == "Living/Dining", tr.state


def test_passing_a_door_is_not_entering_it():
    """Walking past the bathroom then leaving at the far end must NOT log Bathroom."""
    tr, step, _ = build()
    step([MIDHALL]); step([BATHROOM]); step([MIDHALL]); step([FAR_END]); step([], 4)
    assert tr.state == "Living/Dining", tr.state


def test_brief_dropout_logs_nothing():
    """A sub-threshold detection gap must not produce a transition."""
    tr, step, tmp = build()
    step([BATHROOM]); before = zones_of(tmp)
    step([], 2.0)                      # under vanish_seconds
    step([BATHROOM])
    assert zones_of(tmp) == before, zones_of(tmp)


def test_full_route():
    tr, step, tmp = build()
    step([MIDHALL]); step([BEDROOM]); step([], 4)
    step([BEDROOM]); step([MIDHALL]); step([BATHROOM]); step([], 4)
    step([BATHROOM]); step([MIDHALL]); step([FAR_END]); step([], 4)
    got = [z for z in zones_of(tmp) if z != "Hallway"]
    assert got == ["Bedroom", "Bathroom", "Living/Dining"], got


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
