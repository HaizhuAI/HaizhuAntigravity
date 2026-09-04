# HaizhuAntigravity Design

## Brief

- Product: operator console for first-login Antigravity activation
- Audience: the account owner running batch Google login locally
- Primary task: authenticate as admin, enter email / password / TOTP / proxy, ignite one run, watch the process log
- Platform: FastAPI + one static HTML page, desktop first, usable on phone
- Constraints: no React, no extra frontend build, Chinese UI, session cookie auth

## Visual thesis

Mission hangar, not a SaaS marketing page. Deep sea-ink surfaces, bone type, one copper instrument light, one ignition red for the only irreversible action. Typography is editorial serif for the name and industrial sans for controls. Motion is short feedback, never decoration.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0e1a21` | page |
| `--bg-2` | `#13242d` | panels |
| `--ink` | `#f3eee4` | primary text |
| `--muted` | `#93a29c` | labels, hints |
| `--line` | `#2b414b` | borders |
| `--copper` | `#e08a3d` | focus, status, secondary emphasis |
| `--ignite` | `#ff5a3c` | 一键激活 |
| `--ok` | `#3dba8b` | success |
| `--warn` | `#e2b15a` | partial |
| `--bad` | `#ff6b4a` | error |
| `--radius` | `12px` | cards |
| `--control` | `8px` | inputs / buttons |
| `--space` | `8 / 12 / 16 / 24 / 40` | density |

Display type: `"Fraunces", "Iowan Old Style", "Songti SC", serif`
UI type: `"Bahnschrift", "Segoe UI Variable", "PingFang SC", "Microsoft YaHei", sans-serif`
Mono: `"Cascadia Mono", "Sarasa Mono SC", "Consolas", monospace`

## Motion

- Gate: 280ms opacity + 12px rise
- Controls: 120ms color / translate on hover-press
- Running pill: opacity pulse
- Reduced motion: no pulse, no entrance, instant state color

## States

Every control has default, hover, focus-visible, active, disabled.
Forms expose error text with `role="alert"`.
Logs use `aria-live="polite"`.
Empty queue has a written empty state, not a blank table.

## Anti-patterns

No purple, no rainbow gradient, no glass stack, no pill-every-button, no animation on every card.
