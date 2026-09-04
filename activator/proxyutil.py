from __future__ import annotations

from urllib.parse import unquote, urlparse


def playwright_proxy(raw: str | None) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.hostname:
        return {"server": raw}
    port = parsed.port
    if port is None:
        port = 1080 if parsed.scheme.startswith("socks") else 8080
    cfg = {"server": f"{parsed.scheme}://{parsed.hostname}:{port}"}
    if parsed.username:
        cfg["username"] = unquote(parsed.username)
    if parsed.password:
        cfg["password"] = unquote(parsed.password)
    return cfg


def httpx_proxy(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    return raw or None

def detect_local_proxy() -> str | None:
    import socket

    for port in (7897, 7890, 10808, 1080, 20171):
        sock = socket.socket()
        sock.settimeout(0.2)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            sock.close()
        return f"http://127.0.0.1:{port}"
    return None
