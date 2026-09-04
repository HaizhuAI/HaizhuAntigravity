from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TOKEN_DIR = DATA_DIR / "tokens"
RESULT_PATH = DATA_DIR / "results.jsonl"
DEFAULT_ACCOUNTS = ROOT / "accounts.csv"

CLIENT_ID = os.environ.get("GOOGLE_ANTIGRAVITY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_ANTIGRAVITY_CLIENT_SECRET", "").strip()


def load_oauth_client() -> tuple[str, str]:
    cid = os.environ.get("GOOGLE_ANTIGRAVITY_CLIENT_ID", "").strip() or CLIENT_ID
    csec = os.environ.get("GOOGLE_ANTIGRAVITY_CLIENT_SECRET", "").strip() or CLIENT_SECRET
    cred_path = ROOT / "credentials.json"
    if cred_path.exists():
        import json

        data = json.loads(cred_path.read_text(encoding="utf-8"))
        cid = cid or str(data.get("client_id") or "").strip()
        csec = csec or str(data.get("client_secret") or "").strip()
    if not cid or not csec:
        raise RuntimeError(
            "Missing Antigravity OAuth client. Set GOOGLE_ANTIGRAVITY_CLIENT_ID / "
            "GOOGLE_ANTIGRAVITY_CLIENT_SECRET, or copy credentials.example.json to credentials.json"
        )
    return cid, csec
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
PROD_API = "https://cloudcode-pa.googleapis.com"
DAILY_API = "https://daily-cloudcode-pa.googleapis.com"
API_VERSION = "v1internal"

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 51121
CALLBACK_PATH = "/oauth-callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

USER_AGENT = "antigravity/1.107.0 windows/amd64"
IDE_VERSION = "1.107.0"
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
"""
