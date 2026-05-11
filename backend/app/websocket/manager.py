"""
WebSocket connection manager.
Maintains a registry of connected frontend clients per channel (symbol).
Broadcasts real-time ticks, signals, and alerts pushed via Redis pub/sub.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # channel → set of WebSocket connections
        self._channels: Dict[str, Set[WebSocket]] = defaultdict(set)
        # WebSocket → set of subscribed channels (for cleanup on disconnect)
        self._client_channels: Dict[WebSocket, Set[str]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self._channels[channel].add(websocket)
        self._client_channels[websocket].add(channel)
        logger.debug("WS client subscribed to channel: %s (total: %d)",
                     channel, len(self._channels[channel]))

    def disconnect(self, websocket: WebSocket):
        for channel in self._client_channels.get(websocket, set()):
            self._channels[channel].discard(websocket)
        self._client_channels.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, channel: str):
        """Subscribe an existing connection to an additional channel."""
        self._channels[channel].add(websocket)
        self._client_channels[websocket].add(channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str):
        self._channels[channel].discard(websocket)
        self._client_channels[websocket].discard(channel)

    async def broadcast(self, channel: str, message: dict):
        """Send message to all subscribers of a channel."""
        dead = set()
        payload = json.dumps(message)
        for ws in list(self._channels.get(channel, set())):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_all(self, message: dict):
        """Broadcast to every connected client (e.g., market status)."""
        payload = json.dumps(message)
        dead = set()
        all_clients = set(self._client_channels.keys())
        for ws in all_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    def client_count(self, channel: str = None) -> int:
        if channel:
            return len(self._channels.get(channel, set()))
        return len(self._client_channels)


ws_manager = ConnectionManager()
