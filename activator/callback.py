from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from . import config

SUCCESS_HTML = b"""HTTP/1.1 200 OK\r
Content-Type: text/html; charset=utf-8\r
Connection: close\r
\r
<!doctype html><meta charset="utf-8">
<title>Antigravity OK</title>
<body style="font-family:sans-serif;padding:40px">
<h2>Antigravity OAuth captured</h2>
<p>You can close this tab.</p>
</body>"""


class CallbackServer:
    def __init__(self) -> None:
        self.code: str | None = None
        self.error: str | None = None
        self._event = asyncio.Event()
        self._server: asyncio.AbstractServer | None = None

    def reset(self) -> None:
        self.code = None
        self.error = None
        self._event = asyncio.Event()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=10)
            first = data.decode("latin-1", errors="ignore").split("\r\n", 1)[0]
            path = first.split(" ")[1] if " " in first else "/"
            qs = parse_qs(urlparse(path).query)
            code = (qs.get("code") or [None])[0]
            if code:
                self.code = code
                self.error = None
                self._event.set()
            elif qs.get("error"):
                self.error = (qs.get("error_description") or qs.get("error") or ["unknown"])[0]
                self._event.set()
            writer.write(SUCCESS_HTML)
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", config.CALLBACK_PORT)
        except OSError as exc:
            raise RuntimeError(
                f"port {config.CALLBACK_PORT} in use. Close Antigravity or another activator first"
            ) from exc

    async def wait_code(self, timeout: float = 180.0) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if self.code:
                return self.code
            await asyncio.sleep(0.2)
        if self.code:
            return self.code
        if self.error:
            raise RuntimeError(self.error)
        raise TimeoutError("OAuth callback timed out")

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


def code_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    return (parse_qs(parsed.query).get("code") or [None])[0]
