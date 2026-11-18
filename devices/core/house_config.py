"""
Highline Tech -- house config loader
====================================
Loads the per-install house config that devices/run.py uses to decide which
device monitors to start and with what real HA entity ids. YAML (preferred) or
JSON; YAML is a superset of JSON so the same loader handles both. PyYAML is used
when present, else a JSON fallback keeps things dependency-free.

See devices/core/README.md for the format.
"""

from __future__ import annotations

from pathlib import Path


def load_config(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml
        data = yaml.safe_load(text)
    except ImportError:
        import json
        data = json.loads(text)
    if not isinstance(data, dict) or "devices" not in data:
        raise ValueError(f"{path}: config must be a mapping with a 'devices' list")
    return data
