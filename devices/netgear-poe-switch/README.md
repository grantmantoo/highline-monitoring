# NETGEAR GS108LP -- PoE+ Switch

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

The wired backbone of the monitoring system. Delivers both data and power over
a single Cat 6 run to each Reolink camera, so the cameras need no separate power
adapters.

See the full bill of materials in [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md).

---

## Hardware

| Field | Value |
|-------|-------|
| Model | NETGEAR GS108LP (8-port Gigabit, 8 PoE+ ports) |
| PoE standard | 802.3af / 802.3at (PoE+) |
| Power budget | ~60W total across all ports |
| Management | Unmanaged (no web UI, no SNMP) |
| Integration method | Wired Ethernet / PoE |

---

## Role

- Powers and connects the 4-camera Reolink system (2x bullet, 2x dome) over PoE.
- Provides the wired uplink between the cameras and the router / Home Assistant host.
- Acts as the aggregation point for all camera Cat 6 runs (see
  [`devices/cat6-cabling`](../cat6-cabling/README.md)).

## Integration method -- PoE / wired

The GS108LP is **unmanaged**: there is nothing to pair and no firmware UI. It is
pure infrastructure. Plug cameras into ports 1-8; each PoE+ port negotiates power
with the camera automatically.

**Power budget matters.** Four Reolink 5MP cameras draw roughly 10-12W each, so
~40-48W against the ~60W budget. That leaves little headroom -- do not hang
additional PoE devices (extra cameras, PoE access points) off this switch without
re-checking the total draw. If cameras randomly reboot, suspect the power budget
first.

## Home Assistant config notes

- The switch itself exposes **no entity** to Home Assistant (unmanaged hardware).
- To monitor that the link is healthy, watch the **cameras** instead: the Reolink
  integration entities (see [`devices/reolink-camera-bundle`](../reolink-camera-bundle/README.md))
  go `unavailable` if PoE or the uplink drops.
- Optional: add a `ping` (or SNMP-capable replacement switch) later if per-port
  power telemetry becomes worth the cost. The GS108LP cannot provide it.
- Give the switch a **static DHCP reservation only if** you later swap to a managed
  model; the GS108LP has no IP of its own.

## Gotchas

- Uplink port: any port works (unmanaged), but keep the run to the router short
  and label it so it is not mistaken for a camera drop.
- Place the switch somewhere ventilated -- PoE switches run warm under load.
- Put it on the same **UPS** as the Home Assistant host so a brief outage does not
  drop the cameras.
