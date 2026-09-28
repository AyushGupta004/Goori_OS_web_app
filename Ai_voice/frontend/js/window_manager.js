/**
 * Window Manager for Nova OS
 * Implements windows, dragging, focus, and the 5 desktop applications.
 */
class WindowManager {
    constructor() {
        this.windows = new Map();
        this.zIndexCounter = 100;
        this.container = document.getElementById('window-manager');
        this.taskbarApps = document.getElementById('taskbar-apps');
    }

    openApp(appId) {
        if (this.windows.has(appId)) {
            this.focusWindow(appId);
            return;
        }
        const appConfig = this.getAppConfig(appId);
        if (!appConfig) return;

        this.createWindow(appId, appConfig);
        this.updateTaskbar();
    }

    getAppConfig(appId) {
        const configs = {
            'nova-voice': {
                title: '🎤 Nova Voice Agent',
                width: 440,
                height: 560,
                x: 80,
                y: 60,
                contentHtml: `
                    <div style="display: flex; flex-direction: column; height: 100%;">
                        <div class="nova-voice-orb-container">
                            <div class="nova-orb" id="nova-orb">NOVA</div>
                        </div>
                        <div class="nova-voice-status" id="nova-status">STANDBY — READY FOR COMMANDS</div>
                        <div class="nova-voice-history" id="nova-history" style="flex-grow: 1;">
                            <div class="history-entry system">Nova OS Runtime initialized.</div>
                            <div class="history-entry system">Listening for phone commands...</div>
                        </div>
                        <div style="display: flex; border-top: 1px solid var(--border-3); padding: 12px; background: var(--bg-panel-2); gap: 8px;">
                            <input type="file" id="nova-file-upload" style="display: none;" onchange="window.handleFileUpload(event)">
                            <button onclick="document.getElementById('nova-file-upload').click()" style="background: var(--bg-panel-4); border: 1px solid var(--border-3); color: var(--text-muted); cursor: pointer; font-size: 16px; padding: 6px 10px; border-radius: 6px;" title="Upload File via Bridge">📎</button>
                            <input type="text" id="nova-cli-input" placeholder="Say or type a command..." style="flex-grow: 1; background: var(--bg-panel-4); border: 1px solid var(--border-3); color: var(--text-primary); padding: 8px 12px; border-radius: 6px; font-family: var(--font-ui); font-size: 13px; outline: none;">
                            <button onclick="window.sendMockCommand()" style="background: rgba(90, 247, 142, 0.1); border: 1px solid rgba(90, 247, 142, 0.3); color: var(--accent-green); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px;">SEND</button>
                        </div>
                    </div>
                `
            },
            'terminal': {
                title: 'user@novaos:~',
                width: 640,
                height: 420,
                x: 180,
                y: 100,
                contentHtml: `
                    <div class="terminal-container" id="terminal-app-container">
                        <div class="terminal-output" id="terminal-output-log">
                            <div class="term-line info">[Nova OS Terminal v1.0.0 — Canonical Bridge Protocol Client]</div>
                            <div class="term-line muted">Type commands like 'open files', 'open settings', 'screenshot', or 'help'.</div>
                            <div class="term-line muted">------------------------------------------------------------</div>
                        </div>
                        <div class="terminal-input-row">
                            <span class="term-prompt-label">user@novaos:~$</span>
                            <input type="text" id="terminal-cli-input" class="terminal-input" autocomplete="off" spellcheck="false" placeholder="Enter command...">
                        </div>
                    </div>
                `,
                onInit: () => this.initTerminal()
            },
            'files': {
                title: '📁 File Manager — /uploads/files/mobile',
                width: 720,
                height: 480,
                x: 220,
                y: 110,
                contentHtml: `
                    <div class="files-layout">
                        <div class="files-sidebar">
                            <div class="files-tree-section-title">Directories</div>
                            <div class="files-nav-item active" id="files-nav-mobile" onclick="window.navigateToFolder('mobile')">
                                <span>📱 Mobile</span>
                                <span class="tree-badge" id="badge-mobile-count">-</span>
                            </div>
                            <div class="files-nav-item tree-child" id="files-nav-photos" onclick="window.navigateToFolder('photos')">
                                <span>🖼️ Photos</span>
                                <span class="tree-badge" id="badge-photos-count">-</span>
                            </div>

                            <div class="files-tree-section-title" style="margin-top: 10px;">Quick Views</div>
                            <div class="files-nav-item" id="files-nav-all" onclick="window.filterFiles('all')">
                                <span>⚡ All Received</span>
                                <span class="tree-badge" id="badge-all-count">-</span>
                            </div>
                            <div class="files-nav-item" id="files-nav-docs" onclick="window.filterFiles('files')">
                                <span>📄 Documents</span>
                            </div>
                        </div>
                        <div class="files-main">
                            <div class="files-toolbar">
                                <div class="files-breadcrumbs" id="files-breadcrumbs">
                                    <span style="color: var(--text-muted);">/</span>
                                    <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">files</button>
                                    <span style="color: var(--text-muted);">/</span>
                                    <button class="files-breadcrumb-btn current" onclick="window.navigateToFolder('mobile')">mobile</button>
                                </div>
                                <div class="files-toolbar-actions">
                                    <input type="file" id="files-app-upload-input" style="display: none;" onchange="window.handleFilesAppUpload(event)">
                                    <button class="files-toolbar-btn" onclick="document.getElementById('files-app-upload-input').click()">
                                        ⬆ Upload File
                                    </button>
                                    <button class="files-toolbar-btn" onclick="window.loadFilesList()">
                                        ↻ Refresh
                                    </button>
                                    <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); min-width: 60px; text-align: right;" id="files-count-label">Loading...</span>
                                </div>
                            </div>
                            <div class="files-content" id="files-table-container">
                                <div style="color: var(--text-muted); text-align: center; padding: 40px;">Loading uploaded files...</div>
                            </div>
                        </div>
                    </div>
                `,
                onInit: () => window.loadFilesList()
            },
            'editor': {
                title: '📝 Nova Text Editor',
                width: 620,
                height: 460,
                x: 280,
                y: 140,
                contentHtml: `
                    <div class="editor-container">
                        <div class="editor-toolbar">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 14px;">📄</span>
                                <input type="text" id="editor-filename" class="editor-filename-input" value="notes.txt">
                            </div>
                            <div style="display: flex; gap: 8px;">
                                <button class="btn-widget-action" onclick="window.editorNew()">New</button>
                                <button class="btn-widget-action" onclick="window.editorClear()">Clear</button>
                                <button class="btn-widget-action" style="color: var(--accent-green); border-color: rgba(90, 247, 142, 0.3);" onclick="window.editorSave()">💾 Save to Uploads</button>
                            </div>
                        </div>
                        <textarea id="editor-textarea" class="editor-textarea" placeholder="Start typing your document or notes here...&#10;&#10;Click 'Save to Uploads' to stream this file to the Windows Bridge uploads directory."></textarea>
                        <div class="editor-statusbar">
                            <span id="editor-char-count">0 characters | 0 words</span>
                            <span>UTF-8 | Plain Text</span>
                        </div>
                    </div>
                `,
                onInit: () => this.initEditor()
            },
            'settings': {
                title: '⚙ Nova OS Settings & Bridge Diagnostics',
                width: 640,
                height: 590,
                x: 280,
                y: 70,
                contentHtml: `
                    <div class="settings-container" id="settings-app-container">
                        <!-- Network Reachability & Diagnostics -->
                        <div class="settings-card">
                            <div class="settings-card-title">📡 NETWORK REACHABILITY & PHONE CONTACT</div>
                            <div id="st-phone-contact-box" style="margin-bottom: 12px; padding: 10px 12px; border-radius: 8px; font-family: var(--font-mono); font-size: 11px; line-height: 1.4; background: rgba(255, 179, 71, 0.12); border: 1px solid rgba(255, 179, 71, 0.35); color: var(--accent-warning);">
                                Checking phone reachability...
                            </div>
                            <div class="settings-grid">
                                <span class="settings-label">HTTP Port (0.0.0.0):</span>
                                <span class="settings-val" id="st-http-port">7890</span>
                                <span class="settings-label">WS Port (0.0.0.0):</span>
                                <span class="settings-val" id="st-ws-port">7891</span>
                                <span class="settings-label">Firewall Status:</span>
                                <span class="settings-val" id="st-fw-status">Checking...</span>
                                <span class="settings-label">mDNS Discovery:</span>
                                <span class="settings-val" id="st-mdns-status" style="color: var(--accent-green);">_winbridge._tcp (Active)</span>
                            </div>
                            <div id="st-fw-fix-box" style="display: none; margin-top: 10px; padding: 8px 10px; border-radius: 6px; background: rgba(255, 107, 107, 0.12); border: 1px solid rgba(255, 107, 107, 0.35); font-family: var(--font-mono); font-size: 11px; color: #ff6b6b;"></div>
                            
                            <div style="margin-top: 12px;">
                                <div style="font-size: 11px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; font-family: var(--font-mono);">LAN IP ADDRESSES & ADAPTERS:</div>
                                <div id="st-lan-adapters" style="display: flex; flex-direction: column; gap: 4px; font-family: var(--font-mono); font-size: 11px;"></div>
                            </div>
                        </div>

                        <!-- Active Pairing PIN -->
                        <div class="settings-card">
                            <div class="settings-card-title">📱 PHONE PAIRING SECURITY</div>
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                                <div>
                                    <div style="font-family: var(--font-mono); font-size: 28px; font-weight: 700; color: var(--accent-green); letter-spacing: 0.15em;" id="st-pin-code">------</div>
                                    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);" id="st-pin-timer">Expires in: 05:00</div>
                                </div>
                                <button class="btn-widget-action" onclick="window.regeneratePin()" style="padding: 8px 14px; font-weight: 600;">↻ REGENERATE PIN</button>
                            </div>
                            <div style="font-size: 12px; color: var(--text-muted); line-height: 1.4;">
                                Enter this 6-digit code on the Windows Remote Flutter phone app to securely establish an authenticated session.
                            </div>
                            <div id="st-latest-attempt" style="margin-top: 10px; font-family: var(--font-mono); font-size: 11px; padding: 6px 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-2); color: var(--text-secondary);">
                                No pairing attempts recorded yet.
                            </div>
                        </div>

                        <!-- Paired Devices -->
                        <div class="settings-card">
                            <div class="settings-card-title">📱 PAIRED DEVICES</div>
                            <div id="st-paired-devices-list" style="font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary);">
                                Loading paired devices...
                            </div>
                        </div>
                    </div>
                `,
                onInit: () => window.loadSettingsStatus()
            }
        };

        return configs[appId] || {
            title: appId,
            width: 420,
            height: 320,
            x: 200,
            y: 150,
            contentHtml: `<div style="padding: 24px; color: var(--text-muted);">Application '${appId}' is initialized.</div>`
        };
    }

