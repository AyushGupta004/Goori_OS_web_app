from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PairingRequest(BaseModel):
    code: str
    protocolVersion: Optional[str] = Field(default="1.0")
    protocol_version: Optional[str] = None
    clientId: Optional[str] = None
    client_id: Optional[str] = None

    def get_protocol_version(self) -> str:
        return self.protocol_version or self.protocolVersion or "1.0"

    def get_client_id(self) -> Optional[str]:
        return self.clientId or self.client_id

class PairingResponse(BaseModel):
    success: bool
    deviceId: str = ""
    sessionToken: Optional[str] = None
    refreshToken: Optional[str] = None
    expiresAt: Optional[str] = None
    errorMessage: Optional[str] = None
    protocolVersion: str = "1.0"

class MessageEnvelope(BaseModel):
    type: str
    request_id: Optional[str] = None
    protocol_version: Optional[str] = "1.0"
    timestamp: Optional[int] = None
    token: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class AuthResult(BaseModel):
    type: str = "auth_result"
    success: bool
    device_id: str = ""
    version: str = "1.0"
    error: Optional[str] = None
