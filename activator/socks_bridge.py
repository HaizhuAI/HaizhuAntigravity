from __future__ import annotations

import select
import socket
import struct
import threading
from urllib.parse import unquote, urlparse

import socks


class Socks5Relay:
    """Local SOCKS5 (no auth) -> upstream SOCKS5 (user/pass). Chrome speaks SK5 natively."""

    def __init__(self, socks_url: str, bind: str = "127.0.0.1") -> None:
        parsed = urlparse(socks_url)
        if not parsed.hostname:
            raise ValueError("invalid socks url")
        self.remote_host = parsed.hostname
        self.remote_port = parsed.port or 1080
        self.username = unquote(parsed.username) if parsed.username else None
        self.password = unquote(parsed.password) if parsed.password else None
        self.bind = bind
        self.port = 0
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def socks_url(self) -> str:
        return f"socks5://{self.bind}:{self.port}"

    def probe(self, timeout: float = 20.0) -> None:
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5,
            self.remote_host,
            self.remote_port,
            True,
            self.username,
            self.password,
        )
        sock.settimeout(timeout)
        sock.connect(("accounts.google.com", 443))
        sock.close()

    def start(self) -> str:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.bind, 0))
        srv.listen(128)
        srv.settimeout(1.0)
        self._sock = srv
        self.port = srv.getsockname()[1]
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self.socks_url

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                client, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _open_remote(self, host: str, port: int) -> socket.socket:
        sock = socks.socksocket()
        sock.set_proxy(
            socks.SOCKS5,
            self.remote_host,
            self.remote_port,
            True,
            self.username,
            self.password,
        )
        sock.settimeout(45)
        sock.connect((host, port))
        return sock

    def _recv_exact(self, client: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = client.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("client closed")
            buf += chunk
        return buf

    def _handle(self, client: socket.socket) -> None:
        remote = None
        try:
            client.settimeout(45)
            ver_n = self._recv_exact(client, 2)
            if ver_n[0] != 5:
                return
            methods = set(self._recv_exact(client, ver_n[1]))
            if 0x00 in methods:
                client.sendall(b"\x05\x00")
            elif 0x02 in methods:
                client.sendall(b"\x05\x02")
                auth_ver_ulen = self._recv_exact(client, 2)
                self._recv_exact(client, auth_ver_ulen[1])
                plen = self._recv_exact(client, 1)[0]
                self._recv_exact(client, plen)
                client.sendall(b"\x01\x00")
            else:
                client.sendall(b"\x05\xff")
                return
            hdr = self._recv_exact(client, 4)
            if hdr[0] != 5 or hdr[1] != 1:
                client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            atyp = hdr[3]
            if atyp == 1:
                addr = socket.inet_ntoa(self._recv_exact(client, 4))
            elif atyp == 3:
                ln = self._recv_exact(client, 1)[0]
                addr = self._recv_exact(client, ln).decode("utf-8", "ignore")
            elif atyp == 4:
                addr = socket.inet_ntop(socket.AF_INET6, self._recv_exact(client, 16))
            else:
                client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            port = struct.unpack("!H", self._recv_exact(client, 2))[0]
            remote = self._open_remote(addr, port)
            client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            self._pipe(client, remote)
        except Exception:
            try:
                client.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
        finally:
            try:
                client.close()
            except OSError:
                pass
            if remote:
                try:
                    remote.close()
                except OSError:
                    pass

    def _pipe(self, a: socket.socket, b: socket.socket) -> None:
        sockets = [a, b]
        while sockets:
            r, _, _ = select.select(sockets, [], [], 60)
            if not r:
                break
            for s in r:
                other = b if s is a else a
                try:
                    buf = s.recv(65536)
                except OSError:
                    return
                if not buf:
                    return
                try:
                    other.sendall(buf)
                except OSError:
                    return
