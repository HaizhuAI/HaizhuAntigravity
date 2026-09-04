from __future__ import annotations

import asyncio
import socket
import subprocess
from pathlib import Path


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def find_chrome() -> Path:
    for p in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    ):
        if p.exists():
            return p
    raise FileNotFoundError("Google Chrome not found")


async def connect_real_chrome(pw, profile: Path, start_url: str, proxy: str | None = None):
    chrome = find_chrome()
    profile.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    args = [
        str(chrome),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--start-maximized",
        "--lang=en-US",
    ]
    if proxy:
        server = proxy.replace("http://", "").replace("https://", "")
        if "://" in server:
            server = server.split("://", 1)[1]
        args.append(f"--proxy-server={server}")
    args.append(start_url)
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    browser = None
    last_err = None
    for _ in range(40):
        await asyncio.sleep(0.25)
        try:
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            break
        except Exception as exc:
            last_err = exc
    if browser is None:
        proc.kill()
        raise RuntimeError(f"connect_over_cdp failed: {last_err}")
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return proc, browser, context, page
