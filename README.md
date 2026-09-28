# Nova OS — Windows AI Bridge

Production Windows-side bridge server (FastAPI) and browser-based desktop environment (**Nova OS**) for remote AI automation, voice/text command execution, and streaming media uploads from the companion **Windows Remote** Flutter client.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |   Flutter Android ("Windows Remote")  |
                      +-------------------+-------------------+
                                          |
                   mDNS (_winbridge._tcp) | Host IP (7890 HTTP / 7891 WS)
                                          v
+----------------------------------------------------------------------------------+
| Windows Machine ("Ai_voice")                                                     |
|                                                                                  |
|   +------------------------------------+   +---------------------------------+   |
|   | HTTP Server (Port 7890)            |   | Dedicated WebSocket (Port 7891) |   |
|   | - POST /pair                       |   | - /ws                           |   |
|   | - POST /upload/file (Bearer auth)  |   |   * Authenticate handshake      |   |
|   | - POST /upload/photo (Bearer auth) |   |   * Real-time command router    |   |
|   | - GET  /files (Live folder tree)   |   |   * Action dispatch             |   |
|   | - GET  /desktop (Nova OS UI)       |   | - (Port 7890 /ws dual-fallback) |   |
|   +-----------------+------------------+   +----------------+----------------+   |
|                     |                                       |                    |
|                     |              +------------------------+                    |
|                     v              v                                             |
|   +--------------------------------------------------------------------------+   |
|   | Nova OS Web Desktop (/desktop)                                           |   |
|   | - Nova Voice Orb Agent (Live Phone Command Transcript)                   |   |
|   | - Interactive Terminal                                                   |   |
|   | - Files Manager (Real Folder Tree: Mobile / Photos)                      |   |
|   | - Text Editor & System Settings                                          |   |
|   | - Persistent 6-Digit Pairing PIN Widget                                  |   |
|   +--------------------------------------------------------------------------+   |
|                                                                                  |
|   Uploads Directory Structure:                                                   |
|     Ai_voice/uploads/files/mobile/                                               |
|     ├── <uploaded-documents-and-files>                                           |
|     └── photos/                                                                  |
|         └── <uploaded-photos>                                                    |
+----------------------------------------------------------------------------------+
```

---

## Ports & Protocols (Agreed Canonical Truth)

| Service | Port | Path | Description |
| :--- | :--- | :--- | :--- |
| **HTTP API & Desktop** | **`7890`** | `/pair`, `/upload/*`, `/files`, `/desktop` | Primary HTTP server and Web UI |
| **Dedicated WebSocket**| **`7891`** | `/ws` | Dedicated full-duplex WebSocket for Flutter phone app |
| **WebSocket Fallback** | **`7890`** | `/ws` | Dual-port fallback if phone connects WS on port 7890 |
| **mDNS / Zeroconf**   | **`7890`** | Service: `_winbridge._tcp.local.` | Auto-discovery for Flutter app |

---

## Quickstart: Running the Bridge Server

### 1. Install Dependencies

```bash
pip install -r Ai_voice/requirements.txt
```

Required packages: `fastapi`, `uvicorn`, `websockets`, `pydantic`, `python-multipart`, `zeroconf`, `httpx`.

### 2. Start the Server

From `Ai_voice/`:

```bash
python run_bridge.py
```

*(Or on Windows, simply double-click `start_bridge.bat` to automatically verify firewall rules and launch the bridge.)*


The bridge server will automatically:
1. Bind HTTP endpoints (including `/pair`, `/upload/*`, `/files`, and `/desktop`) to **port 7890**.
2. Launch the dedicated WebSocket server on **port 7891** at path `/ws`.
3. Register mDNS / Zeroconf service `_winbridge._tcp.local.` on port 7890 broadcasting machine hostname and ports.
4. Generate an active 6-digit pairing PIN with a 5-minute rolling TTL.

### 3. Open the Nova OS Desktop

Open your browser to:
```
http://localhost:7890/desktop
```

---

## Where the Pairing PIN is Displayed

1. **Persistent Desktop Pairing Widget (Top-Right)**:
   A dedicated glassmorphic card prominently displays the current 6-digit PIN (e.g. `842 109`), the countdown timer (`Expires in: 04:32`), a `↻ REFRESH PIN` button, and live phone connection status.
2. **System Tray Pill (Taskbar Right)**:
   Displays `PIN: 842109`. Clicking it opens the **Settings** window.
3. **Settings Application (`settings`)**:
   Shows pairing security details, full bridge telemetry, and the live list of authenticated devices.

---

## Canonical Protocol Specification

### 1. Device Pairing (`POST /pair`)
- **Port**: `7890` (HTTP)
- **Path**: `/pair`
- **Headers**:
  ```http
  Content-Type: application/json
  X-Protocol-Version: 1.0
  ```
- **Request Body**:
  ```json
  {
    "code": "842109",
    "protocolVersion": "1.0"
  }
  ```
- **Success Response (200 OK)**:
  ```json
  {
    "success": true,
    "deviceId": "win-hostname",
    "sessionToken": "win_sec_d83e29f...",
    "refreshToken": null,
    "expiresAt": "2026-10-28T00:00:00Z",
    "errorMessage": null,
    "protocolVersion": "1.0"
  }
  ```
- **Failure Response (200 OK with error)**:
  ```json
  {
    "success": false,
    "deviceId": "",
    "sessionToken": null,
    "refreshToken": null,
    "expiresAt": null,
    "errorMessage": "INVALID_PAIRING_CODE: Incorrect 6-digit pairing code.",
    "protocolVersion": "1.0"
  }
  ```

---

### 2. Full-Duplex WebSocket (`/ws`)
- **Port**: `7891` (or `7890` dual-fallback)
- **Path**: `/ws`

#### Step A: Authentication Handshake (Mandatory 1st Message)
- **Client Frame**:
  ```json
  {
    "type": "authenticate",
    "token": "win_sec_d83e29f...",
    "protocol_version": "1.0"
  }
  ```
- **Server Response**:
  ```json
  {
    "type": "auth_result",
    "success": true,
    "device_id": "win-hostname",
    "version": "1.0",
    "error": null
  }
  ```
*Unauthenticated connections sending `command` frames are immediately rejected with `UNAUTHORIZED`.*

#### Step B: Command Execution
- **Client Frame**:
  ```json
  {
    "type": "command",
    "request_id": "cmd-1790535-a1b2",
    "timestamp": 1790535000000,
    "data": {
      "command": "open terminal",
      "type": "text"
    }
  }
  ```
- **Server Response**:
  ```json
  {
    "type": "command_result",
    "request_id": "cmd-1790535-a1b2",
    "protocol_version": "1.0",
    "timestamp": 1790535000015,
    "success": true,
    "data": {
      "status": "completed",
      "action": {
        "action": "app.open",
        "target": "terminal"
      },
      "message": "Opened Terminal",
      "execution_time_ms": 2,
      "error": null
    }
  }
  ```
*When a phone sends an app-opening command, the bridge broadcasts the command result to the Nova OS desktop browser so the window opens live on screen!*

#### Step C: Supported Commands
| Command | Resulting Action | Behavior |
| :--- | :--- | :--- |
| `open nova voice` / `voice` | `{"action": "app.open", "target": "nova-voice"}` | Opens Nova Voice agent |
| `open files` / `files` | `{"action": "app.open", "target": "files"}` | Opens File Manager |
| `open terminal` / `terminal` | `{"action": "app.open", "target": "terminal"}` | Opens Terminal |
| `open editor` / `editor` | `{"action": "app.open", "target": "editor"}` | Opens Text Editor |
| `open settings` / `settings` | `{"action": "app.open", "target": "settings"}` | Opens Settings |
| `take screenshot` / `screenshot` | `{"action": "system.screenshot"}` | Triggers screenshot flash & stub |
| `status` / `ping` | `{"action": "system.status"}` | Returns bridge system health |
| `help` | `{"action": "system.help"}` | Lists supported commands |
| *unrecognized* | `{"action": "unknown", "status": "failed"}` | Graceful fallback (never crashes) |

---

### 3. Authenticated Streamed Uploads (`files/mobile/`)

#### File Upload (`POST /upload/file`)
- **Headers**: `Authorization: Bearer <sessionToken>`, `X-Protocol-Version: 1.0`
- **Body**: `multipart/form-data` with field `file`
- **Destination**: `Ai_voice/uploads/files/mobile/<filename>` (streamed chunk-by-chunk to disk without RAM buffering)
- **Response**: `{"success": true, "filename": "doc.pdf", "size": 128420, "path": "/uploads/files/mobile/doc.pdf"}`

#### Photo Upload (`POST /upload/photo`)
- **Headers**: `Authorization: Bearer <sessionToken>`, `X-Protocol-Version: 1.0`
- **Body**: `multipart/form-data` with field `photo`
- **Destination**: `Ai_voice/uploads/files/mobile/photos/<filename>`
- **Response**: `{"success": true, "filename": "photo.jpg", "size": 512000, "path": "/uploads/files/mobile/photos/photo.jpg"}`

*Unauthenticated requests without a valid Bearer token return `HTTP 401 Unauthorized`.*

---

### 4. Files List API (`GET /files`)
- **URL**: `http://<host>:7890/files`
- **Response**:
  ```json
  {
    "files": [
      {
        "name": "hello_bridge.txt",
        "size": 19,
        "size_formatted": "19 B",
        "type": "file",
        "path": "/uploads/files/mobile/hello_bridge.txt",
        "modified": "2026-09-28 01:49:22"
      },
      {
        "name": "camera_snap.jpg",
        "size": 12,
        "size_formatted": "12 B",
        "type": "photo",
        "path": "/uploads/files/mobile/photos/camera_snap.jpg",
        "modified": "2026-09-28 01:49:22"
      }
    ],
    "total": 2
  }
  ```

---

## Nova OS "Files" Desktop Application

The built-in **Files** app (`frontend/js/window_manager.js`, `helpers.js`) renders a live, interactive folder tree:
- **Top-level `Mobile` folder** (`/files/mobile`): Displays documents received from the phone alongside a nested **`photos/`** folder.
- **Nested `Photos` folder** (`/files/mobile/photos`): Opening the `photos/` folder drills into the photos directory with full parent directory navigation (`.. (Parent Folder)`).
- **Interactive Breadcrumb Navigation**: Click any breadcrumb segment (`files / mobile / photos`) to instantly jump up or down the directory hierarchy.
- **Live Sync**: Counts and file entries update dynamically from `GET /files`.

---

## End-to-End Manual Verification Procedure

Follow this test procedure to verify the entire system with a real mobile device:

1. **Boot the Bridge Server**:
   ```bash
   cd Ai_voice
   python run_bridge.py
   ```
2. **Open Nova OS Desktop**:
   Open a browser to `http://localhost:7890/desktop`.
3. **Confirm Pairing PIN**:
   - Check the top-right widget: verify a live 6-digit code (e.g. `458 129`) is shown with a rolling countdown timer.
4. **Connect from Phone**:
   - Ensure the phone and PC are on the same Wi-Fi network.
   - Open the **Windows Remote** Flutter app.
   - The app will automatically discover the PC via mDNS (`_winbridge._tcp`). Alternatively, tap **Connect manually** and enter the PC's LAN IP with HTTP port `7890` / WS port `7891`.
   - When prompted, enter the 6-digit PIN shown on the Nova OS desktop.
   - Tap **Pair**. Confirm pairing succeeds and issues a secure session token.
5. **Test Remote Command Execution**:
   - On the phone, speak or type `open terminal` or `open files`.
   - In Nova OS, observe the corresponding window pop up on screen immediately, and watch the Nova Voice transcript record the event in real-time.
6. **Test Remote Uploads**:
   - Upload a document from the phone: confirm it lands in `Ai_voice/uploads/files/mobile/`.
   - Upload a photo from the phone: confirm it lands in `Ai_voice/uploads/files/mobile/photos/`.
   - Open the **Files** app in Nova OS: open the `Mobile` folder to see the file and double-click `photos` to view the uploaded photo.

---

## Automated Test Suites

```bash
# Run unit tests (health, diagnostics, clientId re-pair, expired session pruning, PIN auth, uploads, WebSocket)
venv\Scripts\python -m unittest Ai_voice/backend/tests/test_bridge.py
```

---

## Troubleshooting: "Can't reach your PC" & Reachability Diagnostics

If the companion phone app fails with **"Can't reach your PC"** or `POST http://<pc-ip>:7890/pair` times out (errno 110):

### 1. How to Read the New Diagnostics Panel (Desktop & Settings)
The bridge provides real-time visibility into whether phone packets are reaching your computer:

* **Desktop PIN Panel Widget** (top-right of Nova OS desktop):
  - **Green banner (`Last phone contact: 192.168.0.42 GET /health 200 (3s ago)`)**: Packets from the phone are successfully reaching your PC over Wi-Fi.
  - **Yellow warning (`No phone has reached this PC yet. Check Wi-Fi, firewall and router isolation`)**: Zero network packets from any non-loopback device have reached the bridge. Inbound traffic is blocked at the network, router, or firewall layer.
  - **Port status badge**: Shows whether HTTP 7890 is listening, whether dedicated WS 7891 is bound or using fallback, and whether active profile firewall rules pass.

* **Settings App (`⚙ Settings` on desktop or taskbar)**:
  - **Network Reachability & Phone Contact**: Shows the exact last phone contact timestamp, method, path, and status code.
  - **Active Profile Firewall Status**: Shows `PASS` if Windows Defender Firewall has inbound rules enabled for your **active** network profile (`Public` or `Private`). If `BLOCKED`, it prints the exact command to run.
  - **LAN IP Addresses & Adapters**: Lists all detected network interfaces with adapter names. Identifies `[RECOMMENDED FOR PHONE]` (physical Wi-Fi/Ethernet) vs `[VIRTUAL ADAPTER / VPN]` (VirtualBox, Hyper-V, VMware, WSL, Tailscale) so you know which IP to enter on the phone.
  - **Paired Devices Management**: Lists all actively paired mobile devices (Device ID / Client ID, paired timestamp, last seen timestamp) with a **Revoke** button to instantly invalidate unauthorized or stale sessions.

---

### 2. Phone Browser Test of `/health` (Key Test)
Before troubleshooting complex pairing issues, verify basic HTTP reachability:
1. On your mobile phone, open **Safari** (iOS) or **Chrome** (Android).
2. Navigate to:
   ```
   http://<pc-lan-ip>:7890/health
   ```
   *(Replace `<pc-lan-ip>` with the recommended IP displayed on the bridge startup banner, e.g. `http://192.168.0.200:7890/health`)*.
3. **Expected result**: The browser immediately returns a JSON response:
   ```json
   {
     "status": "ok",
     "protocol_version": "1.0",
     "http_port": 7890,
     "ws_port": 7891,
     "ws_port_bound": true,
     "ws_urls": ["ws://192.168.0.200:7891/ws", "ws://192.168.0.200:7890/ws"],
     "lan_ips": ["192.168.0.200"]
   }
   ```
   *Within 4 seconds of opening this URL, the Nova OS desktop widget will turn green and display: `Last phone contact: <phone-ip> GET /health 200 (1s ago)`.*
4. **If the phone browser spins and times out**: The phone cannot reach your PC's IP. Follow steps 3–6 below.

---

### 3. Verify Listening Ports with Netstat
Confirm that both HTTP and WebSocket servers are listening on `0.0.0.0` (all network adapters), not just `127.0.0.1`:
Open Command Prompt or PowerShell on the PC and run:
```cmd
netstat -ano | findstr "7890 7891"
```
You should see:
```text
  TCP    0.0.0.0:7890           0.0.0.0:0              LISTENING        <PID>
  TCP    0.0.0.0:7891           0.0.0.0:0              LISTENING        <PID>
```
If port 7891 is in use by another application, the bridge automatically retries once and falls back to serving `/ws` on port 7890, ensuring the phone client can still connect via the fallback URL in `/health`.

---

### 4. Windows Defender Firewall (Active Profile)
Windows Firewall often classifies home Wi-Fi networks as `Public`, which silently blocks all inbound connections by default. The local bind test cannot detect this because Windows bypasses firewall filtering for connections originating on the local machine.

To allow inbound connections on all profiles (Public, Private, Domain):
1. Right-click PowerShell and select **Run as Administrator**.
2. Run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/allow_firewall.ps1
   ```
   *(Or simply run `start_bridge.bat`, which requests elevation and applies this automatically before launch).*

---

### 5. Third-Party Antivirus & Security Suites
If you have third-party antivirus software installed (e.g. Norton 360, McAfee LiveSafe, Bitdefender, ESET Smart Security, Kaspersky, Avast, AVG):
- Third-party suites install their own proprietary network packet filters that completely override Windows Defender Firewall rules.
- Even if Windows Defender allows port 7890, the third-party firewall will drop inbound packets from the phone.
- **Fix**: Open your antivirus control center -> **Firewall** / **Network Protection** -> add inbound rules allowing TCP `7890`, TCP `7891`, and UDP `5353`, or set your local Wi-Fi connection profile to **"Home / Trusted Network"**.

---

### 6. Router Client Isolation (AP Isolation)
- Many modern Wi-Fi routers (especially guest networks, mesh repeaters, or ISP-provided routers) have **"AP Isolation"**, **"Client Isolation"**, or **"Guest Network Isolation"** enabled by default.
- This security feature deliberately blocks Wi-Fi devices from sending packets to each other, preventing phones from reaching PCs on the same Wi-Fi.
- **Fix**:
  1. Ensure both PC and phone are connected to your primary home Wi-Fi, NOT a Guest SSID.
  2. If using separate 2.4GHz and 5GHz SSIDs, connect both devices to the same frequency band or ensure SSID bridging is enabled.
  3. Log into your router's web admin (usually `http://192.168.1.1` or `http://192.168.0.1`), go to Wireless Settings / Advanced, and verify **"AP Isolation" / "Station Isolation"** is **Disabled**.

