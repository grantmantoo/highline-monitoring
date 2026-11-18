# Aqara FP1E mmWave Presence Sensor

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

USB-powered Zigbee **mmWave** presence sensor. Unlike a PIR, it detects a person
who is **stationary** (sitting, sleeping, standing still) via micro-movement, not
just gross motion. Joins the
[SONOFF Zigbee coordinator](../sonoff-zigbee-dongle/README.md).

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM and
[`doc/internal/sensor-notes.md`](../../doc/internal/sensor-notes.md) for what we
track.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Aqara Presence Sensor FP1E (mmWave / 60 GHz radar) |
| Detects | Presence including stationary occupants; some firmware exposes motion |
| Power | 5V USB (continuous power -- not battery) |
| Band | Zigbee 2.4 GHz |
| Integration method | Zigbee -> ZHA (needs current ZHA with FP1E support) |

---

## Role

- The cornerstone sensor for the **elder-care** use case: "is someone in this
  room, even sitting still?" PIR sensors go dark when a person stops moving;
  mmWave does not.
- Enables occupancy-based logic: room-by-room presence, "no presence anywhere for
  N hours" wellness checks, and lights/automation that don't time out on a
  motionless person.
- Complements the [door/window](../aqara-door-window/README.md) and
  [camera](../reolink-camera-bundle/README.md) signals.

## Integration method -- Zigbee / ZHA

- Joins the Zigbee mesh through ZHA, but is **USB-powered**, so it reports
  continuously and never sleeps.
- **Requires a current Home Assistant / ZHA** with an FP1E quirk -- the FP1E is
  newer than the original FP1. On older ZHA it may pair but expose only a bare
  occupancy bit (or nothing useful). Update HA before relying on it.

## Home Assistant config notes

- Pairs via ZHA permit-join (see SETUP). Primary entity:
  - `binary_sensor.<name>_occupancy` / `_presence` -- `on` while a person is in the
    monitored space.
  - Depending on firmware/quirk: approach/away direction, distance, or motion
    sub-entities, plus config entities for sensitivity and detection distance.
- Assign to its **Area** (room) -- presence is inherently room-scoped.
- Tune **sensitivity** and **detection distance** as entities/options rather than
  moving the device.
- Verify with `tools/ha-probe.sh binary_sensor.<name>_occupancy`.

## Gotchas

- **mmWave sees through small movement, including non-people.** Ceiling fans,
  billowing curtains, HVAC airflow, and pets can hold presence `on`. Aim away from
  fans/vents and tune sensitivity.
- **Placement is everything.** Mount per Aqara's guidance (corner/wall at the
  recommended height and downward tilt) and define the detection zone -- a bad
  angle either misses a seated person or sees the hallway next door.
- **Needs constant USB power.** Plan a nearby USB source; it is not a stick-anywhere
  battery sensor.
- **Update HA first.** FP1E support is recent -- an old install gives a degraded or
  empty device.
