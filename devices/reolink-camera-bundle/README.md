# REOLINK 5MP PoE Camera Bundle

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

The video layer of the monitoring system: a 4-camera set (2x bullet, 2x dome),
all 5MP PoE. Each camera is a single-cable install -- data and power over one
Cat 6 run from the [PoE switch](../netgear-poe-switch/README.md).

See the full bill of materials in [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md).

---

## Hardware

| Field | Value |
|-------|-------|
| Cameras | 2x REOLINK 5MP PoE Bullet + 2x REOLINK 5MP PoE Dome |
| Resolution | 5MP (2560x1920), H.264/H.265 |
| Power / data | PoE (802.3af), single Cat 6 run each |
| Protocols | RTSP, ONVIF, Reolink HTTP API |
| Integration method | PoE (wired) + RTSP / ONVIF / Reolink integration |

**Bullet vs dome:** bullets are visible and good for entries/driveways with a
clear "this is monitored" signal; domes are lower-profile and good for porches and
wider interior coverage. Mixing both covers the first install.

---

## Role

- Live view + recorded clips of entries and key exterior/interior areas.
- Motion / person events feed automations and alerts -- the elder-care use case
  cares about presence and comings-and-goings, not just intrusion.
- Fully **local**: no Reolink cloud, no subscription. RTSP/ONVIF stay on the LAN.

## Integration method

Two paths, used together:

1. **Reolink integration (Home Assistant, built-in).** Adds a `camera` entity per
   device plus `binary_sensor` motion / person / vehicle detections straight from
   the camera's own AI. Easiest path; no extra compute.
2. **Local capture module (`devices/cameras/`).** Our standalone Python monitor
   polls each camera's motion API and stitches pre/post clips into
   `devices/cameras/clips/`. See [`devices/cameras/SETUP.md`](../cameras/SETUP.md)
   for that pipeline. (Frigate is the heavier alternative if on-box object
   detection with recording is wanted later.)

## Home Assistant config notes

- Integration: **Settings -> Devices & Services -> Add Integration -> Reolink**.
  Point it at each camera's static IP with the admin credentials.
- Entities per camera:
  - `camera.<name>` -- live stream (main + sub).
  - `binary_sensor.<name>_motion`, `..._person`, `..._vehicle` -- AI detections.
- **Assign each camera to an Area** (Front Door, Porch, etc.) so automations and
  the dashboard group correctly. Same convention as the sensors in
  [`doc/install-guide.md`](../../doc/install-guide.md).
- Verify entities with `tools/ha-probe.sh` or Developer Tools -> States.
- RTSP main stream path is typically `/h264Preview_01_main`; sub is
  `/h264Preview_01_sub`. Full RTSP details and the capture pipeline live in
  [`devices/cameras/SETUP.md`](../cameras/SETUP.md).

## Gotchas

- **Set a static IP per camera** (router DHCP reservation) before integrating --
  the Reolink integration keys off IP, and a DHCP change breaks it.
- **Disable the Reolink cloud + push** in the camera UI to keep it local.
- **Power budget:** 4 cameras sit near the GS108LP's ~60W ceiling -- see the
  [switch notes](../netgear-poe-switch/README.md).
- **H.265 vs H.264:** if a client can't decode the stream, force the sub stream or
  switch the main stream to H.264 in the camera UI.
