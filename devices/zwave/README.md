# Highline Tech — Z-Wave Lock Control

> **Status: installed and verified against real hardware.** This code has been
> run against the physical device, not only the simulator.

Controls a Schlage BE469ZP Z-Wave lock via a Zooz 800 series USB stick (ZST39).
Uses [zwave-js](https://github.com/zwave-js/node-zwave-js) on the server side and
[zwave-js-server-python](https://github.com/home-assistant-libs/zwave-js-server-python) for the Python scripts.

---

## Hardware

| Part | Model |
|------|-------|
| Lock | Schlage BE469ZP (Touchscreen Deadbolt Z-Wave Plus) |
| USB stick | Zooz 800 Series (ZST39) |

---

## Setup

### 1. Install JS server dependencies

```bash
cd zwave/server
npm install
```

### 2. Install Python dependencies

```bash
cd zwave
pip install -r requirements.txt
```

### 3. Start the server

**macOS / Linux:**
```bash
cd zwave
./start_server.sh /dev/tty.usbserial-XXXXXXXX
```

**Windows:**
```powershell
cd zwave
.\start_server.ps1 COM3
```

Find your serial port:
- macOS: `ls /dev/tty.usbserial-*`
- Linux: `ls /dev/ttyUSB*`
- Windows: Device Manager → Ports (COM & LPT)

On first run the server generates S2 security keys and saves them to
`server/cache/keys.json`. **Back this file up** — losing it means re-pairing
all secure devices.

### 4. Set the lock node ID

After pairing (see below), set the node ID in your shell:

```bash
export ZWAVE_LOCK_NODE_ID=19
```

Add it to your shell profile (`~/.zshrc` or `~/.bashrc`) to make it permanent.

---

## Pairing a lock

The Schlage BE469ZP requires S2 security. The server must be running first.

```bash
python3 pair.py
```

Steps:
1. The script prompts for the **5-digit DSK PIN** — find it on the label on the back of the lock (first 5 digits of the DSK string, e.g. `62289`)
2. Wait for **"Inclusion mode ACTIVE"**
3. Press the **small red button** inside the battery cover once
4. The lock LED will flash, then go green when S2 pairing succeeds
5. The interview runs automatically — the lock may cycle through `Failed` stages as it sleeps and retries; this is normal
6. When it prints **"Paired successfully"**, copy the node ID

The DSK PIN can also be set as an environment variable to skip the prompt:
```bash
export ZWAVE_DSK_PIN=62289
```

---

## Controlling the lock

```bash
python3 lock.py status    # show current lock state
python3 lock.py lock      # lock the deadbolt
python3 lock.py unlock    # unlock the deadbolt
python3 lock.py list      # list all known nodes
python3 lock.py interview # re-run interview on the lock node
```

---

## Maintenance scripts

### Remove stale/failed nodes

If a pairing attempt fails and leaves a ghost node behind:

```bash
python3 cleanup.py
```

Removes all nodes with an incomplete interview. No button press needed.
If a node responds to pings (cleanup.py reports an error), use `exclude.py` instead.

### RF exclusion

For nodes that are alive but need to be removed:

```bash
python3 exclude.py
```

Then press the small red button on the lock once.

---

## Moving the USB stick to a new computer

The Z-Wave network is stored on the stick itself, but the S2 security keys live on disk.
You must copy the keys or the lock will refuse to communicate.

1. Copy the entire `zwave/server/cache/` directory to the new machine
2. Install dependencies (steps 1 and 2 above)
3. Find the serial port name on the new machine (it may differ)
4. Start the server pointing at the correct port

Without `cache/keys.json` the stick will still see the lock on the network but
all encrypted communication will fail and you will need to re-pair.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZWAVE_SERVER_URL` | `ws://127.0.0.1:3000` | URL of the zwave-js-server (for Python scripts) |
| `ZWAVE_PORT` | `COM3` | Serial port of the USB stick (for server) |
| `ZWAVE_SERVER_PORT` | `3000` | WebSocket port the server listens on |
| `ZWAVE_DSK_PIN` | *(prompt)* | 5-digit DSK PIN for S2 pairing |
| `ZWAVE_LOCK_NODE_ID` | `13` | Node ID of the lock |
| `ZWAVE_LOG` | `0` | Set to `1` for full zwave-js debug logging |

---

## Troubleshooting

**Interview stage stays `None` forever**
- The server has no S2 keys configured. Check that `server/cache/keys.json` exists and the server printed `loaded existing security keys` on startup.

**Lock LED goes solid red after pairing**
- S2 bootstrapping failed. Most likely cause: wrong DSK PIN, or the server had no security keys. Wipe `server/cache/`, restart the server (new keys will generate), run `cleanup.py`, then `pair.py`.

**`cleanup.py` errors: "node responded to a ping"**
- The node is alive on the network. Use `exclude.py` instead and press the lock button.

**Interview cycles through `Failed` before completing**
- Normal for battery-powered locks — they sleep aggressively. zwave-js retries automatically. Let it run; it will reach `Complete`.

**Lock locks/unlocks but status reads stale**
- The lock only reports state changes when awake. Manually operate the lock (press a button) to wake it, then check status again.
