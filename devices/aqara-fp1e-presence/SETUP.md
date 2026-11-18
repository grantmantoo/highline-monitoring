# Aqara FP1E Presence -- Setup Guide

Pairing, mounting, and tuning the mmWave presence sensor. The
[Zigbee coordinator](../sonoff-zigbee-dongle/SETUP.md) must already be in ZHA, and
Home Assistant should be **up to date** (FP1E support is recent).

## Prerequisites

- ZHA network up (SONOFF coordinator paired)
- **Current** Home Assistant / ZHA (confirm FP1E is supported before relying on it)
- FP1E + a 5V USB power source near the mount point
- The included mount / bracket

## 1. Power and provisionally place

1. Pick a corner or wall in the room with a clear view of where people actually
   sit/stand, at roughly the height Aqara recommends, angled slightly down.
2. Power it from USB. Keep it **away from ceiling fans, HVAC vents, and curtains**.

## 2. Pair via ZHA

1. **Settings -> Devices & Services -> ZHA -> Add Device** (permit-join).
2. **Press and hold the reset button (~5-10s)** until the LED indicates pairing;
   release.
3. Confirm ZHA creates an **occupancy/presence** entity (not just a generic
   device). If it comes in bare, your ZHA may be too old -- update and re-pair.
4. Name it for the room and set its **Area**.

## 3. Tune detection

1. Set **sensitivity** and **detection distance** via the device's config entities
   in ZHA -- start at the defaults.
2. Walk the room, then **sit still** for a minute. Confirm presence stays `on`
   while seated (the whole point of mmWave) and clears shortly after you leave.
3. Watch for **false holds**: if presence never clears in an empty room, something
   is moving in view (fan/vent/pet) or sensitivity is too high. Re-aim or lower it.

## 4. Verify

```bash
tools/ha-probe.sh binary_sensor.<name>_occupancy
```

Confirm: `on` when occupied (including stationary), `off` shortly after the room
empties, and stable values otherwise.

## Gotchas

- **Empty room shows occupied** = a fan, vent, curtain, or pet in the detection
  zone, or sensitivity too high. Fix placement first, then tune.
- **Misses a seated person** = bad angle/height or detection distance too short.
  Re-mount per Aqara's diagram and extend the distance.
- **No useful entities after pairing** = ZHA too old for FP1E. Update HA, delete
  the device, and re-pair.
- **Don't relocate to fix tuning.** Adjust the sensitivity/distance entities first;
  only re-mount if the geometry is genuinely wrong.
