# Zooz ZAC36 Titan -- Z-Wave Water Valve Actuator

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

Motorized actuator that physically turns an existing quarter-turn ball valve to
**shut off the house water**. It is the action half of the auto-shutoff pair with
the [Aqara water leak sensors](../aqara-water-leak/README.md). Joins the **Zooz
ZST39 Z-Wave coordinator** via Z-Wave JS.

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM and
[`../zwave/README.md`](../zwave/README.md) for Z-Wave coordinator background.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Zooz ZAC36 Titan Water Valve Actuator |
| Action | Opens/closes a mounted quarter-turn ball valve (motorized) |
| Power | Included DC power adapter (mains-powered, acts as a Z-Wave repeater) |
| Extras | Onboard temperature + inputs for Zooz leak/temp probes; manual override |
| Band | Z-Wave Long Range / Z-Wave (908 MHz) |
| Integration method | Z-Wave -> Z-Wave JS |

---

## Role

- Automatic **whole-house water shutoff**. The single highest-impact failsafe in
  the kit: a leak with nobody home becomes a closed valve instead of a flooded
  house.
- Driven by the [Aqara leak sensors](../aqara-water-leak/README.md) via a Home
  Assistant automation (Zigbee leak -> Z-Wave valve close).
- Can also act on its **own** attached leak/temp probes and includes freeze-temp
  awareness near the valve.

## Integration method -- Z-Wave / Z-Wave JS

- Included into the same Z-Wave network as the [lock](../zwave/README.md) and
  [thermostat](../honeywell-t6-thermostat/README.md), owned by HA's **Z-Wave JS**
  in production (one coordinator at a time -- see
  [`doc/install-guide.md`](../../doc/install-guide.md)).
- Supports Z-Wave Long Range; include it the same way as a classic node unless you
  are explicitly running an LR network.

## Home Assistant config notes

- After inclusion, Z-Wave JS exposes:
  - a **`switch.<name>`** (or `valve.<name>`) for open/close,
  - a **temperature** sensor (valve/ambient),
  - config parameters for auto-shutoff behavior and the attached probes.
- Assign it to an **Area** ("Water Main").
- **The automation that matters:** any `binary_sensor.*_water` -> `on` closes this
  valve and sends an alert. Keep **reopen manual** (a human verifies the leak is
  resolved first).
- Verify with `tools/ha-probe.sh switch.<name>`.

## Gotchas

- **Valve fit.** The ZAC36 mounts on an existing **quarter-turn ball valve** within
  its supported size range. A gate valve (round multi-turn handle) or out-of-range
  ball valve will not work -- plan a plumbing change if needed.
- **Calibrate open/closed.** After mounting, set the open and closed stops so it
  fully seats without stalling the motor.
- **Keep manual override reachable.** Leave the override accessible so water can be
  turned by hand if the actuator or network is down.
- **Test the full chain.** Prove leak-sensor -> valve-close works end to end, not
  just that the switch toggles (see SETUP).
