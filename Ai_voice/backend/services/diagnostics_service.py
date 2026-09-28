import os
import sys
import time
import socket
import ipaddress
import subprocess
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional, Any

VIRTUAL_ADAPTER_KEYWORDS = [
    "virtual", "vbox", "vmware", "hyper-v", "wsl", "vethernet",
    "tap", "tun", "vpn", "tailscale", "zerotier", "loopback", "bluetooth"
]

class DiagnosticsService:
    def __init__(self, max_contacts: int = 50):
        # Ring buffer for last 50 requests from NON-loopback clients
        # Entry: { time, timestamp, ip, method, path, status }
        self.contact_buffer = deque(maxlen=max_contacts)
        self.last_contact: Optional[Dict[str, Any]] = None

        # WebSocket server bind status
        self.ws_port_bound: bool = False
        self.ws_bind_error: Optional[str] = None

        # mDNS registration status
        self.mdns_registered: bool = False

        # Cache firewall check results for 10 seconds to avoid repeated subprocess overhead
        self._cached_fw_check: Optional[Dict[str, Any]] = None
        self._cached_fw_time: float = 0

    def record_client_request(self, client_ip: str, method: str, path: str, status_code: int):
        """Records a request from a NON-loopback client into the ring buffer. Never records tokens or bodies."""
        if not client_ip:
            return

        ip_clean = client_ip.strip()
        # Strictly ignore loopback addresses
        if ip_clean in ("127.0.0.1", "localhost", "::1"):
            return

        now = time.time()
        time_str = datetime.now().strftime("%H:%M:%S")
        entry = {
            "time": time_str,
            "timestamp": now,
            "ip": ip_clean,
            "method": method.upper(),
            "path": path,
            "status": status_code
        }
        self.contact_buffer.append(entry)
        self.last_contact = entry

    def get_last_phone_contact(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent phone contact with seconds_ago calculation."""
        if not self.last_contact:
            return None
        sec_ago = max(0, int(time.time() - self.last_contact["timestamp"]))
        return {
            "time": self.last_contact["time"],
            "timestamp": self.last_contact["timestamp"],
            "ip": self.last_contact["ip"],
            "method": self.last_contact["method"],
            "path": self.last_contact["path"],
            "status": self.last_contact["status"],
            "seconds_ago": sec_ago
        }

    def get_recent_contacts(self) -> List[Dict[str, Any]]:
        """Returns recent non-loopback contacts ordered newest first."""
        now = time.time()
        res = []
        for item in reversed(self.contact_buffer):
            res.append({
                "time": item["time"],
                "timestamp": item["timestamp"],
                "ip": item["ip"],
                "method": item["method"],
                "path": item["path"],
                "status": item["status"],
                "seconds_ago": max(0, int(now - item["timestamp"]))
            })
        return res

    def get_detailed_lan_adapters(self) -> List[Dict[str, Any]]:
        """
        Discovers all private IPv4 addresses with adapter names,
        flagging likely virtual/VPN adapters and marking physical adapters as recommended.
        """
        results = []
        seen_ips = set()

        # Try ifaddr for adapter names
        try:
            import ifaddr
            adapters = ifaddr.get_adapters()
            for a in adapters:
                name = a.nice_name or "Unknown Adapter"
                name_lower = name.lower()
                is_virt = any(kw in name_lower for kw in VIRTUAL_ADAPTER_KEYWORDS)
                for ip in a.ips:
                    if isinstance(ip.ip, str):
                        try:
                            ip_obj = ipaddress.IPv4Address(ip.ip)
                            if not ip_obj.is_loopback and not ip_obj.is_link_local and ip_obj.is_private:
                                if ip.ip not in seen_ips:
                                    seen_ips.add(ip.ip)
                                    is_recommended = (not is_virt) and any(
                                        kw in name_lower for kw in ["wi-fi", "wifi", "wireless", "ethernet", "lan"]
                                    )
                                    results.append({
                                        "ip": ip.ip,
                                        "adapter": name,
                                        "is_virtual": is_virt,
                                        "recommended": is_recommended
                                    })
                        except Exception:
                            pass
        except Exception:
            pass

        # Fallback to hostname lookup if ifaddr found nothing
        if not results:
            try:
                hostname = socket.gethostname()
                for res in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    ip_str = res[4][0]
                    try:
                        ip_obj = ipaddress.IPv4Address(ip_str)
                        if not ip_obj.is_loopback and not ip_obj.is_link_local and ip_obj.is_private:
                            if ip_str not in seen_ips:
                                seen_ips.add(ip_str)
                                results.append({
                                    "ip": ip_str,
                                    "adapter": "Default Adapter",
                                    "is_virtual": False,
                                    "recommended": True
                                })
                    except Exception:
                        pass
            except Exception:
                pass

        # Ensure at least one adapter is marked recommended if physical ones exist
        if results and not any(r["recommended"] for r in results):
            for r in results:
                if not r["is_virtual"]:
                    r["recommended"] = True
                    break
            if not any(r["recommended"] for r in results):
                results[0]["recommended"] = True

        return results

    def check_firewall_rules(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Queries Windows Defender Firewall to verify TCP 7890, TCP 7891, and UDP 5353
        are allowed for the ACTIVE network profile.
        Tolerates non-Windows OS.
        """
        now = time.time()
        if not force_refresh and self._cached_fw_check and (now - self._cached_fw_time < 10):
            return self._cached_fw_check

        if sys.platform != "win32":
            res = {
                "ok": True,
                "active_profile": "N/A (non-Windows)",
                "missing": [],
                "fix_command": None
            }
            self._cached_fw_check = res
            self._cached_fw_time = now
            return res

        active_profile = "Public"
        try:
            prof_res = subprocess.run(
                ["netsh", "advfirewall", "show", "currentprofile"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in prof_res.stdout.splitlines():
                line_lower = line.strip().lower()
                if "profile settings" in line_lower:
                    if "public" in line_lower:
                        active_profile = "Public"
                    elif "private" in line_lower:
                        active_profile = "Private"
                    elif "domain" in line_lower:
                        active_profile = "Domain"
                    break
        except Exception:
            pass

        required = {
            "TCP:7890": False,
            "TCP:7891": False,
            "UDP:5353": False,
        }

        try:
            res = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in"],
                capture_output=True,
                text=True,
                timeout=8
            )
            current_rule = {}
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    if (current_rule.get("enabled", "").lower() == "yes" and
                        current_rule.get("action", "").lower() == "allow"):
                        proto = current_rule.get("protocol", "").upper()
                        port = current_rule.get("localport", "")
                        prof = current_rule.get("profiles", "").lower()

                        if "all" in prof or active_profile.lower() in prof:
                            ports = [p.strip() for p in port.split(",")]
                            if proto == "TCP":
                                if "7890" in ports or port == "7890":
                                    required["TCP:7890"] = True
                                if "7891" in ports or port == "7891":
                                    required["TCP:7891"] = True
                            elif proto == "UDP":
                                if "5353" in ports or port == "5353":
                                    required["UDP:5353"] = True
                    current_rule = {}
                    continue

                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if "rule name" in k:
                        current_rule["name"] = v
                    elif "enabled" in k:
                        current_rule["enabled"] = v
                    elif "direction" in k:
                        current_rule["direction"] = v
                    elif "profiles" in k:
                        current_rule["profiles"] = v
                    elif "action" in k:
                        current_rule["action"] = v
                    elif "protocol" in k:
                        current_rule["protocol"] = v
                    elif "localport" in k:
                        current_rule["localport"] = v
        except Exception as e:
            # Tolerant fallback
            pass

        missing = [k for k, v in required.items() if not v]
        fix_cmd = "powershell -ExecutionPolicy Bypass -File scripts/allow_firewall.ps1"

        check_res = {
            "ok": len(missing) == 0,
            "active_profile": active_profile,
            "missing": missing,
            "checked": required,
            "fix_command": fix_cmd if missing else None
        }

        self._cached_fw_check = check_res
        self._cached_fw_time = now
        return check_res

diagnostics_service = DiagnosticsService()
