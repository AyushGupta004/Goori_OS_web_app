import asyncio
import json
import os
import sys
import time
import urllib.request
import websockets
import httpx

# End-to-end integration verification matching Flutter's RealWindowsBridgeClient flow
async def run_e2e():
    print("=" * 60)
    print("RUNNING COMPLETE END-TO-END CANONICAL BRIDGE VERIFICATION")
    print("=" * 60)

    # 0. Check HTTP port 7890 /health
    health_url = "http://127.0.0.1:7890/health"
    res = urllib.request.urlopen(health_url)
    assert res.status == 200, f"Expected 200 from health, got {res.status}"
    health_data = json.loads(res.read().decode())
    assert health_data["status"] == "ok"
    assert "lan_ips" in health_data
    print(f"[PASS] Task 2: /health endpoint reachable: protocol={health_data['protocol_version']}, IPs={health_data['lan_ips']}")

    # 1. Check HTTP port 7890 /desktop
    desktop_url = "http://127.0.0.1:7890/desktop"
    res = urllib.request.urlopen(desktop_url)
    assert res.status == 200, f"Expected 200 from desktop, got {res.status}"
    print("[PASS] Task 4: /desktop accessible on HTTP port 7890")

    # 2. Check /pair/status to obtain the 6-digit PIN displayed on Nova OS desktop
    status_url = "http://127.0.0.1:7890/pair/status"
    res = urllib.request.urlopen(status_url)
    status_data = json.loads(res.read().decode())
    pin_code = status_data["code"]
    assert len(pin_code) == 6 and pin_code.isdigit(), f"Invalid pin: {pin_code}"
    print(f"[PASS] Task 1: Desktop PIN active: {pin_code} (TTL: {status_data['expires_in']}s)")

    # 3. Simulate Flutter Phone POST /pair
    pair_url = "http://127.0.0.1:7890/pair"
    async with httpx.AsyncClient() as client:
        # 3a. Verify wrong PIN fails
        wrong_code = "000000" if pin_code != "000000" else "999999"
        wrong_res = await client.post(
            pair_url,
            headers={"Content-Type": "application/json", "X-Protocol-Version": "1.0"},
            json={"code": wrong_code, "protocolVersion": "1.0"}
        )
        assert wrong_res.status_code == 200
        wrong_json = wrong_res.json()
        assert wrong_json["success"] is False
        assert "INVALID_PAIRING_CODE" in wrong_json["errorMessage"]
        print(f"[PASS] Task 2: Deliberately wrong code correctly rejected: {wrong_json['errorMessage']}")

        # 3b. Verify incompatible protocol version fails
        compat_res = await client.post(
            pair_url,
            headers={"Content-Type": "application/json", "X-Protocol-Version": "1.0"},
            json={"code": pin_code, "protocolVersion": "9.9"}
        )
        assert compat_res.status_code == 200
        compat_json = compat_res.json()
        assert compat_json["success"] is False
        assert "INCOMPATIBLE_PROTOCOL_VERSION" in compat_json["errorMessage"]
        print(f"[PASS] Task 2: Incompatible protocolVersion correctly rejected: {compat_json['errorMessage']}")

        # 3c. Valid pairing with correct PIN
        pair_res = await client.post(
            pair_url,
            headers={"Content-Type": "application/json", "X-Protocol-Version": "1.0"},
            json={"code": pin_code, "protocolVersion": "1.0"}
        )
        assert pair_res.status_code == 200
        pair_json = pair_res.json()
        assert pair_json["success"] is True, f"Pairing failed: {pair_json}"
        assert pair_json["protocolVersion"] == "1.0"
        session_token = pair_json["sessionToken"]
        device_id = pair_json["deviceId"]
        print(f"[PASS] Task 1: Phone paired successfully with live code {pin_code}. Session token: {session_token[:12]}..., DeviceId: {device_id}")

        # 3d. Verify reusing the same PIN is rejected
        reused_res = await client.post(
            pair_url,
            headers={"Content-Type": "application/json", "X-Protocol-Version": "1.0"},
            json={"code": pin_code, "protocolVersion": "1.0"}
        )
        assert reused_res.status_code == 200
        reused_json = reused_res.json()
        assert reused_json["success"] is False
        assert "INVALID_PAIRING_CODE" in reused_json["errorMessage"]
        print(f"[PASS] Task 2: Reusing already-paired PIN correctly rejected")

    # 4. Simulate Flutter Phone connecting to WebSocket on Port 7891 at /ws
    ws_url = "ws://127.0.0.1:7891/ws"
    async with websockets.connect(ws_url) as ws:
        print(f"[PASS] Task 4: Connected to dedicated WebSocket on port 7891 ({ws_url})")

        # 4a. Authenticate handshake
        auth_msg = {
            "type": "authenticate",
            "token": session_token,
            "protocol_version": "1.0"
        }
        await ws.send(json.dumps(auth_msg))
        auth_res = json.loads(await ws.recv())
        assert auth_res["type"] == "auth_result", f"Unexpected response: {auth_res}"
        assert auth_res["success"] is True, f"Auth failed: {auth_res}"
        assert auth_res["version"] == "1.0"
        print(f"[PASS] Task 2: WebSocket authenticated successfully: device_id={auth_res['device_id']}")

        # 4b. Send command "open terminal"
        req_id = "test-cmd-terminal-99"
        cmd_msg = {
            "type": "command",
            "request_id": req_id,
            "timestamp": int(time.time() * 1000),
            "data": {
                "command": "open terminal",
                "type": "text"
            }
        }
        await ws.send(json.dumps(cmd_msg))
        cmd_res = json.loads(await ws.recv())
        assert cmd_res["type"] == "command_result"
        assert cmd_res["request_id"] == req_id
        assert cmd_res["success"] is True
        assert cmd_res["data"]["status"] == "completed"
        assert cmd_res["data"]["action"]["target"] == "terminal"
        assert cmd_res["data"]["execution_time_ms"] >= 0
        print(f"[PASS] Task 5: Command 'open terminal' succeeded in {cmd_res['data']['execution_time_ms']}ms: {cmd_res['data']['message']}")

        # 4c. Send command "open files"
        await ws.send(json.dumps({
            "type": "command",
            "request_id": "test-cmd-files-1",
            "data": {"command": "open files"}
        }))
        cmd_res = json.loads(await ws.recv())
        assert cmd_res["data"]["action"]["target"] == "files"
        print(f"[PASS] Task 5: Command 'open files' succeeded: {cmd_res['data']['message']}")

        # 4d. Send screenshot command
        await ws.send(json.dumps({
            "type": "command",
            "request_id": "test-cmd-shot-1",
            "data": {"command": "take screenshot"}
        }))
        cmd_res = json.loads(await ws.recv())
        assert cmd_res["data"]["action"]["action"] == "system.screenshot"
        print(f"[PASS] Task 5: Screenshot command succeeded: {cmd_res['data']['message']}")

        # 4e. Send unrecognized command
        await ws.send(json.dumps({
            "type": "command",
            "request_id": "test-cmd-unrec-1",
            "data": {"command": "brew some espresso"}
        }))
        cmd_res = json.loads(await ws.recv())
        assert cmd_res["data"]["status"] == "failed"
        assert cmd_res["data"]["action"]["action"] == "unknown"
        print(f"[PASS] Task 5: Unrecognized command gracefully returned failed/unknown: {cmd_res['data']['message']}")

    # 5. Simulate Flutter Phone Streaming Uploads: /upload/file and /upload/photo
    async with httpx.AsyncClient() as client:
        # File upload
        file_payload = b"Sample streamed document content from phone"
        upload_res = await client.post(
            "http://127.0.0.1:7890/upload/file",
            headers={"Authorization": f"Bearer {session_token}", "X-Protocol-Version": "1.0"},
            files={"file": ("phone_doc.pdf", file_payload, "application/pdf")}
        )
        assert upload_res.status_code == 200, f"Upload file failed: {upload_res.text}"
        assert upload_res.json()["success"] is True
        assert upload_res.json()["path"] == "/uploads/files/mobile/phone_doc.pdf"
        print(f"[PASS] Task 3: Streamed file upload (/upload/file) succeeded: {upload_res.json()['filename']} -> {upload_res.json()['path']}")

        # Photo upload
        photo_payload = b"\xFF\xD8\xFF\xE0...photo binary data..."
        photo_res = await client.post(
            "http://127.0.0.1:7890/upload/photo",
            headers={"Authorization": f"Bearer {session_token}", "X-Protocol-Version": "1.0"},
            files={"photo": ("camera_snap.jpg", photo_payload, "image/jpeg")}
        )
        assert photo_res.status_code == 200, f"Upload photo failed: {photo_res.text}"
        assert photo_res.json()["success"] is True
        assert photo_res.json()["path"] == "/uploads/files/mobile/photos/camera_snap.jpg"
        print(f"[PASS] Task 3: Streamed photo upload (/upload/photo) succeeded: {photo_res.json()['filename']} -> {photo_res.json()['path']}")

    # 6. Verify Files app endpoint /files
    async with httpx.AsyncClient() as client:
        files_res = await client.get("http://127.0.0.1:7890/files")
        assert files_res.status_code == 200
        files_list = files_res.json()["files"]
        file_map = {f["name"]: f["path"] for f in files_list}
        assert "phone_doc.pdf" in file_map
        assert file_map["phone_doc.pdf"] == "/uploads/files/mobile/phone_doc.pdf"
        assert "camera_snap.jpg" in file_map
        assert file_map["camera_snap.jpg"] == "/uploads/files/mobile/photos/camera_snap.jpg"
        print(f"[PASS] Task 6: Files app endpoint /files verified. Found {len(file_map)} uploads in files/mobile/.")

    print("=" * 60)
    print("ALL CANONICAL PROTOCOL ENDPOINTS AND TASKS VERIFIED LIVE!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_e2e())
