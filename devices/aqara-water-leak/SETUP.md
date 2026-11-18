# Aqara Water Leak Sensor -- Setup Guide

Pairing, placing, and -- most importantly -- testing the leak-to-shutoff chain.
The [Zigbee coordinator](../sonoff-zigbee-dongle/SETUP.md) must already be in ZHA.

## Prerequisites

- ZHA network up (SONOFF coordinator paired)
- Aqara Water Leak sensor(s), fresh CR2032
- (For the shutoff automation) the [Zooz ZAC36 valve](../zooz-valve-actuator/SETUP.md)
  installed and paired to Z-Wave JS

## 1. Pair via ZHA

1. **Settings -> Devices & Services -> ZHA -> Add Device** (permit-join).
2. On the sensor, **press and hold the reset button (~5s)** until the LED blinks;
   release. It blinks while joining.
3. Name it for its location ("Water Heater Leak") and set its **Area**.
4. Repeat for each sensor.

## 2. Place at the risk points

Sit each sensor **flat on the floor**, contacts down, at the lowest spot where
water would pool first:

- Under each sink (kitchen, bathrooms)
- At the base of the water heater
- Behind/beside the toilet
- Under the washing machine / dishwasher
- In the sump area

## 3. Verify detection

1. Bridge the two underside contacts with a **damp cloth or wet finger**.
2. Confirm `binary_sensor.<name>_water` flips to `on` (wet) within a second:
   ```bash
   tools/ha-probe.sh binary_sensor.<name>_water
   ```
3. Dry the contacts; confirm it returns to `off`.

## 4. Wire up auto-shutoff + alert (the important part)

1. Create an HA automation:
   - **Trigger:** any `binary_sensor.*_water` -> `on`.
   - **Action:** close the [Zooz ZAC36 valve](../zooz-valve-actuator/SETUP.md) +
     send a notification (and optionally announce on any speaker).
2. **Test the full chain:** wet a sensor and confirm the valve actually closes and
   the alert arrives -- do not assume it works because the binary sensor toggled.
3. Decide on auto-reopen policy: usually **manual** reopen after a human checks,
   not automatic.

## Gotchas

- **Flat on floor, contacts down.** Upright or on a shelf, it will never detect.
- **Test the chain, not the sensor.** The sensor toggling proves Zigbee works; it
  does not prove the Z-Wave valve closed. Test end to end.
- **Aqara drop-off.** If it goes `unavailable` hours after pairing, re-pair nearer
  the coordinator (picky-router issue).
- **Low battery alert.** A leak sensor with a dead cell is worse than none --
  alert on battery now.
