import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, UploadFile, File, Form, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse

from backend.auth.pairing_manager import pairing_manager
from backend.protocol.schemas import PairingRequest, PairingResponse
from backend.services.connection_manager import connection_manager
from backend.services.diagnostics_service import diagnostics_service

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MOBILE_DIR = os.path.join(UPLOAD_DIR, "files", "mobile")
PHOTOS_DIR = os.path.join(MOBILE_DIR, "photos")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(MOBILE_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)

def verify_token(authorization: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """Helper to validate bearer token from header or query param."""
    extracted_token = None
    if authorization and authorization.startswith("Bearer "):
        extracted_token = authorization.split("Bearer ", 1)[1].strip()
    elif token:
        extracted_token = token.strip()

    if not extracted_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Unauthorized: Missing authorization token.", "error": "UNAUTHORIZED"}
        )

    session = pairing_manager.validate_token(extracted_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": "Unauthorized: Invalid or expired authorization token.", "error": "UNAUTHORIZED"}
        )
    return session

@router.get("/health")
async def health_endpoint(request: Request):
    """
    CANONICAL WINDOWS BRIDGE PROTOCOL: GET /health
    Unauthenticated health check for reachability testing and network diagnostics.
    """
    from backend.services.mdns_service import get_lan_ipv4_addresses
    http_port = int(os.environ.get("PORT_HTTP", os.environ.get("HTTP_PORT", os.environ.get("PORT", "7890"))))
    ws_port = int(os.environ.get("PORT_WS", os.environ.get("WS_PORT", "7891")))
    lan_ips = get_lan_ipv4_addresses()

    # Determine host for ws_urls fallback
    host = request.url.hostname if (request and request.url and request.url.hostname) else None
    if not host or host in ("0.0.0.0", "127.0.0.1", "localhost"):
        host = lan_ips[0] if lan_ips else "127.0.0.1"

    ws_urls = [
        f"ws://{host}:{ws_port}/ws",
        f"ws://{host}:{http_port}/ws"
    ]

    return {
        "status": "ok",
        "protocol_version": "1.0",
        "device_id": pairing_manager.device_id,
        "http_port": http_port,
        "ws_port": ws_port,
        "ws_port_bound": diagnostics_service.ws_port_bound,
        "ws_urls": ws_urls,
        "lan_ips": lan_ips
    }

@router.post("/pair", response_model=PairingResponse)
async def pair_endpoint(request: Request):
    """
    CANONICAL WINDOWS BRIDGE PROTOCOL: POST /pair
    Accepts 6-digit PIN and validates against current active PIN.
    Returns opaque sessionToken, deviceId, and expiry.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    code = str(body.get("code") or "").strip()
    protocol_version = str(body.get("protocolVersion") or body.get("protocol_version") or "1.0").strip()
    client_id = body.get("clientId") or body.get("client_id")
    if client_id is not None:
        client_id = str(client_id).strip()

    client_ip = request.client.host if (request.client and request.client.host) else "unknown"

    # Validate pairing (PIN validation logic in pairing_manager.pair_device is preserved)
    result = pairing_manager.pair_device(code=code, protocol_version=protocol_version, client_id=client_id)

    # Classify outcome for audit log and pairing visibility
    if result.get("success"):
        outcome = "success"
    else:
        err = result.get("errorMessage") or ""
        if "INCOMPATIBLE_PROTOCOL_VERSION" in err:
            outcome = "version_mismatch"
        elif "expired" in err or "already used" in err:
            outcome = "expired"
        else:
            outcome = "wrong_pin"

    # Log attempt (client IP, time, result). NEVER log raw tokens or PIN!
    attempt_record = pairing_manager.record_attempt(client_ip=client_ip, result=outcome)
    print(f"[Pairing] {attempt_record['message']}")

    return JSONResponse(status_code=status.HTTP_200_OK, content=result)

@router.get("/pair/status")
async def get_pair_status():
    """Returns current active PIN, expiry countdown, latest attempt, and local session info for Nova OS desktop UI."""
    return pairing_manager.get_pin_status()

@router.post("/pair/regenerate")
async def regenerate_pair_code():
    """Forces regeneration of the 6-digit pairing code."""
    new_code = pairing_manager.generate_new_pin()
    return {"success": True, "code": new_code, "status": pairing_manager.get_pin_status()}

@router.post("/pair/revoke")
async def revoke_pair_session(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Revokes a paired session token. Accepts token in Authorization header or JSON body.
    """
    token_to_revoke = None
    if authorization and authorization.startswith("Bearer "):
        token_to_revoke = authorization.split("Bearer ", 1)[1].strip()
    else:
        try:
            body = await request.json()
            token_to_revoke = body.get("token") or body.get("token_hash")
        except Exception:
            pass

    if not token_to_revoke:
        raise HTTPException(status_code=400, detail="Token required to revoke")

    revoked = pairing_manager.revoke_token(token_to_revoke)
    return {"success": revoked, "message": "Session revoked" if revoked else "Token not found"}

