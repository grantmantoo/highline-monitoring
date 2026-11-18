# Aqara Door & Window Sensor

> **Status: installed and verified against real hardware.** This code has been
> run against the physical device, not only the simulator.

Battery Zigbee contact sensor (two-part magnet + reed). Bought as a 3-pack -- one
per monitored door/window. Joins the
[SONOFF Zigbee coordinator](../sonoff-zigbee-dongle/README.md).

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Aqara Door and Window Sensor (MCCGQ11LM) |
| Detects | Magnet separation (open) / proximity (closed) |
| Power | CR1632 coin cell (battery) |
| Band | Zigbee 2.4 GHz |
| Integration method | Zigbee -> ZHA |

---

## Role

- Open/closed state for the **front door** and key windows.
- Elder-care signals: front-door comings and goings (paired with presence and the
  [door lock](../zwave/README.md)); a window or exterior door left open (security
  + heat loss, which ties into the [thermostat](../honeywell-t6-thermostat/README.md)).
- Cheap, instant-reporting building block for "is the house buttoned up?" logic.

## Integration method -- Zigbee / ZHA

Battery end device on the Zigbee mesh. Wakes and reports immediately on an
open/close transition.

## Home Assistant config notes

- Pairs via ZHA permit-join (see SETUP). Creates:
  - `binary_sensor.<name>` (device class `opening`/`door`) -- `on` = open.
  - a battery level sensor.
- Assign each to its **Area** and name it for the opening ("Front Door",
  "Kitchen Window").
- Useful automations:
  - Front door opens while no one is expected -> notify.
  - Any window `on` for > N minutes while the [thermostat](../honeywell-t6-thermostat/README.md)
    is heating -> notify "window open, heat running".
  - Door open + [presence](../aqara-fp1e-presence/README.md) -> log a coming/going
    event.
- Verify with `tools/ha-probe.sh binary_sensor.<name>`.

## Gotchas

- **Alignment + gap.** The magnet and body must sit close and parallel; keep the
  gap under ~22 mm when closed or it reads "open" while shut.
- **Body on the frame, magnet on the moving leaf** (so the cable-free magnet rides
  the door/window). Mark the alignment notches before sticking.
- **Aqara + third-party routers.** Same picky-router caveat -- pair within good
  range of the coordinator/compatible router.
- **Low battery alert.** A door sensor stuck "closed" on a dead cell is a silent
  gap -- alert on battery.
