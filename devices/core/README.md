# devices/core -- shared device core

The pieces every device monitor shares, plus the runner that turns 12 standalone
monitors into one system. This is the custom software layer that sits on top of
Home Assistant.

## What's here

| File | Role |
|------|------|
| `ha.py` | `HAClient` (real HA REST + WebSocket transport) and `SimulatedHA` (in-memory stand-in for tests). Single source of truth -- every device imports from here. |
| `notifier.py` | The unified alert path. `emit_alert(...)` is what each monitor's `_alert` calls; `Notifier` is the one place that turns an alert into an elder-care notification and delivers it (webhook now, email/SMS later). |
| `house_config.py` | Loads the house config (YAML or JSON). |
| `loader.py` | Imports a monitor module by file path (device folders have hyphens, so they aren't importable as packages). |

The runner itself is `devices/run.py` (one level up), so it can load the sibling
device folders.

## How a device imports the core

Device folders have hyphens in their names, so they can't be packages. Each
monitor and sim puts `devices/core` on `sys.path` with a two-line bootstrap and
imports the core modules as top-level (`from ha import ...`, `from notifier import
emit_alert`). The same code therefore runs whether a device is exercised on its
own (`python valve.py`) or wired together by `run.py`.

## Alerts: emit, don't deliver

Monitors **emit** structured alerts and never format their own delivery:

```python
await self._alert(ha, "critical", "leak_detected", "Water at the kitchen sink ...")
# -> emit_alert records {level, code, message} on monitor.alerts and either:
#    * routes to monitor.notifier  (set by run.py -> the one Notifier), or
#    * falls back to an HA persistent_notification when run standalone.
```

`run.py` points every monitor's `.notifier` at one `Notifier`, injecting the
device slug + area, so every alert in the house funnels through a single delivery
decision (level filtering, payload shape, webhook).

## House config format

YAML (preferred) or JSON. See `devices/house.example.yaml`.

```yaml
notify:
  webhook_url: ""      # POST target; empty = log/record only
  min_level: info      # info | warning | critical

devices:
  - type: zooz-valve-actuator    # must match a key in run.py REGISTRY
    area: Water Main             # label carried into every alert from this device
    enabled: true                # optional, default true; false = never started
    config:                      # passed straight to the monitor's constructor
      switch: switch.water_main_valve
      temp: sensor.water_main_valve_temperature
      leak: binary_sensor.water_main_valve_leak
```

- A device absent from `devices:` (or `enabled: false`) is never started.
- `config:` keys are the monitor constructor's keyword arguments; omit it to take
  the monitor's defaults (e.g. `aqara-temp-humidity` watches by device_class and
  needs none).
- The 10 always-on monitors are in `run.py`'s `REGISTRY`. The two passive-hardware
  diagnostics (`cat6-cabling/linkcheck.py`, `ainope-usb-extension/placement.py`)
  are run on demand, not by the runner.

## Running

```bash
python run.py house.yaml            # live HA (HA_URL / HA_TOKEN)
python run.py house.yaml --dry-run  # load config, print the wired system, exit
python test_system.py               # all monitors on one SimulatedHA, scenario asserted
```
