import json
import logging
from typing import Dict, Set, Optional, Any, List
from fastapi import WebSocket
from backend.auth.pairing_manager import pairing_manager

logger = logging.getLogger("connection_manager")

class ConnectionManager:
    def __init__(self):
        # websocket -> { "authenticated": bool, "device_id": str, "client_type": str, "connected_at": float }
        self.connections: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, client_type: str = "unknown"):
        await websocket.accept()
        self.connections[websocket] = {
            "authenticated": False,
            "device_id": "",
            "client_type": client_type,
            "connected_at": None
        }
        print(f"[ConnectionManager] Client connected ({client_type}). Total connections: {len(self.connections)}")

    def disconnect(self, websocket: WebSocket):
        info = self.connections.pop(websocket, None)
        if info and info.get("authenticated"):
            print(f"[ConnectionManager] Authenticated client disconnected ({info.get('device_id')}). Remaining: {len(self.connections)}")
        else:
            print(f"[ConnectionManager] Unauthenticated client disconnected. Remaining: {len(self.connections)}")

    def is_authenticated(self, websocket: WebSocket) -> bool:
        info = self.connections.get(websocket)
        return bool(info and info.get("authenticated"))

    def authenticate_connection(self, websocket: WebSocket, token: str, version: str = "1.0") -> Dict[str, Any]:
        """
        Validates token and protocol version.
        Returns dict for auth_result response.
        """
        if version != "1.0":
            return {
                "type": "auth_result",
                "success": False,
                "device_id": "",
                "version": "1.0",
                "error": f"INCOMPATIBLE_PROTOCOL_VERSION: Protocol mismatch. Server=1.0, Client={version}"
            }

        session = pairing_manager.validate_token(token)
        if not session:
            return {
                "type": "auth_result",
                "success": False,
                "device_id": "",
                "version": "1.0",
                "error": "INVALID_TOKEN: Session token is missing, invalid, or expired."
            }

        device_id = session.get("deviceId", pairing_manager.device_id)
        is_local = session.get("is_local", False)
        client_type = "desktop" if is_local else "phone"

        if websocket in self.connections:
            self.connections[websocket]["authenticated"] = True
            self.connections[websocket]["device_id"] = device_id
            self.connections[websocket]["client_type"] = client_type

        print(f"[ConnectionManager] Client authenticated as '{device_id}' (type={client_type})")

        return {
            "type": "auth_result",
            "success": True,
            "device_id": pairing_manager.device_id,
            "version": "1.0",
            "error": None
        }

    def get_authenticated_phone_count(self) -> int:
        return sum(1 for info in self.connections.values() if info.get("authenticated") and info.get("client_type") == "phone")

    def get_authenticated_devices(self) -> List[Dict[str, Any]]:
        devices = []
        for info in self.connections.values():
            if info.get("authenticated"):
                devices.append({
                    "device_id": info.get("device_id"),
                    "client_type": info.get("client_type")
                })
        return devices

    async def broadcast(self, message: Dict[str, Any], exclude: Optional[WebSocket] = None):
        """Broadcasts a JSON-serializable message to all active WebSocket connections."""
        msg_text = json.dumps(message)
        dead_connections = []
        for ws in list(self.connections.keys()):
            if ws != exclude:
                try:
                    await ws.send_text(msg_text)
                except Exception:
                    dead_connections.append(ws)
        
        for dead_ws in dead_connections:
            self.disconnect(dead_ws)

# Global singleton
connection_manager = ConnectionManager()
