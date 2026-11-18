# Highline Tech — Home Monitoring Platform

A custom software layer on top of [Home Assistant](https://www.home-assistant.io/)
that turns a set of off-the-shelf smart-home devices into one coordinated
aging-in-place monitoring system: leak → auto-shutoff, freeze warnings, open-door
and heat-loss alerts, wellness/inactivity checks, network and mesh health, and a
local YOLO camera that reports which room a person moved into.

Built at **Highline Tech MT** (a home-monitoring startup I co-founded in 2026).
This repository is a **curated, sanitized excerpt** of a larger private business
repo — the device/software layer only, with all credentials and per-install
config removed. See [*Scope & honesty*](#scope--honesty) below.

```
                    ┌──────────────────────────────┐
   Home Assistant   │   core/ha.py                 │   SimulatedHA (tests)
   (real hardware)  │   HAClient  ── REST + WS ──┐ │   same interface,
         ▲          └───────────────────────────┼─┘   in-memory events
         │                                      │
         │            one shared connection     ▼
         │        ┌───────────────────────────────────────────┐
         │        │  run.py  — the orchestrator               │
         └────────│  wires every configured device monitor    │
                  │  onto ONE event bus                        │
                  └───────────────────────────────────────────┘
                     │        │         │                │
                 doorwindow  leak     valve   …   cameras/zones
                     │        │         │                │
                     └────────┴────┬────┴────────────────┘
                                   ▼
                        core/notifier.py  — one delivery path
                        (level filter → elder-care payload → webhook)
```

## Why it's built this way

- **One shared Home Assistant interface, two backends.** Every device depends only
  on the thin async surface in [`core/ha.py`](devices/core/ha.py): `get_state`,
  `set_state`, `call_service`, and an `events()` stream. `HAClient` is the real
  REST + WebSocket transport; `SimulatedHA` is an in-memory twin that emits the
  same Home-Assistant-shaped `state_changed` events. **The automation code runs
  unmodified against either**, so the whole system can be exercised with no
  hardware and no live HA.

- **Cross-device automations on one event bus.** [`run.py`](devices/run.py)
  instantiates a monitor for each enabled device against a single connection, so
  monitors that never reference each other still coordinate: an Aqara leak sensor
  closes the Zooz water valve because both see the same events on the same bus.
  The whole-system test asserts exactly this chain.

- **Monitors emit; one notifier delivers.** A monitor never formats its own
  alert — it calls `_alert(level, code, message)`. The single
  [`Notifier`](devices/core/notifier.py) applies level filtering, stamps which
  device/area produced the alert, and delivers (webhook now; email/SMS slot in
  behind the same `emit()`). One place decides delivery for the whole house.

- **Failure isolation.** One monitor raising — a bad parse, a failed control
  call — must not stop the others or kill the event loop that keeps every
  timer-based safety check alive. `dispatch` and `run_checks` isolate each
  monitor and log, and there are tests that prove a deliberately-crashing monitor
  doesn't take its neighbors down.

## Repository layout

```
devices/
  core/            shared HA client + simulator, unified notifier, config + module loaders
  run.py           the orchestrator: config → wired system on one bus
  test_system.py   whole-system test: all monitors on one SimulatedHA, scenario asserted
  house.example.yaml   per-install wiring (which monitors run, which HA entities they watch)

  zwave/           Z-Wave Schlage deadbolt control (zwave-js-server)      [hardware-verified]
  aqara-door-window/   door/window contacts, open-too-long + heat-loss    [hardware-verified]
  cameras/         local YOLO person detection + hallway zone tracking    [hardware-verified]

  aqara-water-leak/  leak → valve auto-shutoff chain                      [simulated]
  zooz-valve-actuator/  water main valve control + freeze watch           [simulated]
  aqara-temp-humidity/  per-room temperature / freeze monitoring          [simulated]
  aqara-fp1e-presence/  presence + wellness / inactivity window           [simulated]
  honeywell-t6-thermostat/  thermostat state monitoring                   [simulated]
  thirdrealm-smart-plugs/   routine-appliance activity                    [simulated]
  sonoff-zigbee-dongle/     Zigbee mesh health, mass-outage detection     [simulated]
  netgear-poe-switch/       PoE/camera uplink health                      [simulated]

.github/workflows/zone-tests.yml   CI for the camera zone + climate logic
```

Each device folder has its own `README.md` (what the hardware is and how it's
integrated), a monitor module, an in-memory **simulator**, and a **test**. Every
device README states its own hardware status — see *Scope & honesty*.

## Running it

No hardware required for any of the below.

```bash
# Show the wired system without connecting to anything
python devices/run.py devices/house.example.yaml --dry-run

# Whole-system test: boot every monitor on one SimulatedHA and assert the
# leak→valve chain, a freeze warning, a wellness event, and a mesh outage
python devices/test_system.py

# Any single device against its own simulator
cd devices/aqara-door-window && python test_aqara_door_window.py

# Drive against a real Home Assistant
HA_URL=http://homeassistant.local:8123 HA_TOKEN=… \
  python devices/run.py devices/house.example.yaml
```

To run against live hardware, copy `house.example.yaml` to `house.yaml` and set
the entity IDs to match your Home Assistant (that file and camera `config.json`
are git-ignored).

## Testing & CI

- **Every device ships a simulator and a test** that runs on the standard library
  alone — fast, deterministic, no hardware, no network.
- **`test_system.py`** is the integration test: all monitors on one simulated bus,
  with a realistic scenario (leak closes the valve, freeze at the main, a
  prolonged-presence wellness event, a Zigbee mass outage) asserted at the single
  delivery path.
- **GitHub Actions** ([`zone-tests.yml`](.github/workflows/zone-tests.yml)) guards
  the camera zone state machine and the temperature card on Python 3.11 and 3.12,
  and fails the build if real camera credentials are ever committed. The vision
  logic (`cameras/zones.py`) is pure standard library so CI runs in seconds
  without pulling in OpenCV/Torch.

```
$ python devices/test_system.py
PASS  test_full_house_scenario
PASS  test_notifier_level_filter
PASS  test_disabled_device_not_started
PASS  test_dispatch_isolates_a_failing_monitor
PASS  test_run_checks_isolates_a_failing_monitor
5/5 passed
```

## Scope & honesty

- **Hardware-verified** (run against the physical device, as stated in each
  folder's README): the **Z-Wave Schlage deadbolt**, the **Aqara door/window
  contacts**, and the **YOLO camera** system (hallway person-detection + zone
  tracking + a live temperature card).
- **Simulated** device monitors are **feature-complete and pass their tests**, but
  were written ahead of a planned hardware rollout and have **not** been installed
  on real hardware. Each such folder's README says so at the top. They're included
  because the architecture — one bus, cross-device chains, unified alerts — is the
  point, and the simulators are how that architecture is validated before any
  hardware ships.
- This is a **sanitized excerpt** of a private business repository, published as a
  portfolio piece with the other founder's agreement. Credentials, per-install
  config, model weights, and all non-engineering material (business, website,
  strategy) have been removed.

## My role

I built this device/software layer: the shared Home Assistant client and its
in-memory twin, the orchestrator and one-bus wiring, the unified notifier, the
per-device monitors and their simulators and tests, the camera zone state machine,
and the CI. AI-assisted development tools were used throughout; I reviewed and own
the code and the design decisions behind it.

— Grant Frandsen
