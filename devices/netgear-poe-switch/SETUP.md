# NETGEAR GS108LP -- Setup Guide

Physical install and verification for the PoE+ switch. There is no pairing or
firmware step -- this is unmanaged hardware.

## Prerequisites

- NETGEAR GS108LP switch + its power brick
- Router / network with a spare LAN port for the uplink
- Cat 6 runs to each camera location (see [`devices/cat6-cabling`](../cat6-cabling/SETUP.md))
- A UPS to share with the Home Assistant host

## 1. Mount and power

1. Place the switch in a ventilated spot near the router (a wiring shelf or
   closet). It can sit flat or wall-mount via the keyhole slots on the underside.
2. Plug the power brick into the **UPS**, not straight to the wall.
3. The **PWR** LED should come on solid.

## 2. Wire it up

1. Run a patch cable from a **router LAN port** to any port on the GS108LP. This
   is the uplink. Label both ends.
2. Plug each camera's Cat 6 drop into ports 1-8. Each port's PoE LED lights once
   the camera negotiates power (give it 10-30s to boot).
3. Confirm the per-port **link LED** is on for every connected camera.

## 3. Verify power and link

- Every camera should power on (IR ring or status LED visible, fan/click on PTZ
  models). If a camera never powers up:
  - Re-seat the cable at both ends.
  - Move it to a different port to rule out a dead port.
  - Check the **PoE budget**: 4 cameras is near the ~60W ceiling. Temporarily
    unplug one camera; if the others stabilize, you are over budget.
- From the Home Assistant host (or any LAN machine), confirm each camera answers:
  ```bash
  ping <camera-ip>
  ```
  Camera IPs come from your router's DHCP table -- assign static reservations
  (see [`devices/reolink-camera-bundle`](../reolink-camera-bundle/SETUP.md)).

## 4. Home Assistant

Nothing to add for the switch itself. Its health is observed indirectly: if the
switch or its uplink fails, the **Reolink camera entities** in HA all go
`unavailable` at once -- a useful single signal that the wired segment is down.

## Gotchas

- **No web UI / no IP.** If you are looking for a login page, you have the wrong
  model -- the GS108LP is unmanaged by design.
- **Power budget creep.** Adding a 5th camera or a PoE access point can silently
  push past 60W and cause intermittent reboots that look like camera faults.
- **Heat.** Do not box it into an unventilated cabinet under full PoE load.
- **One UPS.** Keep the switch, router, and HA host on the same UPS so a flicker
  does not blind the cameras while everything else stays up.
