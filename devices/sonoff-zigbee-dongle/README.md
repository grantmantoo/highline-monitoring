# SONOFF Zigbee 3.0 Dongle Plus -- Zigbee Coordinator

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

The radio that runs the entire Zigbee mesh. Every Aqara sensor and THIRDREALITY
plug in the system joins **this one coordinator**. It plugs into the Home
Assistant host over USB.

See the full bill of materials in [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md)
and the radio overview in [`doc/install-guide.md`](../../doc/install-guide.md) (section 2).

---

## Hardware

| Field | Value |
|-------|-------|
| Model | SONOFF Zigbee 3.0 USB Dongle Plus |
| Variants | `-P` (TI CC2652P) or `-E` (Silabs EFR32MG21) -- check the label |
| Band | 2.4 GHz (Zigbee 3.0) |
| Connection | USB-A (use the [AINOPE USB extension](../ainope-usb-extension/README.md)) |
| Integration method | USB -> ZHA (Zigbee Home Automation) |

---

## Role

- Single Zigbee **coordinator** for the install. Forms one mesh that all battery
  and mains Zigbee devices join.
- Mains-powered Zigbee devices (e.g. [THIRDREALITY plugs](../thirdrealm-smart-plugs/README.md))
  act as **routers** and extend the mesh range for the battery sensors.
- Counterpart to the Z-Wave coordinator (Zooz ZST39) -- the two radios are
  independent: Zigbee at 2.4 GHz, Z-Wave at 908 MHz.

## Integration method -- USB / ZHA

- Plug into the HA host on the **[AINOPE USB extension cable](../ainope-usb-extension/README.md)**,
  not directly into the box. This keeps the 2.4 GHz radio clear of USB 3.0 and
  Wi-Fi interference, which is the single biggest cause of flaky Zigbee.
- Home Assistant's **ZHA** integration owns the dongle and runs the Zigbee
  network. (Zigbee2MQTT is the alternative; this install uses ZHA per the install
  guide.)
- **One coordinator owns the stick at a time.** ZHA and Z2M cannot both run on it.

## Home Assistant config notes

- Integration: **Settings -> Devices & Services -> ZHA**. On setup it auto-detects
  the serial port (e.g. `/dev/ttyUSB0` or `/dev/serial/by-id/...`); prefer the
  stable `by-id` path so a reboot can't reassign it.
- Pick a **Zigbee channel away from your Wi-Fi**: channels 15, 20, or 25 avoid the
  busiest 2.4 GHz Wi-Fi. Set this at network formation -- changing it later forces
  devices to re-join.
- Pairing devices: put ZHA into **permit-join** (Add Device), then trigger pairing
  on each sensor/plug. Name each device and assign an **Area**.
- The coordinator appears as a device in ZHA; its "network settings" hold the
  **backup** -- export it (see SETUP), since losing the network key means re-
  pairing everything.

## Gotchas

- **USB 3.0 interference is real.** A coordinator plugged next to a USB 3.0 SSD or
  hub will show dropouts and "device unavailable" churn. The extension cable is not
  optional here.
- **Back up the network.** Export the ZHA backup after the mesh is built; restore
  it if the dongle is ever replaced to avoid re-pairing 10+ devices.
- **Don't move it after the mesh forms.** Relocating the coordinator changes which
  routers are reachable; let the mesh heal for a day after any move.
