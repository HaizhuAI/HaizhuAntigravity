from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from . import config


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def build_auth_url(challenge: str, state: str) -> str:
    client_id, _ = config.load_oauth_client()
    params = {
        "client_id": client_id,
        "redirect_uri": config.REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(config.SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{config.AUTH_ENDPOINT}?{urlencode(params)}"
