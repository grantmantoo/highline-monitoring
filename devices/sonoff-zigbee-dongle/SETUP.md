# SONOFF Zigbee Dongle -- Setup Guide

Standing up the Zigbee coordinator in Home Assistant via ZHA. Do this **before**
pairing any Aqara sensors or THIRDREALITY plugs -- they all need this network to
exist first.

## Prerequisites

- Home Assistant OS host up (see [`doc/install-guide.md`](../../doc/install-guide.md))
- SONOFF Zigbee 3.0 Dongle Plus
- [AINOPE USB extension cable](../ainope-usb-extension/SETUP.md)

## 1. Plug in (on the extension)

1. Connect the dongle to the **AINOPE USB extension**, then the extension to a USB
   **2.0** port on the HA host if one is free (2.0 ports radiate less 2.4 GHz noise
   than 3.0).
2. Keep the dongle physically away from the host, any USB 3.0 SSD/hub, and the
   Wi-Fi router.

## 2. Add the ZHA integration

1. **Settings -> Devices & Services -> Add Integration -> Zigbee Home Automation (ZHA).**
2. When prompted for the serial port, pick the dongle. Prefer the
   `/dev/serial/by-id/...` path (stable across reboots) over `/dev/ttyUSB0`.
3. Choose the radio type if asked (`znp` for the `-P`/TI variant, `ezsp` for the
   `-E`/Silabs variant -- check the dongle label).
4. **Set the Zigbee channel** to 15, 20, or 25 to dodge your Wi-Fi. This is much
   easier to choose correctly now than to change later.
5. Let ZHA form the network. The coordinator now shows up under the ZHA
   integration.

## 3. Back up the network

1. ZHA -> Configure -> **Network settings -> Download backup** (or it is captured
   automatically). Save the backup off-device.
2. This backup holds the network key + channel. With it, replacing a dead dongle
   does **not** require re-pairing every device.

## 4. Verify, then pair devices

- Confirm the coordinator is online: ZHA shows it as a device with a "Coordinator"
  badge and a healthy network.
- To add sensors/plugs: ZHA -> **Add Device** (permit-join), then follow each
  device's pairing steps:
  - [Aqara temp/humidity](../aqara-temp-humidity/SETUP.md)
  - [Aqara water leak](../aqara-water-leak/SETUP.md)
  - [Aqara door/window](../aqara-door-window/SETUP.md)
  - [Aqara FP1E presence](../aqara-fp1e-presence/SETUP.md)
  - [THIRDREALITY smart plugs](../thirdrealm-smart-plugs/SETUP.md)
- Pair **mains-powered routers (the plugs) first** so the mesh has range before
  you add distant battery sensors.

## Gotchas

- **Pair order:** routers (plugs) before far-away battery sensors, or the sensors
  may join directly to the coordinator and then drop when out of range.
- **`by-id` path:** if you used `/dev/ttyUSB0` and added another USB serial device,
  a reboot can swap the numbers and break ZHA. Re-add using the `by-id` path.
- **Channel change = re-join.** Changing the Zigbee channel after the fact orphans
  joined devices; set it right the first time.
- **One owner.** Do not also point Zigbee2MQTT or the vendor tool at this dongle
  while ZHA is running.
