from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import pyotp


def normalize_secret(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("otpauth://"):
        qs = parse_qs(urlparse(raw).query)
        secret = (qs.get("secret") or [""])[0]
        return unquote(secret).replace(" ", "").upper()
    return re.sub(r"\s+", "", raw).upper()


def current_code(raw: str) -> str:
    secret = normalize_secret(raw)
    if not secret:
        raise ValueError("empty totp secret")
    return pyotp.TOTP(secret).now()
