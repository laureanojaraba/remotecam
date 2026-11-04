"""Anuncia la PC en la red local por mDNS/Bonjour (_phonecam._tcp) y calcula
las IPs que se muestran en el código QR."""

from __future__ import annotations

import logging
import socket

import ifaddr
from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

log = logging.getLogger(__name__)
SERVICE_TYPE = "_phonecam._tcp.local."

# Adaptadores virtuales que casi nunca son el camino al teléfono.
_SKIP = ("vmware", "virtualbox", "vethernet", "hyper-v", "docker", "wsl", "loopback", "tailscale", "zerotier")


def local_ipv4() -> list[str]:
    """IPs IPv4 utilizables, la de la ruta por defecto primero."""
    preferred = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no envía nada
            preferred = s.getsockname()[0]
    except OSError:
        pass

    ips: list[str] = []
    for adapter in ifaddr.get_adapters():
        label = f"{adapter.nice_name} {adapter.name}".lower()
        if any(k in label for k in _SKIP):
            continue
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and not ip.ip.startswith(("127.", "169.254.")):
                ips.append(ip.ip)
    if preferred and not preferred.startswith("127."):
        ips = [preferred] + [i for i in ips if i != preferred]
    return list(dict.fromkeys(ips))


class Announcer:
    def __init__(self, name: str, port: int) -> None:
        self.name = name
        self.port = port
        self.ips = local_ipv4()
        self._zc: AsyncZeroconf | None = None
        self._info: ServiceInfo | None = None

    async def start(self) -> None:
        if not self.ips:
            log.warning("Sin IPs de red local; solo funcionará con IP manual")
            return
        safe = "".join(c for c in self.name if c.isalnum() or c in " -_")[:40] or "PC"
        self._info = ServiceInfo(
            SERVICE_TYPE,
            f"{safe}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip) for ip in self.ips],
            port=self.port,
            properties={"v": "1", "ips": ",".join(self.ips), "name": self.name},
            server=f"{socket.gethostname().split('.')[0]}.local.",
        )
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        try:
            await self._zc.async_register_service(self._info, allow_name_change=True)
            log.info("Anunciado por mDNS en %s", ", ".join(self.ips))
        except Exception as e:
            log.warning("No se pudo anunciar por mDNS (%s); usa QR o IP manual", e)

    async def stop(self) -> None:
        if self._zc:
            try:
                if self._info:
                    await self._zc.async_unregister_service(self._info)
            finally:
                await self._zc.async_close()

    def qr_payload(self) -> str:
        return f"phonecam://connect?h={','.join(self.ips)}&p={self.port}"
