# HaizhuAntigravity

Batch-activate Google Antigravity / Gemini permission by completing one official first login.

Import `email,password,totp`, run Google OAuth for the Antigravity client, then call Cloud Code Assist `loadCodeAssist` / `onboardUser`. A successful first login stores `project_id` and tokens for that account.

## Flow

1. Load accounts from CSV / JSON / paste
2. Listen on `http://localhost:51121/oauth-callback`
3. Playwright opens the Antigravity OAuth page
4. Fill email, password, Authenticator TOTP, click Allow
5. Exchange code for tokens
6. `loadCodeAssist`; if no project, `onboardUser`
7. Write tokens to `data/tokens/` and append `data/results.jsonl`

SMS / passkey / CAPTCHA are not force-solved. The browser stays open so you can finish them by hand.

## Install

```powershell
git clone https://github.com/HaizhuAI/HaizhuAntigravity.git
cd HaizhuAntigravity
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chrome
```

If Chrome is missing:

```powershell
python -m playwright install chromium
python run.py -i accounts.csv --channel chromium
```

## OAuth client

GitHub blocks committing Google OAuth client strings. Copy `credentials.example.json` to `credentials.json` and fill the Antigravity **desktop public OAuth client** (`client_id` / `client_secret`). Those values live in the official Antigravity / `agy` install, not your Google password.

You can also set:

```powershell
$env:GOOGLE_ANTIGRAVITY_CLIENT_ID = "...."
$env:GOOGLE_ANTIGRAVITY_CLIENT_SECRET = "...."
```

`credentials.json` is gitignored.

## Accounts

Copy `accounts.example.csv` to `accounts.csv`:

```csv
email,password,totp,proxy
you@gmail.com,your-password,BASE32SECRET,
```

Also supported: JSON array, `email|password|totp`, `email----password----totp`, or a full `otpauth://totp/...` URL.

Do not commit `accounts.csv`. It is gitignored.

## Run

CLI:

```powershell
copy accounts.example.csv accounts.csv
python run.py -i accounts.csv --channel chrome
```

Web UI:

```powershell
python run.py --web --host 127.0.0.1 --port 8787
```

Open http://127.0.0.1:8787

First visit sets the admin password. Later visits require that password.
Optional reset:

```powershell
python run.py --web --admin-password "your-admin-password"
```

Useful flags:

- `--headed` / `--no-headed`
- `--timeout 180`
- `--proxy http://127.0.0.1:7890`
- `--only you@gmail.com`
- `--no-resume`

`--proxy` accepts `http://host:port` and `socks5://user:pass@host:port`. SOCKS5 with auth is relayed through a local SK5 port because Chrome cannot speak authenticated SOCKS5. If `--proxy` is empty, the runner probes `127.0.0.1:7897/7890/10808/1080`.

## Output

- `data/results.jsonl` - status / project_id / error
- `data/tokens/<email>.json` - access_token / refresh_token / onboard payload

`status=ok` with `project_id` means activation succeeded. `partial` means OAuth worked but CCA project was not created (region / age / Workspace / risk control).

## Notes

- Real Chrome in headed mode is more stable; headless often hits "This browser or app may not be secure"
- Unsupported region IPs frequently return not eligible
- Workspace / under-18 / unsupported country accounts can login and still get no permission
- Do not run two browsers against port 51121 at the same time
- Login uses a real Chrome process over CDP, not Playwright's bundled Chromium
- Playwright-launched Chrome ignores Windows "system proxy" unless TUN mode is on; pass `--proxy` or run a local mixed port
- Saved Chrome profiles reuse Google sessions. The activator picks the matching email on the account chooser instead of clicking Use another account.
- If Google shows Make sure you downloaded this app from Google, click Sign in. Cancel produces access_denied.
- Android device prompts stay on screen for a manual tap; the callback keeps listening until timeout.
