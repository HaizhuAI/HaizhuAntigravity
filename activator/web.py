from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .accounts import Account
from .runner import Activator

STATIC = Path(__file__).resolve().parent / "static"
ADMIN_PATH = config.DATA_DIR / "admin.json"
COOKIE_NAME = "haizhu_session"

_logs: list[str] = []
_state: dict[str, Any] = {
    "running": False,
    "loaded": 0,
    "results": [],
    "current": "",
}
_worker: Activator | None = None
_task: asyncio.Task | None = None
_session_secret = secrets.token_hex(32)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(msg: str) -> None:
    line = f"[{_now()}] {msg}"
    _logs.append(line)
    if len(_logs) > 3000:
        del _logs[:800]
    print(line, flush=True)


def _load_admin() -> dict:
    if not ADMIN_PATH.exists():
        return {}
    try:
        return json.loads(ADMIN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_admin(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000).hex()


def set_admin_password(password: str) -> None:
    password = (password or "").strip()
    if len(password) < 6:
        raise ValueError("admin password must be at least 6 characters")
    data = _load_admin()
    salt = secrets.token_hex(16)
    data["salt"] = salt
    data["hash"] = _hash_password(password, salt)
    data["session_secret"] = data.get("session_secret") or secrets.token_hex(32)
    _save_admin(data)


def _password_ready() -> bool:
    data = _load_admin()
    return bool(data.get("salt") and data.get("hash"))


def _verify_password(password: str) -> bool:
    data = _load_admin()
    salt = data.get("salt") or ""
    expected = data.get("hash") or ""
    if not salt or not expected:
        return False
    got = _hash_password(password, salt)
    return hmac.compare_digest(got, expected)


def _session_secret_value() -> str:
    data = _load_admin()
    secret = data.get("session_secret") or os.environ.get("HAIZHU_SESSION_SECRET") or _session_secret
    if not data.get("session_secret"):
        data["session_secret"] = secret
        _save_admin(data)
    return secret


def _authed(request: Request) -> bool:
    if not _password_ready():
        return False
    token = request.session.get("auth")
    data = _load_admin()
    expected = data.get("hash") or ""
    exp = int(request.session.get("exp") or 0)
    return bool(token and expected and token == expected and exp > time.time())


def _deny() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)


def _dump_results(rows: list) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "email": r.email,
                "status": r.status,
                "message": r.message,
                "project_id": r.project_id,
                "activated": r.activated,
            }
        )
    return out


def create_app(admin_password: str | None = None) -> FastAPI:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    env_pw = os.environ.get("HAIZHU_ADMIN_PASSWORD", "").strip()
    if admin_password:
        set_admin_password(admin_password)
    elif env_pw and not _password_ready():
        set_admin_password(env_pw)

    app = FastAPI(title="HaizhuAntigravity")
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret_value(),
        session_cookie=COOKIE_NAME,
        same_site="lax",
        https_only=False,
        max_age=7 * 24 * 3600,
    )

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        return {
            "ok": True,
            "need_setup": not _password_ready(),
            "authenticated": _authed(request),
        }

    @app.post("/api/auth/setup")
    async def auth_setup(request: Request):
        if _password_ready():
            return JSONResponse({"ok": False, "error": "admin password already set"}, status_code=400)
        body = await request.json()
        password = str(body.get("password") or "")
        confirm = str(body.get("confirm") or password)
        if password != confirm:
            return JSONResponse({"ok": False, "error": "passwords do not match"}, status_code=400)
        try:
            set_admin_password(password)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        request.session["auth"] = _load_admin()["hash"]
        request.session["exp"] = int(time.time()) + 7 * 24 * 3600
        return {"ok": True}

    @app.post("/api/auth/login")
    async def auth_login(request: Request):
        if not _password_ready():
            return JSONResponse({"ok": False, "error": "setup required"}, status_code=400)
        body = await request.json()
        password = str(body.get("password") or "")
        if not _verify_password(password):
            await asyncio.sleep(0.4)
            return JSONResponse({"ok": False, "error": "wrong password"}, status_code=401)
        request.session["auth"] = _load_admin()["hash"]
        request.session["exp"] = int(time.time()) + 7 * 24 * 3600
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        request.session.clear()
        return {"ok": True}

    @app.get("/api/status")
    async def status(request: Request):
        if not _authed(request):
            return _deny()
        return {
            "ok": True,
            "running": _state["running"],
            "loaded": _state["loaded"],
            "current": _state["current"],
            "results": _state["results"][-200:],
            "logs": _logs[-400:],
        }

    @app.post("/api/start")
    async def start(request: Request):
        global _worker, _task
        if not _authed(request):
            return _deny()
        if _state["running"]:
            return JSONResponse({"ok": False, "error": "already running"}, status_code=409)
        body = await request.json()
        rows = body.get("accounts") or []
        accounts: list[Account] = []
        for row in rows:
            email = str(row.get("email") or "").strip()
            password = str(row.get("password") or "").strip()
            if not email or not password:
                continue
            accounts.append(
                Account(
                    email=email,
                    password=password,
                    totp_secret=str(row.get("totp") or row.get("totp_secret") or row.get("2fa") or "").strip(),
                    proxy=str(row.get("proxy") or "").strip(),
                )
            )
        if not accounts:
            return JSONResponse({"ok": False, "error": "no accounts"}, status_code=400)
        _logs.clear()
        _state["loaded"] = len(accounts)
        _state["results"] = []
        _state["current"] = accounts[0].email
        _log(f"queue {len(accounts)} account(s)")
        worker = Activator(
            headed=bool(body.get("headed", True)),
            channel=str(body.get("channel") or "chrome"),
            timeout=float(body.get("timeout") or 180),
            proxy=str(body.get("proxy") or "") or None,
            resume=bool(body.get("resume", False)),
            log=_log,
        )

        async def job():
            _state["running"] = True
            try:
                run_task = asyncio.create_task(worker.run(accounts))
                while not run_task.done():
                    _state["results"] = _dump_results(worker.results)
                    done = len(worker.results)
                    if done < len(accounts):
                        _state["current"] = accounts[done].email
                    await asyncio.sleep(0.35)
                await run_task
                _state["results"] = _dump_results(worker.results)
                ok = sum(1 for r in worker.results if r.status == "ok")
                _log(f"finished ok={ok}/{len(worker.results)}")
            except Exception as exc:
                _log(f"job crashed: {exc}")
            finally:
                _state["running"] = False
                _state["current"] = ""

        _worker = worker
        _task = asyncio.create_task(job())
        return {"ok": True, "count": len(accounts)}

    @app.post("/api/stop")
    async def stop(request: Request):
        if not _authed(request):
            return _deny()
        if _worker:
            _worker.stop()
            _log("stop requested")
        return {"ok": True}

    @app.get("/api/logs/stream")
    async def log_stream(request: Request):
        if not _authed(request):
            return _deny()

        async def gen():
            idx = 0
            while True:
                if await request.is_disconnected():
                    break
                payload = {
                    "logs": _logs[idx:],
                    "running": _state["running"],
                    "current": _state["current"],
                    "loaded": _state["loaded"],
                    "results": _state["results"][-200:],
                }
                idx = len(_logs)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.4)

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def serve(host: str, port: int, admin_password: str | None = None) -> None:
    import uvicorn

    if admin_password:
        set_admin_password(admin_password)
        print(f"admin password saved -> {ADMIN_PATH}")
    elif not _password_ready():
        print("admin password not set. Open the UI to create one, or pass --admin-password")
    uvicorn.run(create_app(admin_password=None), host=host, port=port, log_level="info")
