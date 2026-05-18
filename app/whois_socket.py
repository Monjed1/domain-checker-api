from __future__ import annotations

import socket

from app.config import settings
from app.registries import TldRegistry


def query_registry_whois(domain: str, registry: TldRegistry) -> str:
    if not registry.whois_host:
        return ""

    query = registry.whois_query.format(domain=domain)
    return _tcp_query(registry.whois_host, query)


def _tcp_query(host: str, query: str) -> str:
    payload = f"{query}\r\n".encode("utf-8")
    timeout = settings.request_timeout_seconds

    with socket.create_connection((host, 43), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(8192)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")
