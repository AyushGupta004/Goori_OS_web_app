/**
 * Nova OS Bridge Client
 * Communicates with FastAPI bridge backend over authenticated WebSocket and REST.
 */
class BridgeClient {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.isAuthenticated = false;
        this.localToken = null;
        this.activePhoneCount = 0;
        this.wsPort = 7891; // Default WS port per canonical contract
        
        // Listeners for command results (Terminal app, Voice app, etc.)
        this.commandListeners = new Set();
        this.statusListeners = new Set();
        
        this.init();
    }

    async init() {
        await this.fetchPairingStatus();
        await this.fetchDiagnostics();
        this.connect();

        // Refresh pairing status and diagnostics every 4 seconds
        setInterval(async () => {
            await this.fetchPairingStatus();
            await this.fetchDiagnostics();
        }, 4000);
    }

    async fetchPairingStatus() {
        try {
            const res = await fetch('/pair/status');
            if (res.ok) {
                const data = await res.json();
                this.localToken = data.local_token;
                this.updatePairingUi(data);
                return data;
            }
        } catch (e) {
            console.warn('[BridgeClient] Failed to fetch initial pairing status:', e);
        }
        return null;
    }

    async fetchDiagnostics() {
        try {
            const res = await fetch('/api/network/diagnostics');
            if (res.ok) {
                const data = await res.json();
                this.updateDiagnosticsUi(data);
                return data;
            }
        } catch (e) {
            console.warn('[BridgeClient] Failed to fetch diagnostics:', e);
        }
        return null;
    }

    updateDiagnosticsUi(data) {
        if (!data) return;
        const contactContainer = document.getElementById('pairing-contact-display');
        const contactText = document.getElementById('pairing-contact-text');
        const metaInfo = document.getElementById('pairing-meta-info');

        if (contactText && contactContainer) {
            if (data.last_phone_contact) {
                const c = data.last_phone_contact;
                contactText.textContent = `Last phone contact: ${c.ip} ${c.method} ${c.path} ${c.status} (${c.seconds_ago}s ago)`;
                contactContainer.className = 'pairing-contact-display has-contact';
            } else {
                contactText.textContent = 'No phone has reached this PC yet. Check Wi-Fi, firewall and router isolation';
                contactContainer.className = 'pairing-contact-display no-contact';
            }
        }

        if (metaInfo) {
            const wsStatus = data.ws_bound ? '7891 [OK]' : '7891 [FALLBACK 7890]';
            const fwStatus = data.firewall_rules_ok ? 'FW [OK]' : 'FW [BLOCKED]';
            metaInfo.textContent = `HTTP ${data.http_port} | WS ${wsStatus} | ${fwStatus}`;
        }
    }

    updatePairingUi(data) {
        if (!data) return;
        const pinEl = document.getElementById('pairing-pin-display');
        const trayPin = document.getElementById('tray-pin-val');
        const timerEl = document.getElementById('pairing-timer-display');
        const statusLabel = document.getElementById('pairing-status-label');
        const statusDot = document.getElementById('tray-status-dot');

        if (pinEl) pinEl.textContent = data.code || '------';
        if (trayPin) trayPin.textContent = data.code || '------';

        if (timerEl && data.expires_in !== undefined) {
            const m = Math.floor(data.expires_in / 60).toString().padStart(2, '0');
            const s = (data.expires_in % 60).toString().padStart(2, '0');
            timerEl.textContent = `Expires in: ${m}:${s}`;
        }

        const phoneCount = data.paired_devices_count || 0;
        if (statusLabel && statusDot) {
            if (phoneCount > 0 || this.activePhoneCount > 0) {
                statusLabel.textContent = `Phone paired (${this.activePhoneCount} active)`;
                statusDot.className = 'status-indicator connected';
            } else {
                statusLabel.textContent = 'Waiting for phone pairing...';
                statusDot.className = 'status-indicator disconnected';
            }
        }

        const attemptEl = document.getElementById('pairing-attempt-display');
        if (attemptEl) {
            if (data.latest_attempt && data.latest_attempt.message) {
                attemptEl.textContent = data.latest_attempt.message;
                attemptEl.className = `pairing-attempt-display ${data.latest_attempt.result || ''}`;
                attemptEl.style.display = 'block';
            } else {
                attemptEl.style.display = 'none';
            }
        }
    }

    connect() {
        const host = window.location.hostname || 'localhost';
        // Connect primarily to port 7891, or fallback to current port if on single-port mode
        const targetPort = (this.reconnectAttempts % 2 === 0) ? 7891 : (window.location.port || 7890);
        const wsUrl = `ws://${host}:${targetPort}/ws`;

        try {
            console.log(`[BridgeClient] Connecting to ${wsUrl}...`);
            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                console.log(`[BridgeClient] WebSocket open on ${wsUrl}`);
                this.reconnectAttempts = 0;
                this.addHistory('system', 'Connected to Windows AI Bridge.');

                // Perform authentication handshake with local session token
                if (this.localToken) {
                    this.authenticate(this.localToken);
                } else {
                    this.fetchPairingStatus().then((status) => {
                        if (status && status.local_token) {
                            this.authenticate(status.local_token);
                        }
                    });
                }
            };

            this.socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleMessage(message);
                } catch (err) {
                    console.error('[BridgeClient] Error parsing incoming message:', err);
                }
            };

            this.socket.onclose = () => {
                this.isAuthenticated = false;
                this.updateSysMic();
                this.scheduleReconnect();
            };

            this.socket.onerror = (error) => {
                console.warn('[BridgeClient] WebSocket Error:', error);
            };
        } catch (e) {
            this.scheduleReconnect();
        }
    }

    authenticate(token) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            const authPayload = {
                type: 'authenticate',
                token: token,
                protocol_version: '1.0'
            };
            this.socket.send(JSON.stringify(authPayload));
        }
    }

    scheduleReconnect() {
        const timeout = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 15000);
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), timeout);
    }

    handleMessage(message) {
        // 1. Auth Result
        if (message.type === 'auth_result') {
            if (message.success) {
                this.isAuthenticated = true;
                console.log(`[BridgeClient] Authenticated successfully as ${message.device_id}`);
                this.addHistory('system', '✓ Windows Bridge Authenticated (v' + (message.version || '1.0') + ')');
                this.updateSysMic();
            } else {
                this.isAuthenticated = false;
                this.addHistory('system', `✕ Auth failed: ${message.error || 'Invalid token'}`, true);
            }
        }

        // 2. Status Updates (clients connected, telemetry)
        if (message.type === 'status_update') {
            this.activePhoneCount = message.connected_clients || 0;
            this.updateSysMic();
            this.notifyStatusListeners(message);
            
            const statusLabel = document.getElementById('pairing-status-label');
            const statusDot = document.getElementById('tray-status-dot');
            if (statusLabel && statusDot) {
                if (this.activePhoneCount > 0) {
                    statusLabel.textContent = `Phone connected (${this.activePhoneCount} active)`;
                    statusDot.className = 'status-indicator connected';
                } else {
                    statusLabel.textContent = 'Waiting for phone pairing...';
                    statusDot.className = 'status-indicator disconnected';
                }
            }
        }

        // 3. Command Result
        if (message.type === 'command_result') {
            this.notifyCommandListeners(message);

            if (message.success) {
                const msgText = message.data?.message || 'Command executed';
                const execTime = message.data?.execution_time_ms ? ` (${message.data.execution_time_ms}ms)` : '';
                this.addHistory('system', `✓ ${msgText}${execTime}`);

                // Execute action
                const action = message.data?.action;
                if (action) {
                    if (action.action === 'app.open' && action.target) {
                        if (window.WindowManager) {
                            window.WindowManager.openApp(action.target);
                        }
                    } else if (action.action === 'system.screenshot') {
                        this.triggerScreenshotFlash();
                    }
                }
            } else {
                const errText = message.data?.message || message.error || 'Command failed';
                this.addHistory('system', `✕ ${errText}`, true);
            }
        }
    }

    triggerScreenshotFlash() {
        const flash = document.getElementById('screenshot-flash');
        if (flash) {
            flash.classList.add('active');
            setTimeout(() => {
                flash.classList.remove('active');
            }, 300);
        }
    }

    updateSysMic() {
        const micEl = document.getElementById('sys-mic');
        if (!micEl) return;
        if (this.activePhoneCount > 0) {
            micEl.textContent = `MIC ACTIVE (${this.activePhoneCount})`;
            micEl.className = 'tray-item connected';
        } else if (this.isAuthenticated) {
            micEl.textContent = 'MIC STANDBY';
            micEl.className = 'tray-item';
        } else {
            micEl.textContent = 'BRIDGE OFFLINE';
            micEl.className = 'tray-item';
        }
    }

    sendCommand(commandText, callback) {
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            this.addHistory('system', '✕ Cannot send: Bridge disconnected', true);
            if (callback) callback({ success: false, data: { message: 'Bridge disconnected' } });
            return;
        }

        const requestId = 'cmd-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const envelope = {
            type: 'command',
            request_id: requestId,
            protocol_version: '1.0',
            timestamp: Date.now(),
            data: {
                command: commandText,
                type: 'text'
            }
        };

        this.socket.send(JSON.stringify(envelope));
        this.addHistory('user', commandText);

        if (callback) {
            const listener = (res) => {
                if (res.request_id === requestId) {
                    this.commandListeners.delete(listener);
                    callback(res);
                }
            };
            this.commandListeners.add(listener);
        }
    }

    onCommandResult(listener) {
        this.commandListeners.add(listener);
    }

    onStatusUpdate(listener) {
        this.statusListeners.add(listener);
    }

    notifyCommandListeners(result) {
        this.commandListeners.forEach((listener) => {
            try { listener(result); } catch (e) { console.error(e); }
        });
    }

    notifyStatusListeners(status) {
        this.statusListeners.forEach((listener) => {
            try { listener(status); } catch (e) { console.error(e); }
        });
    }

    addHistory(sender, text, isError = false) {
        const historyEl = document.getElementById('nova-history');
        if (!historyEl) return;

        const entry = document.createElement('div');
        entry.className = `history-entry ${sender}${isError ? ' error' : ''}`;
        entry.textContent = text;
        historyEl.appendChild(entry);
        historyEl.scrollTop = historyEl.scrollHeight;
    }
}

window.BridgeClient = new BridgeClient();
