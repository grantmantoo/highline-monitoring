"""
Highline Tech -- Schlage Z-Wave lock control
============================================
Connects to a running zwave-js-server instance and lets you lock,
unlock, or query the status of the Schlage deadbolt.

Usage:
    python lock.py status
    python lock.py lock
    python lock.py unlock
    python lock.py list          # print all nodes and their IDs

Environment variables (or edit DEFAULTS below):
    ZWAVE_SERVER_URL   ws://127.0.0.1:3000  WebSocket URL of zwave-js-server
    ZWAVE_LOCK_NODE_ID  node ID of the Schlage lock (find it with: python lock.py list)

Requirements:
    pip install -r requirements.txt
"""

import asyncio
import os
import sys
from typing import Optional

import aiohttp
from zwave_js_server.client import Client
from zwave_js_server.model.value import SetValueResult

# ---- config -----------------------------------------------------------------

SERVER_URL = os.environ.get("ZWAVE_SERVER_URL", "ws://127.0.0.1:3000")

# Set this to your Schlage node ID after running: python lock.py list
LOCK_NODE_ID: Optional[int] = int(os.environ["ZWAVE_LOCK_NODE_ID"]) \
    if "ZWAVE_LOCK_NODE_ID" in os.environ else None

# Door Lock command class constants
DOOR_LOCK_CC = 98          # CommandClass.DOOR_LOCK
LOCKED_VALUE = 255         # DOOR_SECURED
UNLOCKED_VALUE = 0         # DOOR_UNSECURED

# ---- helpers ----------------------------------------------------------------

def _door_lock_value(node):
    """Return the targetMode Value for the door lock CC, or None."""
    for value in node.values.values():
        if (
            value.command_class == DOOR_LOCK_CC
            and value.property_name == "targetMode"
        ):
            return value
    return None


def _current_mode_value(node):
    """Return the currentMode Value for the door lock CC, or None."""
    for value in node.values.values():
        if (
            value.command_class == DOOR_LOCK_CC
            and value.property_name == "currentMode"
        ):
            return value
    return None


def _is_lock_node(node) -> bool:
    """True if this node exposes the Door Lock command class."""
    return any(v.command_class == DOOR_LOCK_CC for v in node.values.values())


# ---- commands ---------------------------------------------------------------

async def cmd_list(client: Client):
    """Print every Z-Wave node and flag any that look like locks."""
    nodes = client.driver.controller.nodes
    print(f"{'ID':>4}  {'Label':<30}  {'Stage':<20}  {'Lock?'}")
    print("-" * 70)
    for node_id, node in sorted(nodes.items()):
        label = (node.device_config.description if node.device_config else None) or "unknown"
        lock_flag = "YES" if _is_lock_node(node) else ""
        stage = str(node.interview_stage) if node.interview_stage else "unknown"
        print(f"{node_id:>4}  {label:<30}  {stage:<20}  {lock_flag}")
        if node_id != 1:
            ccs = set(v.command_class for v in node.values.values())
            print(f"       Command classes: {sorted(ccs)}")


async def cmd_status(client: Client, node_id: int):
    node = client.driver.controller.nodes.get(node_id)
    if node is None:
        print(f"ERROR: node {node_id} not found. Run 'python lock.py list' to find it.")
        sys.exit(1)

    current = _current_mode_value(node)
    if current is None:
        print(f"ERROR: node {node_id} doesn't expose Door Lock CC.")
        sys.exit(1)

    mode = current.value
    if mode == LOCKED_VALUE:
        print(f"Node {node_id}: LOCKED")
    elif mode == UNLOCKED_VALUE:
        print(f"Node {node_id}: UNLOCKED")
    else:
        print(f"Node {node_id}: mode={mode} (unknown)")


async def cmd_interview(client: Client, node_id: int):
    node = client.driver.controller.nodes.get(node_id)
    if node is None:
        print(f"ERROR: node {node_id} not found.")
        sys.exit(1)
    print(f"Triggering interview for node {node_id}...")
    await node.async_interview()
    print("Interview started -- wait 30-60 seconds then run: python3 lock.py list")


async def cmd_set(client: Client, node_id: int, target_value: int, action: str):
    node = client.driver.controller.nodes.get(node_id)
    if node is None:
        print(f"ERROR: node {node_id} not found.")
        sys.exit(1)

    target = _door_lock_value(node)
    if target is None:
        print(f"ERROR: node {node_id} doesn't expose Door Lock CC.")
        sys.exit(1)

    print(f"Sending {action} to node {node_id}...")
    result: SetValueResult = await node.async_set_value(target.value_id, target_value)  # value_id is "{nodeId}-98-0-targetMode"

    if "SUCCESS" in result.status.name or result.status.name == "WORKING":
        print(f"SUCCESS: {action} command sent.")
    else:
        print(f"FAILED: {result.status.name}")
        sys.exit(1)


# ---- main -------------------------------------------------------------------

async def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0].lower()

    async with aiohttp.ClientSession() as session:
        async with Client(SERVER_URL, session) as client:
            await client.connect()

            # listen() populates client.driver via a background task;
            # driver_ready fires once the initial state is received.
            driver_ready = asyncio.Event()
            listen_task = asyncio.create_task(client.listen(driver_ready))

            print("Waiting for Z-Wave driver...")
            await driver_ready.wait()

            try:
                if command == "list":
                    await cmd_list(client)
                    return

                # All other commands need a node ID
                node_id = LOCK_NODE_ID
                if node_id is None:
                    print(
                        "ERROR: ZWAVE_LOCK_NODE_ID is not set.\n"
                        "Run 'python lock.py list' to find the Schlage node ID, then:\n"
                        "  set ZWAVE_LOCK_NODE_ID=<id>   (Windows)\n"
                        "  export ZWAVE_LOCK_NODE_ID=<id> (bash)"
                    )
                    sys.exit(1)

                if command == "status":
                    await cmd_status(client, node_id)
                elif command == "lock":
                    await cmd_set(client, node_id, LOCKED_VALUE, "LOCK")
                    await cmd_status(client, node_id)
                elif command == "unlock":
                    await cmd_set(client, node_id, UNLOCKED_VALUE, "UNLOCK")
                    await cmd_status(client, node_id)
                elif command == "interview":
                    await cmd_interview(client, node_id)
                else:
                    print(f"Unknown command: {command}")
                    print("Valid commands: list, status, lock, unlock, interview")
                    sys.exit(1)
            finally:
                listen_task.cancel()
                try:
                    await listen_task
                except (asyncio.CancelledError, Exception):
                    pass


if __name__ == "__main__":
    asyncio.run(main())
