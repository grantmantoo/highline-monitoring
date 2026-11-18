# THIRDREALITY Smart Plugs (Gen3)

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

Mains-powered Zigbee smart plugs with per-outlet **energy monitoring**. Bought as a
4-pack. They do double duty: switchable outlets *and* always-on Zigbee **routers**
that extend the mesh for the battery sensors. Join the
[SONOFF Zigbee coordinator](../sonoff-zigbee-dongle/README.md).

> Folder is `thirdrealm-smart-plugs` (branch name); the brand is **THIRDREALITY**.

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | THIRDREALITY Smart Plug Gen3 (4-pack) |
| Function | On/off relay + per-outlet power/energy metering |
| Power | Mains (plug-in) -- always powered, acts as a Zigbee **router** |
| Band | Zigbee 2.4 GHz |
| Integration method | Zigbee -> ZHA |

---

## Role

- **Control:** switch a lamp, appliance, or space heater on/off and on a schedule.
- **Energy monitoring:** per-outlet wattage -- detect that an appliance is on/off.
- **Mesh backbone:** as mains routers, they extend Zigbee range so distant
  [Aqara battery sensors](../aqara-temp-humidity/README.md) stay connected. **Pair
  these first** so the mesh has reach before the battery sensors join.
- Elder-care angle: appliance power draw is an **activity signal** -- e.g. the
  kettle/coffee maker running each morning confirms routine; a space heater left on
  for hours can trigger a check.

## Integration method -- Zigbee / ZHA

Mains-powered Zigbee router on the ZHA mesh. Reports state and power continuously
(no sleep).

## Home Assistant config notes

- Pairs via ZHA permit-join (see SETUP). Per plug:
  - `switch.<name>` -- on/off control.
  - `sensor.<name>_power` (W), and typically `sensor.<name>_energy` (kWh).
- Assign each to its **Area** and name it for the load ("Kitchen Lamp",
  "Coffee Maker").
- Example automations:
  - Power on `sensor.<name>_power` rising above a threshold -> log "appliance used".
  - A heater plug drawing power for > N hours -> notify.
- Verify with `tools/ha-probe.sh sensor.<name>_power`.

## Gotchas

- **Pair routers first.** Adding the plugs before the far battery sensors gives the
  mesh range; do it in that order.
- **Don't switch off a router you rely on for mesh.** If a plug is also routing for
  a distant sensor, turning the outlet off still keeps the radio powered (it's
  mains) -- but unplugging it drops that mesh path.
- **Energy metering precision.** Treat the power reading as "is it on / roughly how
  much," not a revenue-grade meter.
- **Load rating.** Check the plug's max load before driving a heater or large
  appliance.
