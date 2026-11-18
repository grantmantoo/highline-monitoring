# THIRDREALITY Smart Plugs -- Setup Guide

Pairing the plugs into ZHA. Do these **before** the battery sensors -- as mains
routers they give the Zigbee mesh its range. The
[Zigbee coordinator](../sonoff-zigbee-dongle/SETUP.md) must already be in ZHA.

## Prerequisites

- ZHA network up (SONOFF coordinator paired)
- THIRDREALITY Smart Plug(s)
- The loads you intend to control/monitor (lamp, appliance, heater)

## 1. Plug in (spread them out)

1. Place plugs to **bridge the distance** between the coordinator and the far
   battery sensors -- e.g. one mid-house outlet -- not all in one room.
2. Plug into a standard outlet. The button LED indicates status.

## 2. Pair via ZHA

1. **Settings -> Devices & Services -> ZHA -> Add Device** (permit-join).
2. On the plug, **press and hold the button (~5s)** until the LED blinks rapidly
   (pairing/reset), then release.
3. ZHA discovers it; name it for its **load** ("Coffee Maker") and set its **Area**.
4. Repeat for each plug, pairing the mesh-bridging ones first.

## 3. Verify control + metering

1. Toggle `switch.<name>` from HA and confirm the outlet clicks / the load responds.
2. Turn on a known load and confirm power reports:
   ```bash
   tools/ha-probe.sh sensor.<name>_power
   ```
   It should jump from ~0 W to the load's draw, and the energy total accumulate.

## 4. (Optional) activity / safety automations

- "Appliance used" log when `sensor.<name>_power` crosses a small threshold (an
  activity-of-daily-living signal for the elder-care use case).
- "Heater left on" notify when a heater plug draws power for > N hours.

## Gotchas

- **Pair order matters.** Plugs (routers) before distant battery sensors, or those
  sensors join straight to the coordinator and drop when out of range.
- **Reset vs pair.** A long hold both resets and enters pairing -- if a plug won't
  join, fully reset it and retry with ZHA actively permitting join.
- **Spread for mesh.** All four plugs clustered in one room wastes their routing
  value -- distribute them toward the weak-signal corners.
- **Load limits.** Verify the plug's rated max before driving heaters/large motors.