    createWindow(appId, config) {
        const winEl = document.createElement('div');
        winEl.className = 'window';
        winEl.id = `win-${appId}`;
        winEl.style.width = `${config.width}px`;
        winEl.style.height = `${config.height}px`;
        winEl.style.left = `${config.x}px`;
        winEl.style.top = `${config.y}px`;

        winEl.innerHTML = `
            <div class="window-titlebar">
                <div class="traffic-lights">
                    <div class="light close" onclick="window.WindowManager.closeWindow('${appId}')" title="Close"></div>
                    <div class="light minimize" onclick="window.WindowManager.minimizeWindow('${appId}')" title="Minimize"></div>
                    <div class="light maximize" onclick="window.WindowManager.maximizeWindow('${appId}')" title="Maximize"></div>
                </div>
                <div class="window-title">${config.title}</div>
            </div>
            <div class="window-content">
                ${config.contentHtml}
            </div>
        `;

        winEl.addEventListener('mousedown', () => this.focusWindow(appId));

        // Dragging implementation
        const titlebar = winEl.querySelector('.window-titlebar');
        titlebar.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('light')) return;
            this.focusWindow(appId);
            let startX = e.clientX;
            let startY = e.clientY;
            let startLeft = parseInt(winEl.style.left) || 0;
            let startTop = parseInt(winEl.style.top) || 0;

