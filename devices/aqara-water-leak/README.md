# Aqara Water Leak Sensor

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

Battery Zigbee leak detector. Bought as a 3-pack -- one at each water risk point.
Joins the [SONOFF Zigbee coordinator](../sonoff-zigbee-dongle/README.md) and is the
trigger half of the automatic water-shutoff pair with the
[Zooz valve actuator](../zooz-valve-actuator/README.md).

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Aqara Water Leak Sensor (SJCGQ11LM) |
| Detects | Water bridging the two metal contacts on its underside |
| Power | CR2032 coin cell (battery), IP67 housing |
| Band | Zigbee 2.4 GHz |
| Integration method | Zigbee -> ZHA |

---

## Role

- Catch leaks early at the **highest-risk points**: under sinks, behind the
  toilet, at the water heater, washing machine, dishwasher, and sump.
- For elder care, an unnoticed slow leak is a major property + safety risk -- this
  is one of the highest-value sensors in the kit.
- Pairs with the [Zooz valve actuator](../zooz-valve-actuator/README.md): a leak
  event drives an automation that **shuts the main water valve**.

## Integration method -- Zigbee / ZHA

Battery end device on the Zigbee mesh. Effectively instant reporting on a
leak/clear transition (it wakes immediately on contact, unlike the slow climate
sensors).

## Home Assistant config notes

- Pairs via ZHA permit-join (see SETUP). Creates:
  - `binary_sensor.<name>_water` (device class `moisture`) -- `on` = wet.
  - a battery level sensor.
- Assign each unit to its **Area** (e.g. "Water Heater", "Kitchen Sink").
- **Cross-radio automation** (the high-value bit): when any leak `binary_sensor`
  goes `on`, call the [Zooz ZAC36 valve](../zooz-valve-actuator/README.md) to
  close, and send an alert. Zigbee sensor -> Z-Wave actuator, both owned by HA.
- Verify with `tools/ha-probe.sh binary_sensor.<name>_water`.

## Gotchas

- **Contacts must touch the floor.** Detection is via two pads on the underside --
  sit it flat on the floor at the lowest point, not on a shelf or upright.
- **Aqara + third-party routers.** Same picky-router caveat as the other Aqara
  sensors -- pair within good range and confirm it stays online.
- **Test the whole chain, not just the sensor.** After pairing, simulate a leak and
  confirm the valve-close automation actually fires end to end (see SETUP).
- **Battery = silent failure.** Alert on low battery so a leak detector is never
  quietly dead.
