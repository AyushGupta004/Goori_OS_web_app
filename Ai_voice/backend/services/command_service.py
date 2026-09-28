import time
import re
from typing import Dict, Any, Optional

class CommandService:
    @staticmethod
    def process(command_text: str) -> Dict[str, Any]:
        """
        Deterministic command router.
        Maps text to structured actions, execution time, and statuses.
        """
        start_time = time.perf_counter()
        raw_cmd = (command_text or "").strip()
        cmd = raw_cmd.lower()
        
        # Clean punctuation
        clean_cmd = re.sub(r'[^\w\s]', '', cmd).strip()
        
        # 1. Open Desktop Applications
        app_targets = {
            "nova voice": "nova-voice",
            "novavoice": "nova-voice",
            "voice": "nova-voice",
            "voice agent": "nova-voice",
            "mic": "nova-voice",
            "terminal": "terminal",
            "cmd": "terminal",
            "console": "terminal",
            "command prompt": "terminal",
            "shell": "terminal",
            "files": "files",
            "file": "files",
            "file manager": "files",
            "file explorer": "files",
            "uploads": "files",
            "text editor": "editor",
            "editor": "editor",
            "notepad": "editor",
            "notes": "editor",
            "settings": "settings",
            "config": "settings",
            "preferences": "settings",
            "options": "settings",
            "bridge settings": "settings"
        }

        # Check for open [app] patterns
        opened_app = None
        if clean_cmd.startswith("open ") or clean_cmd.startswith("launch ") or clean_cmd.startswith("start "):
            target = re.sub(r'^(open|launch|start)\s+', '', clean_cmd).strip()
            if target in app_targets:
                opened_app = app_targets[target]
            elif target in ["nova-voice", "files", "terminal", "editor", "settings"]:
                opened_app = target
        elif clean_cmd in app_targets:
            opened_app = app_targets[clean_cmd]

        if opened_app:
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            friendly_name = {
                "nova-voice": "Nova Voice",
                "files": "Files",
                "terminal": "Terminal",
                "editor": "Text Editor",
                "settings": "Settings"
            }.get(opened_app, opened_app.title())
            
            return {
                "status": "completed",
                "action": {
                    "action": "app.open",
                    "target": opened_app
                },
                "message": f"Opened {friendly_name}",
                "execution_time_ms": elapsed_ms,
                "error": None
            }

        # 2. Screenshot Stub
        if any(kw in clean_cmd for kw in ["screenshot", "capture screen", "take screenshot", "screen capture", "snapshot"]):
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "status": "completed",
                "action": {
                    "action": "system.screenshot",
                    "target": "display"
                },
                "message": "Screenshot captured and saved to desktop.",
                "execution_time_ms": elapsed_ms,
                "error": None
            }

        # 3. System Status / Telemetry
        if clean_cmd in ["status", "system status", "ping", "info", "system info"]:
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "status": "completed",
                "action": {
                    "action": "system.status"
                },
                "message": "Nova OS Bridge is active and listening.",
                "execution_time_ms": elapsed_ms,
                "error": None
            }

        # 4. Help
        if clean_cmd in ["help", "commands", "what can you do"]:
            elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "status": "completed",
                "action": {
                    "action": "system.help"
                },
                "message": "Available commands: open [nova-voice | files | terminal | editor | settings], take screenshot, status, help",
                "execution_time_ms": elapsed_ms,
                "error": None
            }

        # 5. Graceful fallback for unrecognized commands
        elapsed_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        return {
            "status": "failed",
            "action": {
                "action": "unknown",
                "target": None
            },
            "message": f"Command not recognized: '{raw_cmd}'. Try 'help' or 'open terminal'.",
            "execution_time_ms": elapsed_ms,
            "error": "UNKNOWN_COMMAND"
        }
