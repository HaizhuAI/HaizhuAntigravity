from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from . import config


def _extract_project_id(data: dict | None) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("cloudaicompanionProject", "projectId", "project"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            return value["id"]
    resp = data.get("response")
    if isinstance(resp, dict):
        return _extract_project_id(resp)
    return None


async def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    client_id, client_secret = config.load_oauth_client()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            config.TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": config.REDIRECT_URI,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def userinfo(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            config.USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _post_cca(url: str, access_token: str, payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": config.USER_AGENT,
        "Client-Metadata": json.dumps(
            {
                "ideType": "ANTIGRAVITY",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        ),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"{url} -> {resp.status_code} {resp.text[:400]}")
        return resp.json() if resp.content else {}


async def load_code_assist(access_token: str) -> tuple[dict, str | None]:
    data = await _post_cca(
        f"{config.PROD_API}/{config.API_VERSION}:loadCodeAssist",
        access_token,
        {"metadata": {"ideType": "ANTIGRAVITY"}},
    )
    return data, _extract_project_id(data)


async def onboard_user(access_token: str) -> tuple[dict, str | None]:
    last: dict = {}
    for _ in range(6):
        try:
            last = await _post_cca(
                f"{config.DAILY_API}/{config.API_VERSION}:onboardUser",
                access_token,
                {
                    "tierId": "free-tier",
                    "tier_id": "free-tier",
                    "metadata": {
                        "ideType": "ANTIGRAVITY",
                        "ide_type": "ANTIGRAVITY",
                        "ideName": "antigravity",
                        "ide_name": "antigravity",
                        "ideVersion": config.IDE_VERSION,
                        "ide_version": config.IDE_VERSION,
                    },
                },
            )
        except RuntimeError as exc:
            if "429" in str(exc) or "50" in str(exc):
                await asyncio.sleep(2)
                continue
            try:
                last = await _post_cca(
                    f"{config.PROD_API}/{config.API_VERSION}:onboardUser",
                    access_token,
                    {
                        "tier_id": "free-tier",
                        "metadata": {
                            "ide_type": "ANTIGRAVITY",
                            "ide_name": "antigravity",
                            "ide_version": config.IDE_VERSION,
                        },
                    },
                )
            except Exception:
                raise exc
        if last.get("done") is True or _extract_project_id(last):
            return last, _extract_project_id(last)
        await asyncio.sleep(2)
    return last, _extract_project_id(last)


async def activate(access_token: str) -> dict[str, Any]:
    load_raw, project_id = await load_code_assist(access_token)
    onboard_raw = {}
    if not project_id:
        onboard_raw, project_id = await onboard_user(access_token)
        load_raw2, project_id2 = await load_code_assist(access_token)
        project_id = project_id or project_id2
        load_raw = load_raw2 or load_raw
    return {
        "project_id": project_id,
        "load": load_raw,
        "onboard": onboard_raw,
        "activated": bool(project_id),
    }
