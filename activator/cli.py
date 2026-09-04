from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from . import config
from .accounts import load_accounts
from .runner import Activator


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Activate Antigravity / Gemini permission by first Google login")
    p.add_argument("-i", "--input", default=str(config.DEFAULT_ACCOUNTS), help="CSV/JSON account file")
    p.add_argument("--headed", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--channel", default="chrome", help="chrome | msedge | empty for bundled chromium")
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--delay-min", type=float, default=6.0)
    p.add_argument("--delay-max", type=float, default=14.0)
    p.add_argument("--proxy", default="")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--only", default="", help="only this email")
    p.add_argument("--web", action="store_true", help="start local web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--admin-password", default="", help="set/reset WebUI admin password")
    return p


async def run_cli(args: argparse.Namespace) -> int:
    path = Path(args.input)
    accounts = load_accounts(path)
    if args.only:
        only = args.only.strip().lower()
        accounts = [a for a in accounts if a.id == only]
    if not accounts:
        print("no accounts loaded")
        return 1
    print(f"loaded {len(accounts)} accounts from {path}")
    worker = Activator(
        headed=args.headed,
        channel=args.channel,
        timeout=args.timeout,
        delay=(args.delay_min, args.delay_max),
        proxy=args.proxy or None,
        resume=not args.no_resume,
    )
    results = await worker.run(accounts)
    ok = sum(1 for r in results if r.status == "ok")
    partial = sum(1 for r in results if r.status == "partial")
    err = sum(1 for r in results if r.status == "error")
    print(f"done ok={ok} partial={partial} error={err} results={config.RESULT_PATH}")
    return 0 if err == 0 else 2


def main() -> None:
    args = build_parser().parse_args()
    if args.web:
        from .web import serve
        serve(args.host, args.port, admin_password=args.admin_password or None)
        return
    raise SystemExit(asyncio.run(run_cli(args)))


if __name__ == "__main__":
    main()
