# Zooz ZAC36 Valve Actuator -- Setup Guide

Mounting the actuator on the main shutoff, including it into Z-Wave JS, and wiring
the leak-to-shutoff automation. The most important test here is the **full chain**,
not the device in isolation.

## Prerequisites

- Zooz ZAC36 + included power adapter
- An accessible **quarter-turn ball valve** on the main (within the ZAC36 size
  range) -- confirm valve type before starting
- Z-Wave coordinator (Zooz ZST39) running under **Z-Wave JS** in HA
- [Aqara leak sensors](../aqara-water-leak/SETUP.md) paired (for the chain test)

## 1. Mount on the valve

1. Identify the main shutoff (or a zone valve) -- it must be a **quarter-turn ball
   valve**. If it is a multi-turn gate valve, stop and plan a plumbing swap.
2. Fit the ZAC36 bracket/adapter over the valve handle per the Zooz instructions.
3. Power it from the included adapter (mains). Keep the **manual override**
   accessible.

## 2. Include into Z-Wave JS

1. In HA: **Settings -> Devices & Services -> Z-Wave JS -> Add device**.
2. Put the ZAC36 into inclusion (button per Zooz manual). Accept the offered
   security level.
3. Let the interview finish. Name it ("Water Main Valve") and set its **Area**.

## 3. Calibrate

1. From HA, command **close** then **open**. Watch the physical valve travel fully
   in each direction.
2. If it stalls or doesn't fully seat, set the open/closed stop parameters so the
   motor reaches each end without binding.

## 4. Wire the leak-to-shutoff automation (the point of all this)

1. Create an HA automation:
   - **Trigger:** any `binary_sensor.*_water` -> `on`
     (from the [leak sensors](../aqara-water-leak/SETUP.md)).
   - **Action:** set this valve to **closed** + send a notification.
2. **Test end to end:** wet a leak sensor and confirm the **valve physically
   closes** and the alert arrives. A toggling switch entity is not proof -- watch
   the valve move.
3. Set reopen to **manual** (a person confirms the leak is handled before water is
   restored).

## 5. Verify

```bash
tools/ha-probe.sh switch.<name>
```

Confirm open/close commands work, state reports correctly, and the valve's
temperature sensor reads sane (useful for freeze alerts near the main).

## Gotchas

- **Wrong valve type/size.** Gate valves and oversized/undersized ball valves are
  the #1 install blocker -- verify before mounting.
- **Uncalibrated stops.** Motor stalls or partial closure come from open/closed
  stops not set after mounting.
- **Manual override buried.** Don't box it in -- you must be able to shut water by
  hand if the actuator or Z-Wave is down.
- **Chain not tested.** The whole value is leak -> auto-close. Test it for real and
  re-test after any change to the leak sensors or automation.
