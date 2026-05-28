import uuid
from collections import defaultdict

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections.
    Supports broadcasting to all clients or to a specific room.
    """

    def __init__(self) -> None:
        # room_id -> {client_id -> WebSocket}
        self._rooms: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, websocket: WebSocket, room_id: str = "global") -> str:
        await websocket.accept()
        client_id = str(uuid.uuid4())
        self._rooms[room_id][client_id] = websocket
        logger.info("WebSocket connected", client_id=client_id, room=room_id)
        return client_id

    def disconnect(self, client_id: str, room_id: str = "global") -> None:
        self._rooms[room_id].pop(client_id, None)
        if not self._rooms[room_id]:
            del self._rooms[room_id]
        logger.info("WebSocket disconnected", client_id=client_id, room=room_id)

    async def send_personal(self, message: str, websocket: WebSocket) -> None:
        await websocket.send_text(message)

    async def broadcast(self, message: str, room_id: str = "global") -> None:
        dead: list[str] = []
        for client_id, ws in list(self._rooms.get(room_id, {}).items()):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(client_id)
        for cid in dead:
            self.disconnect(cid, room_id)

    @property
    def active_connections(self) -> int:
        return sum(len(clients) for clients in self._rooms.values())


# Singleton — import this where needed
ws_manager = ConnectionManager()