            const onMouseMove = (moveEvent) => {
                const dx = moveEvent.clientX - startX;
                const dy = moveEvent.clientY - startY;
                winEl.style.left = `${Math.max(0, startLeft + dx)}px`;
                winEl.style.top = `${Math.max(0, startTop + dy)}px`;
            };
            const onMouseUp = () => {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            };
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });

        this.container.appendChild(winEl);
        this.windows.set(appId, winEl);
        this.focusWindow(appId);

        if (config.onInit) {
            setTimeout(config.onInit, 50);
        }
    }

    focusWindow(appId) {
        this.windows.forEach((win, id) => {
            if (id === appId) {
                win.classList.add('focused');
                win.style.display = 'flex';
                this.zIndexCounter++;
                win.style.zIndex = this.zIndexCounter;
            } else {
                win.classList.remove('focused');
            }
        });
        this.updateTaskbar();
    }

    closeWindow(appId) {
        const win = this.windows.get(appId);
        if (win) {
            win.remove();
            this.windows.delete(appId);
            this.updateTaskbar();
        }
    }

    minimizeWindow(appId) {
        const win = this.windows.get(appId);
        if (win) {
            win.style.display = 'none';
            this.updateTaskbar();
        }
    }

    maximizeWindow(appId) {
        const win = this.windows.get(appId);
        if (!win) return;
        if (win.dataset.maximized === 'true') {
            win.style.width = win.dataset.origW;
            win.style.height = win.dataset.origH;
            win.style.left = win.dataset.origX;
            win.style.top = win.dataset.origY;
            win.dataset.maximized = 'false';
        } else {
            win.dataset.origW = win.style.width;
            win.dataset.origH = win.style.height;
            win.dataset.origX = win.style.left;
            win.dataset.origY = win.style.top;
            win.style.width = 'calc(100vw - 40px)';
            win.style.height = 'calc(100vh - 84px)';
            win.style.left = '20px';
            win.style.top = '20px';
            win.dataset.maximized = 'true';
        }
    }

    updateTaskbar() {
        if (!this.taskbarApps) return;
        this.taskbarApps.innerHTML = '';
        this.windows.forEach((win, appId) => {
            const item = document.createElement('div');
            item.className = `taskbar-app-item ${win.classList.contains('focused') && win.style.display !== 'none' ? 'active' : ''}`;
            const iconMap = {
                'nova-voice': '🎤 Nova Voice',
                'terminal': '🖥 Terminal',
                'files': '📁 Files',
                'editor': '📝 Editor',
                'settings': '⚙ Settings'
            };
            item.textContent = iconMap[appId] || appId;
            item.onclick = () => {
                if (win.style.display === 'none') {
                    win.style.display = 'flex';
                    this.focusWindow(appId);
                } else if (win.classList.contains('focused')) {
                    this.minimizeWindow(appId);
                } else {
                    this.focusWindow(appId);
                }
            };
            this.taskbarApps.appendChild(item);
        });
    }

    initTerminal() {
        const input = document.getElementById('terminal-cli-input');
        const output = document.getElementById('terminal-output-log');
        if (!input || !output) return;

        input.focus();

        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                const line = input.value.trim();
                input.value = '';
                if (!line) return;

                // Print command prompt line
                const p = document.createElement('div');
                p.className = 'term-line prompt-cmd';
                p.textContent = `user@novaos:~$ ${line}`;
                output.appendChild(p);

                // Handle local terminal built-ins
                if (line.toLowerCase() === 'clear') {
                    output.innerHTML = '';
                    return;
                }
                if (line.toLowerCase() === 'exit') {
                    this.closeWindow('terminal');
                    return;
                }

                // Send through BridgeClient
                if (window.BridgeClient) {
                    window.BridgeClient.sendCommand(line, (result) => {
                        const resLine = document.createElement('div');
                        if (result.success) {
                            resLine.className = 'term-line success';
                            const exec = result.data?.execution_time_ms !== undefined ? ` (${result.data.execution_time_ms}ms)` : '';
                            resLine.textContent = `[bridge] ✓ ${result.data?.message || 'Success'}${exec}`;
                        } else {
                            resLine.className = 'term-line error';
                            resLine.textContent = `[bridge] ✕ ${result.data?.message || result.error || 'Failed'}`;
                        }
                        output.appendChild(resLine);
                        output.scrollTop = output.scrollHeight;
                    });
                }
                output.scrollTop = output.scrollHeight;
            }
        };

        // Listen for all external command results
        if (window.BridgeClient) {
            window.BridgeClient.onCommandResult((res) => {
                if (output && output.isConnected) {
                    const line = document.createElement('div');
                    line.className = res.success ? 'term-line info' : 'term-line error';
                    line.textContent = `[event] ${res.success ? '✓' : '✕'} ${res.data?.message || ''}`;
                    output.appendChild(line);
                    output.scrollTop = output.scrollHeight;
                }
            });
        }
    }

    initEditor() {
        const textarea = document.getElementById('editor-textarea');
        const charCount = document.getElementById('editor-char-count');
        if (!textarea || !charCount) return;

        textarea.oninput = () => {
            const val = textarea.value;
            const chars = val.length;
            const words = val.trim() ? val.trim().split(/\s+/).length : 0;
            charCount.textContent = `${chars} characters | ${words} words`;
        };
    }
}

window.WindowManager = new WindowManager();
