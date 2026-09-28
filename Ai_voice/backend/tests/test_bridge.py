import asyncio
import json
import os
import sys
import time
import unittest
from fastapi.testclient import TestClient

# Ensure root dir is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.main import app
from backend.auth.pairing_manager import pairing_manager

class TestBridgeProtocol(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_00_health_endpoint(self):
        """Unauthenticated GET /health returns 200 with server network telemetry and ws_urls"""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["protocol_version"], "1.0")
        self.assertIn("device_id", data)
        self.assertIn("http_port", data)
        self.assertIn("ws_port", data)
        self.assertIn("ws_port_bound", data)
        self.assertIsInstance(data["ws_port_bound"], bool)
        self.assertIn("ws_urls", data)
        self.assertIsInstance(data["ws_urls"], list)
        self.assertGreaterEqual(len(data["ws_urls"]), 2)
        self.assertTrue(any(f":{data['ws_port']}/ws" in url for url in data["ws_urls"]))
        self.assertTrue(any(f":{data['http_port']}/ws" in url for url in data["ws_urls"]))
        self.assertIn("lan_ips", data)
        self.assertIsInstance(data["lan_ips"], list)

    def test_01_pin_status(self):
        res = self.client.get("/pair/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("code", data)
        self.assertEqual(len(data["code"]), 6)
        self.assertTrue(data["code"].isdigit())
        self.assertIn("expires_in", data)

    def test_02_pairing_mismatched_protocol_version(self):
        """Case 5: mismatched protocolVersion -> success:false with compatibility error"""
        current_pin = pairing_manager.get_pin_status()["code"]
        res = self.client.post("/pair", json={"code": current_pin, "protocolVersion": "2.0"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("INCOMPATIBLE_PROTOCOL_VERSION", data["errorMessage"])
        self.assertIn("2.0", data["errorMessage"])

    def test_03_pairing_wrong_pin(self):
        """Case 2: wrong PIN -> success:false + INVALID_PAIRING_CODE and latest attempt logged"""
        active_pin = pairing_manager.get_pin_status()["code"]
        wrong_pin = "000000" if active_pin != "000000" else "999999"
        res = self.client.post("/pair", json={"code": wrong_pin, "protocolVersion": "1.0"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("INVALID_PAIRING_CODE", data["errorMessage"])
        self.assertIn("Incorrect 6-digit pairing code", data["errorMessage"])

        # Verify latest attempt is visible in /pair/status
        status_res = self.client.get("/pair/status")
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertIsNotNone(status_data.get("latest_attempt"))
        self.assertEqual(status_data["latest_attempt"]["result"], "wrong_pin")
        self.assertIn("wrong PIN", status_data["latest_attempt"]["message"])

    def test_04_pairing_correct_pin(self):
        """Case 1: correct current PIN -> success:true + token issued"""
        current_pin = pairing_manager.get_pin_status()["code"]
        res = self.client.post("/pair", json={"code": current_pin, "protocolVersion": "1.0"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["sessionToken"])
        self.assertTrue(data["sessionToken"].startswith("win_sec_"))
        self.assertEqual(data["protocolVersion"], "1.0")
        self.assertIsNotNone(data["deviceId"])

        # Store for subsequent tests
        self.__class__.paired_pin = current_pin
        self.__class__.token = data["sessionToken"]

    def test_04b_session_survives_restart_and_revoke(self):
        """Proves that a paired session token survives a server restart, and tests revoke"""
        token = getattr(self.__class__, "token", None)
        self.assertIsNotNone(token, "Token should have been issued in test_04")

        # Verify token is valid before restart
        sess_before = pairing_manager.validate_token(token)
        self.assertIsNotNone(sess_before)

        # Simulate server restart by creating a new PairingManager instance with same storage_file
        from backend.auth.pairing_manager import PairingManager
        restarted_pm = PairingManager(storage_file=pairing_manager.storage_file)

        # Token must survive restart
        sess_after = restarted_pm.validate_token(token)
        self.assertIsNotNone(sess_after, "Persisted session token must validate after server restart")
        self.assertEqual(sess_after["deviceId"], sess_before["deviceId"])

        # Test revoke support via /pair/revoke endpoint
        res_revoke = self.client.post("/pair/revoke", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_revoke.status_code, 200)
        self.assertTrue(res_revoke.json()["success"])

        # After revocation, token must no longer validate in active manager
        self.assertIsNone(pairing_manager.validate_token(token))

        # And after another simulated restart, the revoked token must not load from disk
        after_revoke_pm = PairingManager(storage_file=pairing_manager.storage_file)
        self.assertIsNone(after_revoke_pm.validate_token(token), "Revoked token must not load on next restart")

        # Re-pair to generate a fresh token for subsequent upload and WebSocket tests
        current_pin = pairing_manager.get_pin_status()["code"]
        res = self.client.post("/pair", json={"code": current_pin, "protocolVersion": "1.0"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.__class__.token = res.json()["sessionToken"]

    def test_05_pairing_reused_pin(self):
        """Case 4: reused (already-paired) PIN -> success:false"""
        previously_paired_pin = getattr(self.__class__, "paired_pin", None)
        self.assertIsNotNone(previously_paired_pin)
        
        # Submitting the PIN that was already used in test_04
        res = self.client.post("/pair", json={"code": previously_paired_pin, "protocolVersion": "1.0"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("INVALID_PAIRING_CODE", data["errorMessage"])

    def test_06_pairing_expired_pin(self):
        """Case 3: expired PIN -> success:false"""
        # Generate a fresh PIN, then artificially expire its timestamp
        fresh_pin = pairing_manager.generate_new_pin()
        pairing_manager.code_expires_at = time.time() - 10

        res = self.client.post("/pair", json={"code": fresh_pin, "protocolVersion": "1.0"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("INVALID_PAIRING_CODE", data["errorMessage"])
        self.assertIn("expired", data["errorMessage"])

    def test_07_uploads_require_auth(self):
        # Without token -> 401 JSON response
        res = self.client.post("/upload/file", files={"file": ("unauth.txt", b"hello world")})
        self.assertEqual(res.status_code, 401)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        self.assertIn("detail", res.json())

        res = self.client.post("/upload/photo", files={"photo": ("unauth.jpg", b"image data")})
        self.assertEqual(res.status_code, 401)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        self.assertIn("detail", res.json())

    def test_08_authenticated_uploads(self):
        token = getattr(self.__class__, "token", None)
        if not token:
            current_pin = pairing_manager.get_pin_status()["code"]
            res = self.client.post("/pair", json={"code": current_pin, "protocolVersion": "1.0"})
            token = res.json()["sessionToken"]
            self.__class__.token = token

        # File upload to files/mobile/
        headers = {"Authorization": f"Bearer {token}"}
        res = self.client.post("/upload/file", headers=headers, files={"file": ("hello_bridge.txt", b"Bridge file content")})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["filename"], "hello_bridge.txt")
        self.assertEqual(data["path"], "/uploads/files/mobile/hello_bridge.txt")

        # Photo upload to files/mobile/photos/
        res = self.client.post("/upload/photo", headers=headers, files={"photo": ("camera_snap.jpg", b"\xFF\xD8\xFF\xE0JPEGDATA")})
        self.assertEqual(res.status_code, 200)
        p_data = res.json()
        self.assertTrue(p_data["success"])
        self.assertEqual(p_data["filename"], "camera_snap.jpg")
        self.assertEqual(p_data["path"], "/uploads/files/mobile/photos/camera_snap.jpg")

        # Verify physical disk landing destinations
        from backend.api.http_routes import MOBILE_DIR, PHOTOS_DIR
        self.assertTrue(os.path.exists(os.path.join(MOBILE_DIR, "hello_bridge.txt")), f"File must exist in {MOBILE_DIR}")
        self.assertTrue(os.path.exists(os.path.join(PHOTOS_DIR, "camera_snap.jpg")), f"Photo must exist in {PHOTOS_DIR}")

    def test_09_list_files(self):
        res = self.client.get("/files")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("files", data)
        file_map = {f["name"]: f for f in data["files"]}
        
        self.assertIn("hello_bridge.txt", file_map)
        self.assertEqual(file_map["hello_bridge.txt"]["path"], "/uploads/files/mobile/hello_bridge.txt")
        self.assertEqual(file_map["hello_bridge.txt"]["type"], "file")
        
        self.assertIn("camera_snap.jpg", file_map)
        self.assertEqual(file_map["camera_snap.jpg"]["path"], "/uploads/files/mobile/photos/camera_snap.jpg")
        self.assertEqual(file_map["camera_snap.jpg"]["type"], "photo")

    def test_10_websocket_rejects_command_before_authenticate(self):
        """Explicitly proves that WebSocket rejects command messages sent before authenticate"""
        with self.client.websocket_connect("/ws") as ws:
            unauth_cmd = {
                "type": "command",
                "request_id": "test-unauth-must-fail-1",
                "data": {"command": "open terminal"}
            }
            ws.send_text(json.dumps(unauth_cmd))
            raw_res = ws.receive_text()
            res = json.loads(raw_res)

            self.assertEqual(res["type"], "command_result")
            self.assertFalse(res["success"])
            self.assertEqual(res["request_id"], "test-unauth-must-fail-1")
            self.assertEqual(res["data"]["status"], "failed")
            self.assertEqual(res["data"]["error"], "UNAUTHORIZED")
            self.assertIn("UNAUTHORIZED", res["data"]["message"])

    def test_11_websocket_authenticated_command_flow(self):
        token = getattr(self.__class__, "token", None)
        with self.client.websocket_connect("/ws") as ws:
            # 1. Authenticate with invalid token -> rejected
            ws.send_text(json.dumps({"type": "authenticate", "token": "fake-bad-token"}))
            res = json.loads(ws.receive_text())
            self.assertEqual(res["type"], "auth_result")
            self.assertFalse(res["success"])

            # 2. Authenticate with valid token -> approved
            ws.send_text(json.dumps({"type": "authenticate", "token": token, "protocol_version": "1.0"}))
            res = json.loads(ws.receive_text())
            self.assertEqual(res["type"], "auth_result")
            self.assertTrue(res["success"])
            self.assertEqual(res["version"], "1.0")

            # 3. Send command 'open terminal'
            ws.send_text(json.dumps({
                "type": "command",
                "request_id": "req-term-1",
                "data": {"command": "open terminal"}
            }))
            res = json.loads(ws.receive_text())
            self.assertEqual(res["type"], "command_result")
            self.assertTrue(res["success"])
            self.assertEqual(res["request_id"], "req-term-1")
            self.assertEqual(res["data"]["status"], "completed")
            self.assertEqual(res["data"]["action"]["target"], "terminal")

            # 4. Ping -> Pong
            ws.send_text(json.dumps({"type": "ping"}))
            res = json.loads(ws.receive_text())
            self.assertEqual(res["type"], "pong")

            # 5. Malformed JSON -> error without disconnecting
            ws.send_text("not-a-valid-json-string")
            res = json.loads(ws.receive_text())
            self.assertEqual(res["type"], "error")
            self.assertEqual(res["error"], "MALFORMED_ENVELOPE")

    def test_12_diagnostics_records_non_loopback_request(self):
        """Proves /api/network/diagnostics records non-loopback requests into ring buffer"""
        simulated_ip = "192.168.1.155"
        # Simulate non-loopback phone request via X-Forwarded-For header
        res = self.client.get("/health", headers={"X-Forwarded-For": simulated_ip})
        self.assertEqual(res.status_code, 200)

        diag_res = self.client.get("/api/network/diagnostics")
        self.assertEqual(diag_res.status_code, 200)
        diag = diag_res.json()

        self.assertIn("lan_ips", diag)
        self.assertIn("http_port", diag)
        self.assertIn("ws_port", diag)
        self.assertIn("ws_bound", diag)
        self.assertIn("firewall_rules_ok", diag)
        self.assertIn("mdns_registered", diag)
        self.assertIn("recent_contacts", diag)

        last_contact = diag.get("last_phone_contact")
        self.assertIsNotNone(last_contact)
        self.assertEqual(last_contact["ip"], simulated_ip)
        self.assertEqual(last_contact["method"], "GET")
        self.assertEqual(last_contact["path"], "/health")
        self.assertEqual(last_contact["status"], 200)
        self.assertIn("seconds_ago", last_contact)

    def test_13_client_id_re_pair_replaces_old_session(self):
        """Proves that a new pairing with the same clientId replaces the old session"""
        client_id = "test-phone-install-id-99"

        # Pair 1
        pin1 = pairing_manager.get_pin_status()["code"]
        res1 = self.client.post("/pair", json={"code": pin1, "protocolVersion": "1.0", "clientId": client_id})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["success"])
        token1 = data1["sessionToken"]
        self.assertIsNotNone(pairing_manager.validate_token(token1))

        # Pair 2 with same clientId
        pin2 = pairing_manager.get_pin_status()["code"]
        res2 = self.client.post("/pair", json={"code": pin2, "protocolVersion": "1.0", "clientId": client_id})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        token2 = data2["sessionToken"]

        # Old session must be invalid
        self.assertIsNone(pairing_manager.validate_token(token1), "Previous session for same clientId must be replaced")
        # New session must be valid
        self.assertIsNotNone(pairing_manager.validate_token(token2), "New session must be valid")

    def test_14_expired_sessions_pruning(self):
        """Proves that expired sessions are automatically pruned on manual prune and on write"""
        expired_hash = "test_expired_hash_12345"
        # Directly insert into memory without saving to verify prune_expired_sessions()
        pairing_manager.sessions[expired_hash] = {
            "deviceId": "test-dev",
            "client_id": "test-expired",
            "issued_at": time.time() - 1000,
            "expires_at": time.time() - 10,
            "last_seen": time.time() - 10,
            "is_local": False
        }
        self.assertIn(expired_hash, pairing_manager.sessions)

        # Call prune_expired_sessions
        pruned_count = pairing_manager.prune_expired_sessions()
        self.assertGreaterEqual(pruned_count, 1)
        self.assertNotIn(expired_hash, pairing_manager.sessions)

        # Also prove pruning on write (_save_sessions)
        pairing_manager.sessions[expired_hash] = {
            "deviceId": "test-dev",
            "client_id": "test-expired",
            "issued_at": time.time() - 1000,
            "expires_at": time.time() - 10,
            "last_seen": time.time() - 10,
            "is_local": False
        }
        pairing_manager._save_sessions()
        self.assertNotIn(expired_hash, pairing_manager.sessions)

    @classmethod
    def tearDownClass(cls):
        # Clean up test artifacts
        from backend.api.http_routes import MOBILE_DIR, PHOTOS_DIR
        for p in [os.path.join(MOBILE_DIR, "hello_bridge.txt"), os.path.join(PHOTOS_DIR, "camera_snap.jpg")]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()
