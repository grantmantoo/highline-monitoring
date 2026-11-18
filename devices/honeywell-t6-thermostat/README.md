# Honeywell Home T6 Pro -- Z-Wave Thermostat

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

Z-Wave Plus smart thermostat. Replaces the existing wall thermostat and brings
HVAC under Home Assistant control. Joins the **Zooz ZST39 Z-Wave coordinator**
via Z-Wave JS.

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM and
[`../zwave/README.md`](../zwave/README.md) for Z-Wave coordinator/S2
background.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Honeywell Home T6 Pro (Z-Wave, TH6320ZW2003) |
| Controls | Heat / cool / auto, fan, setpoints, schedule |
| Power | 24V **C-wire required** (radio needs continuous power) |
| Band | Z-Wave (908 MHz), Z-Wave Plus |
| Integration method | Z-Wave -> Z-Wave JS |

---

## Role

- Brings the furnace/AC under software control: read room temperature and setpoint,
  set target temperature and mode remotely.
- Elder-care safety: alert if the house drifts too cold/hot (heating failure, a
  setpoint changed by accident), and hold a safe minimum temperature.
- Ties into the [door/window sensors](../aqara-door-window/README.md): "window open
  while heating" alerts, and the room [temp sensors](../aqara-temp-humidity/README.md)
  for cross-checking actual vs. setpoint.

## Integration method -- Z-Wave / Z-Wave JS

- Included into the same Z-Wave network as the [door lock](../zwave/README.md),
  owned by HA's **Z-Wave JS** in production. (The standalone `zwave/` scripts and
  HA cannot own the stick at the same time -- one coordinator at a time, see
  [`doc/install-guide.md`](../../doc/install-guide.md).)
- Z-Wave Plus; inclusion is typically **non-secure or S2 unauthenticated** -- it
  does not need the lock's DSK-PIN S2 flow.

## Home Assistant config notes

- After inclusion, Z-Wave JS exposes a **`climate.<name>`** entity:
  - current temperature, target temperature(s), `hvac_mode` (heat/cool/auto/off),
    `hvac_action` (heating/idle), and fan mode.
- Assign it to the **Area** for the main living space.
- Useful automations:
  - Alert if `current_temperature` < safe-min for > N minutes.
  - Notify if any [window](../aqara-door-window/README.md) is open while
    `hvac_action` is `heating`.
- Verify with `tools/ha-probe.sh climate.<name>`.

## Gotchas

- **C-wire is mandatory.** A Z-Wave thermostat must have continuous 24V (the C
  terminal); battery/2-wire power will not keep the radio alive. Confirm a C-wire
  exists (or add a C-wire adapter) before install.
- **Label the old wiring** before pulling the previous thermostat -- HVAC terminal
  letters (R, C, W, Y, G, etc.) vary.
- **Range.** It is a mains device and acts as a Z-Wave repeater, but a thermostat
  in a far hallway can still be a weak link -- confirm it interviews fully.
- **HVAC type.** Set the equipment/stage configuration on the T6 to match the
  furnace/AC (single vs multi-stage, heat-pump) or modes will misbehave.
