"""
Highline Tech -- device module loader
=====================================
Device folders have hyphens in their names (aqara-water-leak), so they cannot be
imported as packages. Each monitor module is loaded by file path instead. The
module's own two-line bootstrap puts devices/core on sys.path, so its
`from ha import ...` / `from notifier import ...` resolve to the shared core.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module(path: str | Path, name: str):
    """Import a Python file by path under a unique module name."""
    path = str(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module      # so dataclasses/self-refs resolve
    spec.loader.exec_module(module)
    return module
