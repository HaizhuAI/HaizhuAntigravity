from __future__ import annotations

import asyncio
import json
import random
import secrets
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright

from . import config
from .accounts import Account
from .callback import CallbackServer, code_from_url
from .google_login import complete_google_login
from .oauth import build_auth_url, generate_pkce
from .onboard import activate, exchange_code, userinfo

LogFn = Callable[[str], None]


@dataclass
class JobResult:
    email: str
    status: str
    message: str = ""
    project_id: str | None = None
    oauth_email: str | None = None
    activated: bool = False
    started_at: str = ""
    finished_at: str = ""
    extra: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_email(email: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in email)


class Activator:
    def __init__(
        self,
        *,
        headed: bool = True,
        channel: str = "chrome",
        timeout: float = 180.0,
        delay: tuple[float, float] = (6.0, 14.0),
        proxy: str | None = None,
        resume: bool = True,
        log: LogFn | None = None,
    ) -> None:
        self.headed = headed
        self.channel = channel
        self.timeout = timeout
        self.delay = delay
        self.proxy = proxy
        self.resume = resume
        self.log = log or (lambda msg: print(msg, flush=True))
        self.results: list[JobResult] = []
        self._stop = asyncio.Event()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        self._stop.set()

    def _done_emails(self) -> set[str]:
        done = set()
        if not config.RESULT_PATH.exists():
            return done
        for line in config.RESULT_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("activated") or row.get("status") == "ok":
                done.add((row.get("email") or "").lower())
        return done

    def _write_result(self, result: JobResult) -> None:
        with config.RESULT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    def _save_token(self, email: str, payload: dict) -> Path:
        path = config.TOKEN_DIR / f"{_safe_email(email)}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    async def run(self, accounts: list[Account]) -> list[JobResult]:
        skip = self._done_emails() if self.resume else set()
        cb = CallbackServer()
        await cb.start()
        self.log(f"OAuth callback listening on {config.REDIRECT_URI}")
        try:
            async with async_playwright() as pw:
                for idx, acc in enumerate(accounts, 1):
                    if self._stop.is_set():
                        self.log("stopped")
                        break
                    if acc.id in skip:
                        self.log(f"[{idx}/{len(accounts)}] skip already activated {acc.email}")
                        continue
                    self.log(f"[{idx}/{len(accounts)}] start {acc.email}")
                    result = await self._run_one(pw, cb, acc)
                    self.results.append(result)
                    self._write_result(result)
                    self.log(f"[{idx}/{len(accounts)}] {acc.email} -> {result.status} {result.message}")
                    if idx < len(accounts) and not self._stop.is_set():
                        wait = random.uniform(*self.delay)
                        self.log(f"sleep {wait:.1f}s")
                        await asyncio.sleep(wait)
        finally:
            await cb.close()
        return self.results

    async def _run_one(self, pw, cb: CallbackServer, acc: Account) -> JobResult:
        result = JobResult(email=acc.email, status="running", started_at=_now())
        cb.reset()
        verifier, challenge = generate_pkce()
        state = secrets.token_urlsafe(24)
        auth_url = build_auth_url(challenge, state)
        browser = None
        context = None
        try:
            launch_kwargs: dict = {
                "headless": not self.headed,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                "ignore_default_args": ["--enable-automation"],
            }
            channel = (self.channel or "").strip().lower()
            if channel and channel not in {"chromium", "none", "bundled"}:
                launch_kwargs["channel"] = channel
            proxy = acc.proxy or self.proxy
            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}
            try:
                browser = await pw.chromium.launch(**launch_kwargs)
            except Exception as exc:
                if channel:
                    self.log(f"channel={channel} launch failed ({exc}), fallback chromium")
                    launch_kwargs.pop("channel", None)
                    browser = await pw.chromium.launch(**launch_kwargs)
                else:
                    raise
            context = await browser.new_context(
                user_agent=config.CHROME_UA,
                locale="en-US",
                viewport={"width": 1280, "height": 860},
            )
            await context.add_init_script(config.STEALTH_JS)
            page = await context.new_page()
            await page.goto(auth_url, wait_until="domcontentloaded")
            login_task = asyncio.create_task(
                complete_google_login(page, acc.email, acc.password, acc.totp_secret, self.log, self.timeout)
            )
            wait_task = asyncio.create_task(cb.wait_code(self.timeout))
            pending: set[asyncio.Task] = {login_task, wait_task}
            try:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                code = None
                errors = []
                for task in done:
                    try:
                        value = task.result()
                        if isinstance(value, str) and value:
                            code = value
                    except Exception as exc:
                        errors.append(str(exc))
                if not code:
                    code = code_from_url(page.url)
                if not code:
                    raise RuntimeError(errors[0] if errors else "no OAuth code")
            finally:
                for task in pending:
                    task.cancel()
            tokens = await exchange_code(code, verifier)
            access = tokens.get("access_token")
            if not access:
                raise RuntimeError(f"token exchange missing access_token: {tokens}")
            info = {}
            try:
                info = await userinfo(access)
            except Exception as exc:
                self.log(f"userinfo failed: {exc}")
            onboard = await activate(access)
            payload = {
                "email": acc.email,
                "oauth_email": info.get("email"),
                "tokens": tokens,
                "userinfo": info,
                "onboard": onboard,
                "saved_at": _now(),
            }
            token_path = self._save_token(acc.email, payload)
            result.status = "ok" if onboard.get("activated") else "partial"
            result.activated = bool(onboard.get("activated"))
            result.project_id = onboard.get("project_id")
            result.oauth_email = info.get("email")
            result.message = (
                f"project={result.project_id or '-'} token={token_path.name}"
                if result.activated
                else "OAuth ok but Cloud Code Assist project missing"
            )
            result.extra = {"currentUserTier": (onboard.get("load") or {}).get("currentUserTier")}
            return result
        except Exception as exc:
            result.status = "error"
            result.message = str(exc)
            result.extra = {"trace": traceback.format_exc()[-1500:]}
            return result
        finally:
            result.finished_at = _now()
            try:
                if context:
                    await context.close()
            except Exception:
                pass
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass
