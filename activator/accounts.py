from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class Account:
    email: str
    password: str
    totp_secret: str = ""
    proxy: str = ""
    recovery_email: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.email.strip().lower()


def _norm(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        key = str(k or "").strip().lower().replace(" ", "_")
        out[key] = "" if v is None else str(v).strip()
    return out


def _from_row(row: dict) -> Account | None:
    row = _norm(row)
    email = row.get("email") or row.get("account") or row.get("gmail") or row.get("user")
    password = row.get("password") or row.get("passwd") or row.get("pass")
    if not email or not password:
        return None
    totp = (
        row.get("totp")
        or row.get("totp_secret")
        or row.get("2fa")
        or row.get("otp")
        or row.get("secret")
        or ""
    )
    return Account(
        email=email,
        password=password,
        totp_secret=totp,
        proxy=row.get("proxy") or "",
        recovery_email=row.get("recovery_email") or row.get("recovery") or "",
        note=row.get("note") or "",
        extra=row,
    )


def load_accounts(path: str | Path) -> list[Account]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"account file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data if isinstance(data, list) else data.get("accounts") or data.get("items") or []
        accounts = []
        for item in rows:
            if isinstance(item, dict):
                acc = _from_row(item)
                if acc:
                    accounts.append(acc)
        return _dedupe(accounts)

    first = text.lstrip().splitlines()[0].lower() if text.strip() else ""
    has_header = any(k in first for k in ("email", "gmail", "account", "user"))
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        if has_header:
            accounts = [acc for row in csv.DictReader(fh) if (acc := _from_row(row))]
        else:
            return parse_text(text)
    return _dedupe(accounts)


def parse_text(blob: str) -> list[Account]:
    blob = blob.strip()
    if not blob:
        return []
    if blob.startswith("{") or blob.startswith("["):
        data = json.loads(blob)
        rows = data if isinstance(data, list) else data.get("accounts") or []
        return _dedupe([acc for row in rows if (acc := _from_row(row))])
    accounts = []
    for line in blob.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
        elif "----" in line:
            parts = [p.strip() for p in line.split("----")]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        else:
            parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and "@" in parts[0]:
            if parts[0].lower() in {"email", "gmail", "account"}:
                continue
            accounts.append(
                Account(
                    email=parts[0],
                    password=parts[1],
                    totp_secret=parts[2] if len(parts) > 2 else "",
                    proxy=parts[3] if len(parts) > 3 else "",
                )
            )
    return _dedupe(accounts)


def _dedupe(accounts: list[Account]) -> list[Account]:
    seen = set()
    out = []
    for acc in accounts:
        if acc.id in seen:
            continue
        seen.add(acc.id)
        out.append(acc)
    return out
