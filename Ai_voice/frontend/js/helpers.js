/**
 * Nova OS Helpers
 * File uploads, command input, Files app rendering, and Settings telemetry.
 */

// Command sending from Nova Voice input field
window.sendMockCommand = function() {
    const input = document.getElementById('nova-cli-input');
    if (input && input.value.trim() !== '') {
        const cmd = input.value.trim();
        if (window.BridgeClient) {
            window.BridgeClient.sendCommand(cmd);
        }
        input.value = '';
    }
};

// Enter key support for Nova Voice input
document.addEventListener('keydown', (e) => {
    if (e.target && e.target.id === 'nova-cli-input' && e.key === 'Enter') {
        window.sendMockCommand();
    }
});

// File upload handler for Nova Voice 📎 button
window.handleFileUpload = async function(event) {
    const file = event.target.files[0];
    if (!file) return;

    if (window.BridgeClient) {
        window.BridgeClient.addHistory('system', `Streaming ${file.name} to Windows Bridge...`);
    }

    const formData = new FormData();
    formData.append('file', file);

    const token = window.BridgeClient?.localToken || '';
    try {
        const response = await fetch('/upload/file', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (response.ok) {
            const result = await response.json();
            if (window.BridgeClient) {
                window.BridgeClient.addHistory('system', `✓ Uploaded ${result.filename} (${formatBytes(result.size)})`);
            }
            window.loadFilesList();
        } else {
            const err = await response.json().catch(() => ({}));
            if (window.BridgeClient) {
                window.BridgeClient.addHistory('system', `✕ Upload failed: ${err.detail || response.statusText}`, true);
            }
        }
    } catch (error) {
        if (window.BridgeClient) {
            window.BridgeClient.addHistory('system', `✕ Network error during upload`, true);
        }
        console.error('Upload error:', error);
    }

    event.target.value = '';
};

// File upload handler inside the Files app
window.handleFilesAppUpload = async function(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    const token = window.BridgeClient?.localToken || '';

    try {
        const response = await fetch('/upload/file', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (response.ok) {
            window.loadFilesList();
        }
    } catch (e) {
        console.error(e);
    }
    event.target.value = '';
};

// Active files cache and folder tree navigation
window._cachedFiles = [];
window._currentFolder = 'mobile'; // 'mobile' | 'photos' | 'all' | 'files'

// Navigate directly into a folder in the folder tree
window.navigateToFolder = function(folder) {
    window._currentFolder = folder;
    
    // Update sidebar active states
    document.querySelectorAll('.files-nav-item').forEach(el => el.classList.remove('active'));
    if (folder === 'mobile') {
        document.getElementById('files-nav-mobile')?.classList.add('active');
    } else if (folder === 'photos') {
        document.getElementById('files-nav-photos')?.classList.add('active');
    }

    window.updateBreadcrumbs();
    window.renderFilesTable();
};

window.updateBreadcrumbs = function() {
    const bcContainer = document.getElementById('files-breadcrumbs');
    if (!bcContainer) return;

    if (window._currentFolder === 'photos') {
        bcContainer.innerHTML = `
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">files</button>
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">mobile</button>
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn current" onclick="window.navigateToFolder('photos')">photos</button>
        `;
    } else if (window._currentFolder === 'all') {
        bcContainer.innerHTML = `
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">files</button>
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn current" onclick="window.filterFiles('all')">all received</button>
        `;
    } else if (window._currentFolder === 'files') {
        bcContainer.innerHTML = `
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">files</button>
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn current" onclick="window.filterFiles('files')">documents</button>
        `;
    } else {
        // 'mobile'
        bcContainer.innerHTML = `
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn" onclick="window.navigateToFolder('mobile')">files</button>
            <span style="color: var(--text-muted);">/</span>
            <button class="files-breadcrumb-btn current" onclick="window.navigateToFolder('mobile')">mobile</button>
        `;
    }
};

// Load files list for Files application
window.loadFilesList = async function() {
    const container = document.getElementById('files-table-container');
    if (!container) return;

    try {
        const res = await fetch('/files');
        if (res.ok) {
            const data = await res.json();
            window._cachedFiles = data.files || [];
            window.updateFolderBadges();
            window.updateBreadcrumbs();
            window.renderFilesTable();
        } else {
            container.innerHTML = `<div style="color: var(--accent-error); text-align: center; padding: 30px;">Failed to load files (HTTP ${res.status})</div>`;
        }
    } catch (e) {
        container.innerHTML = `<div style="color: var(--accent-error); text-align: center; padding: 30px;">Error connecting to bridge files API</div>`;
    }
};

window.updateFolderBadges = function() {
    const allFiles = window._cachedFiles || [];
    const photos = allFiles.filter(f => f.type === 'photo' || f.path.includes('/photos/'));
    const mobileFiles = allFiles.filter(f => f.type !== 'photo' && !f.path.includes('/photos/'));

    const bMobile = document.getElementById('badge-mobile-count');
    const bPhotos = document.getElementById('badge-photos-count');
    const bAll = document.getElementById('badge-all-count');

    if (bMobile) bMobile.textContent = mobileFiles.length + (photos.length > 0 ? 1 : 0);
    if (bPhotos) bPhotos.textContent = photos.length;
    if (bAll) bAll.textContent = allFiles.length;
};

window.filterFiles = function(category) {
    window._currentFolder = category;
    
    document.querySelectorAll('.files-nav-item').forEach(el => el.classList.remove('active'));
    if (category === 'all') {
        document.getElementById('files-nav-all')?.classList.add('active');
    } else if (category === 'files') {
        document.getElementById('files-nav-docs')?.classList.add('active');
    }

    window.updateBreadcrumbs();
    window.renderFilesTable();
};

window.renderFilesTable = function() {
    const container = document.getElementById('files-table-container');
    const countLabel = document.getElementById('files-count-label');
    if (!container) return;

    const allFiles = window._cachedFiles || [];
    const photos = allFiles.filter(f => f.type === 'photo' || f.path.includes('/photos/'));
    const mobileDocs = allFiles.filter(f => f.type !== 'photo' && !f.path.includes('/photos/'));

    let displayRows = [];

    if (window._currentFolder === 'photos') {
        // Inside Photos subfolder
        displayRows.push({
            isFolder: true,
            name: '.. (Parent Folder: mobile)',
            type: 'folder-up',
            size_formatted: '--',
            modified: '--',
            onClick: "window.navigateToFolder('mobile')"
        });
        photos.forEach(p => displayRows.push({ ...p, isFolder: false }));
    } else if (window._currentFolder === 'all') {
        // Quick view: All
        allFiles.forEach(f => displayRows.push({ ...f, isFolder: false }));
    } else if (window._currentFolder === 'files') {
        // Quick view: Documents only
        mobileDocs.forEach(f => displayRows.push({ ...f, isFolder: false }));
    } else {
        // Default: 'mobile' folder
        displayRows.push({
            isFolder: true,
            name: 'photos',
            type: 'folder',
            size_formatted: `${photos.length} item${photos.length === 1 ? '' : 's'}`,
            modified: photos.length > 0 ? photos[0].modified : '--',
            onClick: "window.navigateToFolder('photos')"
        });
        mobileDocs.forEach(d => displayRows.push({ ...d, isFolder: false }));
    }

    const fileCount = displayRows.filter(r => !r.isFolder).length;
    if (countLabel) {
        countLabel.textContent = `${fileCount} file${fileCount === 1 ? '' : 's'}`;
    }

    if (displayRows.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 50px 20px; color: var(--text-muted);">
                <div style="font-size: 36px; margin-bottom: 12px; opacity: 0.6;">📁</div>
                <div style="font-size: 14px; font-weight: 500; color: var(--text-secondary); margin-bottom: 6px;">Folder is empty</div>
                <div style="font-size: 12px;">Upload files from your phone or click "Upload File" above.</div>
            </div>
        `;
        return;
    }

    let html = `
        <table class="files-table">
            <thead>
                <tr>
                    <th style="width: 48%;">Name</th>
                    <th style="width: 14%;">Type</th>
                    <th style="width: 14%;">Size</th>
                    <th style="width: 24%;">Uploaded At</th>
                </tr>
            </thead>
            <tbody>
    `;

    displayRows.forEach((r) => {
        if (r.isFolder) {
            const folderIcon = r.type === 'folder-up' ? '↩️' : '📁';
            html += `
                <tr class="folder-row" onclick="${r.onClick}">
                    <td>
                        <div class="file-row-name" style="cursor: pointer; color: var(--accent-warning);">
                            <span>${folderIcon}</span>
                            <span style="font-weight: 600;">${escapeHtml(r.name)}</span>
                        </div>
                    </td>
                    <td><span class="badge-tag folder">Folder</span></td>
                    <td style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted);">${r.size_formatted}</td>
                    <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${r.modified}</td>
                </tr>
            `;
        } else {
            const icon = r.type === 'photo' ? '🖼️' : '📄';
            const badgeClass = r.type === 'photo' ? 'badge-tag photo' : 'badge-tag file';
            html += `
                <tr>
                    <td>
                        <div class="file-row-name">
                            <span>${icon}</span>
                            <a href="${r.path}" target="_blank" style="color: var(--text-primary); text-decoration: none; font-weight: 500;" title="Click to open file">${escapeHtml(r.name)}</a>
                        </div>
                    </td>
                    <td><span class="${badgeClass}">${r.type}</span></td>
                    <td style="font-family: var(--font-mono); font-size: 12px;">${r.size_formatted}</td>
                    <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${r.modified}</td>
                </tr>
            `;
        }
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
};

// Text Editor actions
window.editorNew = function() {
    const ta = document.getElementById('editor-textarea');
    const fn = document.getElementById('editor-filename');
    if (ta) ta.value = '';
    if (fn) fn.value = 'untitled.txt';
    const charCount = document.getElementById('editor-char-count');
    if (charCount) charCount.textContent = '0 characters | 0 words';
};

window.editorClear = function() {
    const ta = document.getElementById('editor-textarea');
    if (ta) ta.value = '';
    const charCount = document.getElementById('editor-char-count');
    if (charCount) charCount.textContent = '0 characters | 0 words';
};

window.editorSave = async function() {
    const ta = document.getElementById('editor-textarea');
    const fn = document.getElementById('editor-filename');
    if (!ta) return;

    const content = ta.value;
    const filename = (fn?.value.trim()) || 'notes.txt';
    const blob = new Blob([content], { type: 'text/plain' });
    const formData = new FormData();
    formData.append('file', blob, filename);

    const token = window.BridgeClient?.localToken || '';
    try {
        const response = await fetch('/upload/file', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (response.ok) {
            const res = await response.json();
            if (window.BridgeClient) {
                window.BridgeClient.addHistory('system', `✓ Saved editor file: ${res.filename} to uploads`);
            }
            alert(`File '${filename}' saved successfully to uploads directory!`);
            window.loadFilesList();
        } else {
            alert('Failed to save file to bridge.');
        }
    } catch (e) {
        alert('Network error saving file: ' + e);
    }
};

// Regenerate 6-digit pairing PIN
window.regeneratePin = async function() {
    try {
        const res = await fetch('/pair/regenerate', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (window.BridgeClient) {
                window.BridgeClient.updatePairingUi(data.status);
            }
            window.loadSettingsStatus();
        }
    } catch (e) {
        console.error('Error regenerating PIN:', e);
    }
};

// Load status for Settings application
window.loadSettingsStatus = async function() {
    try {
        const [statusRes, diagRes] = await Promise.all([
            fetch('/api/status').catch(() => null),
            fetch('/api/network/diagnostics').catch(() => null)
        ]);

        const data = statusRes && statusRes.ok ? await statusRes.json() : null;
        const diag = diagRes && diagRes.ok ? await diagRes.json() : null;

        if (data) {
            const pinCode = document.getElementById('st-pin-code');
            const pinTimer = document.getElementById('st-pin-timer');

            if (pinCode) pinCode.textContent = data.pairing_code || '------';
            
            if (pinTimer && data.pin_expires_in !== undefined) {
                const m = Math.floor(data.pin_expires_in / 60).toString().padStart(2, '0');
                const s = (data.pin_expires_in % 60).toString().padStart(2, '0');
                pinTimer.textContent = `Expires in: ${m}:${s}`;
            }

            const attemptEl = document.getElementById('st-latest-attempt');
            if (attemptEl) {
                if (data.latest_attempt && data.latest_attempt.message) {
                    attemptEl.textContent = `Latest activity: ${data.latest_attempt.message}`;
                    attemptEl.style.color = (data.latest_attempt.result === 'success') ? 'var(--accent-green)' : '#ff6b6b';
                } else {
                    attemptEl.textContent = 'No pairing attempts recorded yet.';
                    attemptEl.style.color = 'var(--text-muted)';
                }
            }

            // Render Paired Devices (Task 4)
            const pairedList = document.getElementById('st-paired-devices-list');
            if (pairedList) {
                const devices = data.paired_devices || [];
                if (devices.length === 0) {
                    pairedList.innerHTML = `<span style="color: var(--text-muted);">No phone devices paired yet.</span>`;
                } else {
                    let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';
                    devices.forEach(d => {
                        const name = escapeHtml(d.client_id || d.device_id || 'Mobile Client');
                        html += `
                            <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 6px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-2);">
                                <div>
                                    <div style="font-weight: 600; color: var(--text-primary);">📱 ${name}</div>
                                    <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                                        Paired: ${escapeHtml(d.paired_at_str || 'N/A')} &bull; Last seen: ${escapeHtml(d.last_seen_str || 'N/A')}
                                    </div>
                                </div>
                                <button class="btn-widget-action" style="color: #ff6b6b; border-color: rgba(255,107,107,0.4); padding: 4px 10px; flex: 0 0 auto;" onclick="window.revokePairedDevice('${d.token_hash}')">Revoke</button>
                            </div>
                        `;
                    });
                    html += '</div>';
                    pairedList.innerHTML = html;
                }
            }
        }

        if (diag) {
            const httpPort = document.getElementById('st-http-port');
            const wsPort = document.getElementById('st-ws-port');
            const fwStatus = document.getElementById('st-fw-status');
            const fwFixBox = document.getElementById('st-fw-fix-box');
            const contactBox = document.getElementById('st-phone-contact-box');
            const lanAdapters = document.getElementById('st-lan-adapters');
            const mdnsStatus = document.getElementById('st-mdns-status');

            if (httpPort) httpPort.textContent = `${diag.http_port} (Listening)`;
            if (wsPort) wsPort.textContent = diag.ws_bound ? `${diag.ws_port} (Listening)` : `${diag.ws_port} [Fallback /ws on ${diag.http_port}]`;
            
            if (mdnsStatus) {
                mdnsStatus.textContent = diag.mdns_registered ? '_winbridge._tcp (Active)' : '_winbridge._tcp (Unregistered/Offline)';
                mdnsStatus.style.color = diag.mdns_registered ? 'var(--accent-green)' : 'var(--accent-warning)';
            }

            if (fwStatus) {
                if (diag.firewall_rules_ok) {
                    fwStatus.textContent = `PASS (${diag.firewall_info?.active_profile || 'Active'} Profile Allowed)`;
                    fwStatus.style.color = 'var(--accent-green)';
                    if (fwFixBox) fwFixBox.style.display = 'none';
                } else {
                    const missing = diag.firewall_info?.missing?.join(', ') || 'Inbound ports blocked';
                    fwStatus.textContent = `BLOCKED (${missing})`;
                    fwStatus.style.color = '#ff6b6b';
                    if (fwFixBox) {
                        fwFixBox.style.display = 'block';
                        fwFixBox.innerHTML = `⚠️ Run as Admin to fix: <code>${escapeHtml(diag.firewall_info?.fix_command || 'powershell -ExecutionPolicy Bypass -File scripts/allow_firewall.ps1')}</code>`;
                    }
                }
            }

            if (contactBox) {
                if (diag.last_phone_contact) {
                    const c = diag.last_phone_contact;
                    contactBox.innerHTML = `<strong>Last phone contact:</strong> ${escapeHtml(c.ip)} ${escapeHtml(c.method)} ${escapeHtml(c.path)} ${c.status} (${c.seconds_ago}s ago)`;
                    contactBox.style.background = 'rgba(90, 247, 142, 0.12)';
                    contactBox.style.border = '1px solid rgba(90, 247, 142, 0.35)';
                    contactBox.style.color = 'var(--accent-green)';
                } else {
                    contactBox.textContent = 'No phone has reached this PC yet. Check Wi-Fi, firewall and router isolation';
                    contactBox.style.background = 'rgba(255, 179, 71, 0.12)';
                    contactBox.style.border = '1px solid rgba(255, 179, 71, 0.35)';
                    contactBox.style.color = 'var(--accent-warning)';
                }
            }

            if (lanAdapters && diag.lan_ips) {
                let html = '';
                diag.lan_ips.forEach(a => {
                    const rec = a.recommended ? ' <span style="color: var(--accent-green); font-size: 10px; font-weight: 600;">[RECOMMENDED FOR PHONE]</span>' : (a.is_virtual ? ' <span style="color: var(--text-muted); font-size: 10px;">[Virtual Adapter]</span>' : '');
                    html += `
                        <div style="padding: 4px 8px; border-radius: 4px; background: rgba(0,0,0,0.2); border: 1px solid var(--border-1);">
                            <strong>${escapeHtml(a.ip)}</strong> &mdash; ${escapeHtml(a.adapter)}${rec}
                        </div>
                    `;
                });
                lanAdapters.innerHTML = html;
            }
        }
    } catch (e) {
        console.warn('Error loading settings status:', e);
    }
};

window.revokePairedDevice = async function(tokenHash) {
    if (!confirm('Revoke access for this phone? It will need to be re-paired with a PIN.')) {
        return;
    }
    try {
        const res = await fetch('/pair/revoke', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token_hash: tokenHash })
        });
        if (res.ok) {
            window.loadSettingsStatus();
        } else {
            alert('Failed to revoke session.');
        }
    } catch (e) {
        alert('Network error revoking session: ' + e);
    }
};

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
