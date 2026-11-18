# Aqara Temp & Humidity -- Setup Guide

Pairing and placing the climate sensors. The
[Zigbee coordinator](../sonoff-zigbee-dongle/SETUP.md) must already be set up in
ZHA.

## Prerequisites

- ZHA network up (SONOFF coordinator paired)
- Aqara Temp + Humidity sensor(s), battery tab pulled / fresh CR2032
- A paperclip or fingernail for the reset button

## 1. Place (provisionally)

1. Pick a spot ~1.2-1.5 m off the floor, out of direct sun and away from vents,
   radiators, and exterior doors (those skew the reading).
2. Stay within solid Zigbee range of the coordinator or a known-good router for
   the first pairing -- you can relocate slightly once it is stable.

## 2. Pair via ZHA

1. In HA: **Settings -> Devices & Services -> ZHA -> Add Device** (starts
   permit-join).
2. On the sensor, **press and hold the reset button (~5s)** until the LED blinks,
   then release. It blinks while joining.
3. ZHA discovers it; **name it for its room** (e.g. "Bedroom Temp") and set its
   **Area**.
4. Repeat for each sensor in the 3-pack.

## 3. Verify data flow

1. Developer Tools -> States, or:
   ```bash
   tools/ha-probe.sh sensor.<name>_temperature
   tools/ha-probe.sh sensor.<name>_humidity
   ```
2. Confirm: value present, **units correct**, and it **changes over time** (breathe
   on it / move it to a warmer spot to force a change). Battery sensors can take a
   few minutes for the first post-pair update.

## 4. Finalize placement

Once it reports reliably, mount it at the final spot with the included sticker or a
small shelf. Re-confirm it is still reporting from the final location (range can
change behind furniture / inside a cabinet).

## Gotchas

- **Dropped after a few hours?** Classic Aqara-vs-router issue -- re-pair closer to
  the coordinator or a compatible router. See the README note.
- **Reset hold too short.** If it never enters pairing, hold the button longer
  (until the LED does a multi-blink), and make sure ZHA is actively permitting
  join (the window times out).
- **Reading runs warm.** Mounted on an interior wall above an outlet or near
  electronics, it can read a degree or two high -- place it on a free-air surface.
- **Low-battery alert.** Add an automation on the battery entity now so a dead cell
  doesn't go unnoticed.
