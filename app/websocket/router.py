from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.websocket.manager import ws_manager

router = APIRouter()
logger = get_logger(__name__)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    client_id = await ws_manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back to the room — replace with real logic later
            await ws_manager.broadcast(
                message=f"[{client_id[:8]}] {data}",
                room_id=room_id,
            )
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id, room_id)
        await ws_manager.broadcast(
            message=f"Client {client_id[:8]} left the room.",
            room_id=room_id,
        )
