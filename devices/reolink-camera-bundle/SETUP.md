# REOLINK Camera Bundle -- Setup Guide

Physically installing the 4 cameras, getting them on the network, and adding them
to Home Assistant. The custom clip-capture pipeline has its own guide in
[`devices/cameras/SETUP.md`](../cameras/SETUP.md); this doc is the hardware + HA
path.

## Prerequisites

- [PoE switch](../netgear-poe-switch/SETUP.md) installed and powered
- [Cat 6 runs](../cat6-cabling/SETUP.md) pulled to each camera location
- A browser or the Reolink app on the LAN for first-time camera config
- Home Assistant up (see [`doc/install-guide.md`](../../doc/install-guide.md))

## 1. Mount and cable each camera

1. Mount bullets at entries/driveway with a clear downward view; mount domes on
   porch ceilings / interior corners for wider coverage.
2. Run the camera's Cat 6 tail to the [PoE switch](../netgear-poe-switch/SETUP.md).
   The camera powers on within ~30s (IR ring glows in low light).
3. For exterior cameras, weatherproof the connector (junction box / boot) and
   drip-loop the cable.

## 2. First-time camera config (per camera)

Do this once per camera from a browser on the same LAN.

1. Find the camera's IP in the router DHCP list, then **assign a static
   reservation** so it never changes. Record it.
2. Browse to `http://<camera-ip>`. Default user `admin`, blank password --
   **set a strong password immediately**.
3. **Enable RTSP:** Network -> Advanced -> Port Settings -> RTSP **554**.
4. **Enable ONVIF** (Network -> Advanced) so the Reolink integration and HA can
   discover it.
5. **Enable motion / AI detection:** Alarm/Detection -> turn on Motion and the
   Person/Vehicle AI; set sensitivity ~50 and draw detection zones to exclude
   roads/trees.
6. **Disable cloud + push** (Settings -> Push / Cloud) to keep the camera local.

Test the RTSP stream before integrating:
```bash
ffplay rtsp://admin:PASSWORD@<camera-ip>:554/h264Preview_01_main
```

## 3. Add to Home Assistant

1. **Settings -> Devices & Services -> Add Integration -> Reolink.**
2. Enter the camera's **static IP**, username `admin`, and the password you set.
3. Repeat for all 4 cameras.
4. For each device, set its **Area** (Front Door, Porch, etc.).
5. Confirm entities exist:
   - `camera.<name>` streams in the dashboard.
   - `binary_sensor.<name>_motion` / `_person` toggle when you walk in frame.
   Verify with:
   ```bash
   tools/ha-probe.sh binary_sensor.<name>_person
   ```

## 4. (Optional) Local clip-capture pipeline

To also record stitched pre/post-motion clips locally, set up the Python monitor
in [`devices/cameras/SETUP.md`](../cameras/SETUP.md) -- it writes MP4s to
`devices/cameras/clips/`. Put each camera's static IP + credentials in
`devices/cameras/config.json`.

## Gotchas

- **Static IP first.** Integrating before reserving the IP means the integration
  breaks the next time DHCP hands out a different address.
- **Person AI vs raw motion.** Use the `_person` binary sensor (not raw `_motion`)
  for alerts to cut false positives from headlights, rain, and pets.
- **Stream won't decode:** force the sub stream (`/h264Preview_01_sub`) or set the
  main stream to H.264 in the camera UI.
- **Camera unavailable in HA:** check the PoE link LED and `ping <camera-ip>`
  first -- it is usually the [cable run](../cat6-cabling/SETUP.md) or PoE budget,
  not the camera.
- **Keep firmware local-only.** Re-check that cloud/push stay disabled after any
  firmware update -- updates sometimes re-enable them.
