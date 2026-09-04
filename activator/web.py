from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .accounts import parse_text
from .runner import Activator

STATIC = Path(__file__).resolve().parent / "static"

_logs: list[str] = []
_state: dict[str, Any] = {
    "running": False,
    "results": [],
    "loaded": 0,
}
_worker: Activator | None = None
_task: asyncio.Task | None = None


def _log(msg: str) -> None:
    line = msg
    _logs.append(line)
    if len(_logs) > 2000:
        del _logs[:500]
    print(line, flush=True)


def create_app() -> FastAPI:
    app = FastAPI(title="Antigravity Activator")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    async def status():
        return {
            "running": _state["running"],
            "loaded": _state["loaded"],
            "results": _state["results"][-200:],
            "logs": _logs[-200:],
        }

    @app.post("/api/start")
    async def start(
        blob: str = Form(""),
        headed: str = Form("1"),
        channel: str = Form("chrome"),
        timeout: float = Form(180),
        proxy: str = Form(""),
        file: UploadFile | None = File(default=None),
    ):
        global _worker, _task
        if _state["running"]:
            return JSONResponse({"ok": False, "error": "already running"}, status_code=409)
        text = blob
        if file is not None and file.filename:
            raw = await file.read()
            text = (text + "\n" + raw.decode("utf-8-sig", errors="replace")).strip()
        accounts = parse_text(text)
        if not accounts:
            return JSONResponse({"ok": False, "error": "no accounts parsed"}, status_code=400)
        _logs.clear()
        _state["loaded"] = len(accounts)
        _state["results"] = []
        worker = Activator(
            headed=headed not in {"0", "false", "False"},
            channel=channel,
            timeout=timeout,
            proxy=proxy or None,
            log=_log,
        )

        async def job():
            _state["running"] = True
            try:
                results = await worker.run(accounts)
                _state["results"] = [
                    {
                        "email": r.email,
                        "status": r.status,
                        "message": r.message,
                        "project_id": r.project_id,
                        "activated": r.activated,
                    }
                    for r in results
                ]
            finally:
                _state["running"] = False

        _worker = worker
        _task = asyncio.create_task(job())
        return {"ok": True, "count": len(accounts)}

    @app.post("/api/stop")
    async def stop():
        if _worker:
            _worker.stop()
        return {"ok": True}

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
