"""
Highline Tech -- Home Assistant client + simulator
==================================================
One thin async interface for talking to Home Assistant, with two backends:

  * HAClient    -- real REST + WebSocket transport. Point it at a live HA
                   (HA_URL / HA_TOKEN) to drive real hardware.
  * SimulatedHA -- in-memory stand-in that emits realistic state_changed
                   events, so device automations can be exercised with no
                   hardware or HA running. Same idea as the zwave mock-server:
                   the real automation code runs unmodified against a fake.

Device code depends only on this surface, so the backend is swappable:

    state = await ha.get_state("binary_sensor.kitchen_sink_water")
    await ha.set_state("switch.water_main_valve", "off")
    await ha.call_service("switch", "turn_off",
                          {"entity_id": "switch.water_main_valve"})
    async for event in ha.events():        # live state_changed stream
        ...

A state_changed event matches Home Assistant's wire shape:

    {"entity_id": str,
     "old_state": {...} | None,
     "new_state": {"entity_id", "state", "attributes", "last_changed", ...}}

This file is intentionally copied into each device folder so every device is
self-contained (the folders get split onto their own branches later).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

Listener = Callable[[dict], Awaitable[None]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_state(entity_id: str, state, attributes: Optional[dict] = None) -> dict:
    """Build a Home-Assistant-shaped state object."""
    ts = _now()
    return {
        "entity_id": entity_id,
        "state": str(state),
        "attributes": dict(attributes or {}),
        "last_changed": ts,
        "last_updated": ts,
    }


class HAError(RuntimeError):
    pass


def _load_token() -> str:
    """Token from HA_TOKEN, else the file tools/ha-probe.sh reads (~/.ha_token)."""
    token = os.environ.get("HA_TOKEN", "").strip()
    if token:
        return token
    token_file = Path(os.environ.get("HA_TOKEN_FILE", str(Path.home() / ".ha_token")))
    if token_file.is_file():
        return token_file.read_text().strip()
    return ""


# --- real transport ----------------------------------------------------------

class HAClient:
    """Real Home Assistant REST + WebSocket client.

    REST: GET/POST /api/states/<entity_id>, POST /api/services/<domain>/<service>
    WS:   /api/websocket -> auth handshake -> subscribe_events(state_changed)

    aiohttp is imported lazily so the simulator path needs no third-party deps.
    Exercised when pointed at a live HA; with no hardware connected the tests
    drive the automation logic through SimulatedHA instead.
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("HA_URL", "http://localhost:8123")).rstrip("/")
        self.token = token if token is not None else _load_token()
        self._session = None

    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.token}"}
            )
        return self._session

    async def get_state(self, entity_id: str) -> Optional[dict]:
        session = await self._get_session()
        async with session.get(f"{self.base_url}/api/states/{entity_id}") as resp:
            if resp.status == 404:
                return None
            if resp.status >= 300:
                raise HAError(f"get_state {entity_id} -> HTTP {resp.status}")
            return await resp.json()

    async def set_state(self, entity_id: str, state, attributes: Optional[dict] = None) -> dict:
        session = await self._get_session()
        payload = {"state": str(state), "attributes": dict(attributes or {})}
        async with session.post(f"{self.base_url}/api/states/{entity_id}", json=payload) as resp:
            if resp.status >= 300:
                raise HAError(f"set_state {entity_id} -> HTTP {resp.status}")
            return await resp.json()

    async def call_service(self, domain: str, service: str, data: Optional[dict] = None) -> None:
        session = await self._get_session()
        url = f"{self.base_url}/api/services/{domain}/{service}"
        async with session.post(url, json=dict(data or {})) as resp:
            if resp.status >= 300:
                raise HAError(f"call_service {domain}.{service} -> HTTP {resp.status}")

    async def events(self):
        """Yield state_changed event data dicts off the live WebSocket."""
        import aiohttp

        ws_url = self.base_url.replace("http", "ws", 1) + "/api/websocket"
        session = await self._get_session()
        async with session.ws_connect(ws_url, heartbeat=30) as ws:
            hello = await ws.receive_json()
            if hello.get("type") == "auth_required":
                await ws.send_json({"type": "auth", "access_token": self.token})
                ack = await ws.receive_json()
                if ack.get("type") != "auth_ok":
                    raise HAError(f"WS auth failed: {ack}")
            await ws.send_json(
                {"id": 1, "type": "subscribe_events", "event_type": "state_changed"}
            )
            async for raw in ws:
                if raw.type == aiohttp.WSMsgType.TEXT:
                    msg = raw.json()
                    if msg.get("type") == "event":
                        yield msg["event"]["data"]
                elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None


# --- in-memory simulator -----------------------------------------------------

_STOP = object()


class SimulatedHA:
    """In-memory Home Assistant stand-in.

    set_state() updates the store and synchronously fans the resulting
    state_changed event out to every registered listener, so a device's
    handle_event() logic runs against simulated events with deterministic,
    causal ordering (no sleeps, no races). call_service() records every call
    and applies built-in switch/valve effects so a commanded valve close or
    plug toggle actually moves the entity's state in the sim.
    """

    def __init__(self):
        self._states: dict[str, dict] = {}
        self._listeners: list[Listener] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self.services: list[tuple[str, str, dict]] = []
        self._handlers: dict[tuple[str, str], Callable[[dict], Awaitable[None]]] = {}

    # -- listeners / event stream ------------------------------------------
    def add_listener(self, listener: Listener) -> None:
        self._listeners.append(listener)

    async def events(self):
        """Async stream of state_changed data (parity with HAClient.events)."""
        while True:
            ev = await self._queue.get()
            if ev is _STOP:
                return
            yield ev

    def stop(self) -> None:
        self._queue.put_nowait(_STOP)

    # -- state -------------------------------------------------------------
    def seed(self, entity_id: str, state, attributes: Optional[dict] = None) -> None:
        """Set an initial state WITHOUT firing an event (establish a baseline)."""
        self._states[entity_id] = make_state(entity_id, state, attributes)

    async def get_state(self, entity_id: str) -> Optional[dict]:
        return self._states.get(entity_id)

    async def set_state(self, entity_id: str, state, attributes: Optional[dict] = None) -> dict:
        old = self._states.get(entity_id)
        attrs = attributes if attributes is not None else (old["attributes"] if old else {})
        new = make_state(entity_id, state, attrs)
        self._states[entity_id] = new
        event = {"entity_id": entity_id, "old_state": old, "new_state": new}
        self._queue.put_nowait(event)
        for listener in list(self._listeners):
            await listener(event)
        return new

    # -- services ----------------------------------------------------------
    def register_service(self, domain: str, service: str, handler) -> None:
        self._handlers[(domain, service)] = handler

    async def call_service(self, domain: str, service: str, data: Optional[dict] = None) -> None:
        data = dict(data or {})
        self.services.append((domain, service, data))
        handler = self._handlers.get((domain, service))
        if handler is not None:
            await handler(data)
        else:
            await self._default_service(domain, service, data)

    async def _default_service(self, domain: str, service: str, data: dict) -> None:
        entity_id = data.get("entity_id")
        if not entity_id:
            return
        if domain == "switch" and service in ("turn_on", "turn_off"):
            await self.set_state(entity_id, "on" if service == "turn_on" else "off")
        elif domain == "valve" and service in ("open_valve", "close_valve"):
            await self.set_state(entity_id, "open" if service == "open_valve" else "closed")

    # -- test helpers ------------------------------------------------------
    def calls(self, domain: str, service: str) -> list[dict]:
        return [d for (dm, sv, d) in self.services if dm == domain and sv == service]

    async def close(self):
        return None
