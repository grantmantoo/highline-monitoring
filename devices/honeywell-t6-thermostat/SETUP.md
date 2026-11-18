# Honeywell T6 Pro -- Setup Guide

Replacing the wall thermostat, wiring the C-wire, and including it into Z-Wave JS.
**Turn off HVAC power at the breaker before touching thermostat wiring.**

## Prerequisites

- Honeywell Home T6 Pro (Z-Wave) + mounting plate
- A confirmed **C-wire** at the thermostat location (or a C-wire adapter)
- Z-Wave coordinator (Zooz ZST39) running under **Z-Wave JS** in HA
  (see [`doc/install-guide.md`](../../doc/install-guide.md))
- Phone camera, masking tape, small screwdriver

## 1. Swap the thermostat (power off!)

1. **Kill HVAC power at the breaker / furnace switch.** Verify the old thermostat
   is dead.
2. **Photograph the existing wiring** and label each wire with tape (R, Rc, C, W,
   Y, G, ...). Do not rely on wire color alone.
3. Remove the old unit. Mount the T6 backplate; feed the wires through.
4. Land each wire on the matching T6 terminal. **Connect C (common)** -- this is
   the wire that keeps the Z-Wave radio powered.
5. Snap on the T6, restore power, and complete the on-screen HVAC setup (system
   type, stages) per the furnace/AC.

## 2. Include into Z-Wave JS

1. In HA: **Settings -> Devices & Services -> Z-Wave JS -> Add device**
   (inclusion mode).
2. On the thermostat: open the **Z-Wave menu** (Menu -> Z-Wave / "ZWAVE") and
   choose **add/include**.
3. Accept default (non-secure / S2 unauthenticated) -- the T6 does **not** need the
   lock's DSK-PIN S2 flow.
4. Wait for the interview to complete. Name it and set its **Area**.

## 3. Verify

1. Confirm the `climate.<name>` entity exists and reads the room temperature:
   ```bash
   tools/ha-probe.sh climate.<name>
   ```
2. From HA, change the **target temperature** and **mode**; confirm the thermostat
   display and the furnace/AC respond.
3. Confirm `hvac_action` reflects reality (heating vs idle) when it cycles.

## Gotchas

- **No C-wire = unreliable.** Without continuous 24V the thermostat may run on
  borrowed power and drop off Z-Wave intermittently. Add a C-wire adapter rather
  than fighting it.
- **Interview incomplete.** If the `climate` entity is missing values, re-interview
  the node in Z-Wave JS; thermostats sometimes need a second pass.
- **Wrong HVAC config.** If "cool" blows heat or a stage never engages, fix the
  equipment type in the T6's setup menu, not in HA.
- **One coordinator owns the stick.** Don't run the standalone `zwave/` scripts
  against the same stick while HA's Z-Wave JS is using it.
