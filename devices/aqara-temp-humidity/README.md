# Aqara Temperature & Humidity Sensor

> **Status: not installed.** The code and tests here are complete and pass
> against the in-memory simulator, but this device is not deployed yet and
> nothing here has been verified against real hardware.

Battery Zigbee sensor reporting temperature, humidity, and barometric pressure.
Bought as a 3-pack -- one per key room. Joins the
[SONOFF Zigbee coordinator](../sonoff-zigbee-dongle/README.md).

See [`doc/hardware-baseline.md`](../../doc/hardware-baseline.md) for the BOM and
[`doc/internal/sensor-notes.md`](../../doc/internal/sensor-notes.md) for what we
track and why.

---

## Hardware

| Field | Value |
|-------|-------|
| Model | Aqara Temperature and Humidity Sensor (WSDCGQ11LM) |
| Measures | Temperature, relative humidity, atmospheric pressure |
| Power | CR2032 coin cell (battery) |
| Band | Zigbee 2.4 GHz |
| Integration method | Zigbee -> ZHA |

---

## Role

- Room-level climate monitoring. For the elder-care use case, abnormal cold/heat
  in a room is a safety signal (heating failure, window left open), not just a
  comfort metric.
- Trend data feeds history graphs and threshold alerts in Home Assistant.

## Integration method -- Zigbee / ZHA

Joins the existing Zigbee mesh through ZHA. Battery end device, so it sleeps and
reports on its own schedule (on meaningful change, plus periodic heartbeats).

## Home Assistant config notes

- Pairs via ZHA permit-join (see SETUP). Creates one device with three entities:
  - `sensor.<name>_temperature` (degC/degF per HA units)
  - `sensor.<name>_humidity` (%)
  - `sensor.<name>_pressure` (hPa)
- Assign each unit to its **Area / room** so dashboards and automations target the
  right space.
- Verify with `tools/ha-probe.sh sensor.<name>_temperature` -- confirm value,
  **correct units**, and that it updates over time (battery sensors update slowly;
  give it time).

## Gotchas

- **Aqara + third-party routers.** Aqara end devices are notoriously picky about
  Zigbee routers and will silently drop if they try to route through some
  non-Aqara mains devices. Pair within good range of the coordinator or an
  Aqara/known-compatible router, and watch for it going `unavailable` a few hours
  after pairing.
- **Slow reporting is normal.** It will not update every second; it reports on
  change and periodically. Don't mistake the heartbeat interval for a fault.
- **Coin cell.** Surface the battery level entity and alert on low battery -- a
  dead CR2032 is a silent failure.