@router.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
):
    """
    CANONICAL WINDOWS BRIDGE PROTOCOL: POST /upload/file
    Authenticated streaming file upload to uploads/ directory.
    """
    verify_token(authorization=authorization, token=token)

    safe_filename = os.path.basename(file.filename or f"file_{int(time.time())}.bin")
    file_path = os.path.join(MOBILE_DIR, safe_filename)

    # Stream to disk without buffering entire file in memory
    total_bytes = 0
    chunk_size = 64 * 1024
    with open(file_path, "wb") as buffer:
        while chunk := await file.read(chunk_size):
            buffer.write(chunk)
            total_bytes += len(chunk)

    print(f"[Upload] Streamed file: {safe_filename} ({total_bytes} bytes) to {file_path}")

    return {
        "success": True,
        "filename": safe_filename,
        "size": total_bytes,
        "path": f"/uploads/files/mobile/{safe_filename}",
        "uploaded_at": datetime.now().isoformat()
    }

@router.post("/upload/photo")
async def upload_photo(
    photo: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
):
    """
    CANONICAL WINDOWS BRIDGE PROTOCOL: POST /upload/photo
    Authenticated streaming photo upload to uploads/files/mobile/photos/ directory.
    """
    verify_token(authorization=authorization, token=token)

    safe_filename = os.path.basename(photo.filename or f"photo_{int(time.time())}.jpg")
    photo_path = os.path.join(PHOTOS_DIR, safe_filename)

    # Stream to disk without buffering entire photo in memory
    total_bytes = 0
    chunk_size = 64 * 1024
    with open(photo_path, "wb") as buffer:
        while chunk := await photo.read(chunk_size):
            buffer.write(chunk)
            total_bytes += len(chunk)

    print(f"[Upload] Streamed photo: {safe_filename} ({total_bytes} bytes) to {photo_path}")

    return {
        "success": True,
        "filename": safe_filename,
        "size": total_bytes,
        "path": f"/uploads/files/mobile/photos/{safe_filename}",
        "uploaded_at": datetime.now().isoformat()
    }

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

@router.get("/files")
async def list_files():
    """
    Returns live list of all files and photos stored in uploads/files/mobile/ directory.
    Used by Nova OS Files desktop app.
    """
    file_list = []
    
    # 1. Check general files in uploads/files/mobile/
    if os.path.exists(MOBILE_DIR):
        for item in os.listdir(MOBILE_DIR):
            if item.startswith("."):
                continue
            item_path = os.path.join(MOBILE_DIR, item)
            if os.path.isfile(item_path):
                stat = os.stat(item_path)
                file_list.append({
                    "name": item,
                    "size": stat.st_size,
                    "size_formatted": format_file_size(stat.st_size),
                    "type": "file",
                    "path": f"/uploads/files/mobile/{item}",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

    # 2. Check photos in uploads/files/mobile/photos/
    if os.path.exists(PHOTOS_DIR):
        for item in os.listdir(PHOTOS_DIR):
            if item.startswith("."):
                continue
            item_path = os.path.join(PHOTOS_DIR, item)
            if os.path.isfile(item_path):
                stat = os.stat(item_path)
                file_list.append({
                    "name": item,
                    "size": stat.st_size,
                    "size_formatted": format_file_size(stat.st_size),
                    "type": "photo",
                    "path": f"/uploads/files/mobile/photos/{item}",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })

    # Sort newest first
    file_list.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": file_list, "total": len(file_list)}

@router.get("/pair/devices")
async def get_paired_devices():
    """Returns list of active paired mobile devices with last_seen and paired timestamps for Settings."""
    return {"devices": pairing_manager.get_paired_devices()}

@router.get("/api/network/diagnostics")
async def get_network_diagnostics():
    """
    CANONICAL WINDOWS BRIDGE PROTOCOL: GET /api/network/diagnostics
    Returns detailed LAN adapters, ports, bind statuses, firewall rules check,
    mDNS registration, last phone contact, and recent phone contacts ring buffer.
    """
    http_port = int(os.environ.get("PORT_HTTP", os.environ.get("HTTP_PORT", os.environ.get("PORT", "7890"))))
    ws_port = int(os.environ.get("PORT_WS", os.environ.get("WS_PORT", "7891")))
    adapters = diagnostics_service.get_detailed_lan_adapters()
    fw_check = diagnostics_service.check_firewall_rules()

    return {
        "lan_ips": adapters,
        "http_port": http_port,
        "ws_port": ws_port,
        "ws_bound": diagnostics_service.ws_port_bound,
        "firewall_rules_ok": fw_check["ok"],
        "firewall_info": fw_check,
        "mdns_registered": diagnostics_service.mdns_registered,
        "last_phone_contact": diagnostics_service.get_last_phone_contact(),
        "recent_contacts": diagnostics_service.get_recent_contacts(),
        "last_pairing_attempt": pairing_manager.latest_attempt
    }

@router.get("/api/status")
async def get_bridge_status():
    """Returns bridge server telemetry and live client stats for Settings app."""
    pin_status = pairing_manager.get_pin_status()
    return {
        "status": "online",
        "protocol_version": "1.0",
        "device_id": pairing_manager.device_id,
        "connected_phones": connection_manager.get_authenticated_phone_count(),
        "total_connections": len(connection_manager.connections),
        "active_devices": connection_manager.get_authenticated_devices(),
        "pairing_code": pin_status["code"],
        "pin_expires_in": pin_status["expires_in"],
        "latest_attempt": pin_status.get("latest_attempt"),
        "ws_port_bound": diagnostics_service.ws_port_bound,
        "last_phone_contact": diagnostics_service.get_last_phone_contact(),
        "paired_devices": pairing_manager.get_paired_devices()
    }
