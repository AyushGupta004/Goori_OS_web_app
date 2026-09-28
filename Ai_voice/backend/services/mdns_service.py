import asyncio
import atexit
import signal
import socket
import logging
import secrets
import ipaddress
from typing import Optional, List
from zeroconf import ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

logger = logging.getLogger("mdns_service")

def get_lan_ipv4_addresses() -> List[str]:
    """
    Discovers all reachable, private, non-loopback IPv4 addresses
    (192.168.x.x, 10.x.x.x, 172.16-31.x.x). Never returns 127.0.0.1 or link-local.
    """
    candidates = []

    # 1. Try ifaddr (standard with zeroconf)
    try:
        import ifaddr
        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if isinstance(ip.ip, str):
                    candidates.append(ip.ip)
    except Exception:
        pass

    # 2. Try socket.gethostbyname_ex
    try:
        hostname = socket.gethostname()
        _, _, ips = socket.gethostbyname_ex(hostname)
        candidates.extend(ips)
    except Exception:
        pass

    # 3. Try socket.getaddrinfo
    try:
        hostname = socket.gethostname()
        for res in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidates.append(res[4][0])
    except Exception:
        pass

    # Filter for private, non-loopback IPv4 (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    valid_ips = []
    seen = set()
    for ip_str in candidates:
        if ip_str in seen:
            continue
        try:
            ip_obj = ipaddress.IPv4Address(ip_str)
            # Never include loopback (127.0.0.1) or link-local (169.254.x.x)
            if not ip_obj.is_loopback and not ip_obj.is_link_local and ip_obj.is_private:
                seen.add(ip_str)
                valid_ips.append(ip_str)
        except Exception:
            continue

    return valid_ips

class MDNSService:
    def __init__(self, service_type: str = "_winbridge._tcp.local.", http_port: int = 7890, ws_port: int = 7891):
        self.service_type = service_type if service_type.endswith(".") else f"{service_type}."
        self.http_port = http_port
        self.ws_port = ws_port
        self.aiozc: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.instance_id: str = secrets.token_hex(4)  # Per-run unique instance ID
        self.current_ips: List[str] = []
        self.is_registered: bool = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._running: bool = False

        # Register process exit hook to cleanly unregister
        atexit.register(self.stop_sync)

    async def start(self):
        self._running = True
        await self._register_service()
        # Launch periodic network re-check background task (every 30s)
        if not self._monitor_task or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_network_changes())

    async def _register_service(self):
        try:
            hostname = socket.gethostname()
            lan_ips = get_lan_ipv4_addresses()
            self.current_ips = list(lan_ips)

            addresses = [socket.inet_aton(ip) for ip in lan_ips]

            instance_name = f"{hostname}.{self.service_type}"
            properties = {
                "version": "1.0",
                "name": "Windows AI Bridge",
                "hostname": hostname,
                "instance_id": self.instance_id,
                "http_port": str(self.http_port),
                "ws_port": str(self.ws_port),
                "lan_ips": ",".join(lan_ips)
            }

            self.service_info = ServiceInfo(
                type_=self.service_type,
                name=instance_name,
                addresses=addresses,
                port=self.http_port,
                properties=properties,
                server=f"{hostname}.local."
            )

            if not self.aiozc:
                self.aiozc = AsyncZeroconf()

            await self.aiozc.async_register_service(self.service_info)
            self.is_registered = True
            try:
                from backend.services.diagnostics_service import diagnostics_service
                diagnostics_service.mdns_registered = True
            except Exception:
                pass
            print(f"[mDNS] Registered service '{instance_name}' (instance_id={self.instance_id}) on {lan_ips}:{self.http_port} (WS on {self.ws_port})")
        except Exception as e:
            self.is_registered = False
            try:
                from backend.services.diagnostics_service import diagnostics_service
                diagnostics_service.mdns_registered = False
            except Exception:
                pass
            err_msg = str(e) or repr(e)
            print(f"[mDNS] Warning: Failed to register mDNS service: {err_msg}. Fallback to manual IP entry.")

    async def _monitor_network_changes(self):
        """Re-checks LAN IPs every 30s. If DHCP or Wi-Fi changes, re-registers mDNS."""
        while self._running:
            try:
                await asyncio.sleep(30)
                if not self._running:
                    break
                latest_ips = get_lan_ipv4_addresses()
                if set(latest_ips) != set(self.current_ips):
                    print(f"[mDNS] Detected LAN IP change from {self.current_ips} to {latest_ips}. Updating mDNS...")
                    if self.aiozc and self.service_info:
                        try:
                            await self.aiozc.async_unregister_service(self.service_info)
                        except Exception:
                            pass
                    await self._register_service()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[mDNS] Monitor loop error: {e}")

    async def stop(self):
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None

        if self.aiozc and self.service_info:
            try:
                print("[mDNS] Unregistering mDNS service...")
                await self.aiozc.async_unregister_service(self.service_info)
                await self.aiozc.async_close()
            except Exception as e:
                print(f"[mDNS] Error during unregister: {e}")
            self.aiozc = None
            self.service_info = None
        self.is_registered = False
        try:
            from backend.services.diagnostics_service import diagnostics_service
            diagnostics_service.mdns_registered = False
        except Exception:
            pass

    def stop_sync(self):
        """Synchronous unregister for atexit and signal handlers on process exit."""
        self._running = False
        if self.aiozc and self.service_info:
            try:
                # Use synchronous Zeroconf to close if event loop is dead
                print("[mDNS] Cleanly unregistering mDNS service before exit...")
                zc = Zeroconf()
                zc.unregister_service(self.service_info)
                zc.close()
            except Exception:
                pass
            self.aiozc = None
            self.service_info = None
        self.is_registered = False
        try:
            from backend.services.diagnostics_service import diagnostics_service
            diagnostics_service.mdns_registered = False
        except Exception:
            pass


