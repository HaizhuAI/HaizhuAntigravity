from __future__ import annotations

import asyncio
import random
from typing import Callable

from playwright.async_api import Page

from .callback import code_from_url
from .totp import current_code

LogFn = Callable[[str], None]


async def _human_type(locator, text: str) -> None:
    await locator.click()
    await locator.fill("")
    for ch in text:
        await locator.type(ch, delay=random.randint(35, 95))


async def _visible(page: Page, selector: str) -> bool:
    loc = page.locator(selector).first
    try:
        return await loc.is_visible(timeout=400)
    except Exception:
        return False


async def _click_first(page: Page, selectors: list[str]) -> bool:
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.is_visible(timeout=500):
                await loc.click()
                return True
        except Exception:
            continue
    return False


async def _text(page: Page) -> str:
    try:
        return (await page.inner_text("body")).lower()
    except Exception:
        return ""


async def _fill_if_empty(page: Page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.is_visible(timeout=400):
                current = await loc.input_value()
                if current.strip() == value:
                    return True
                await _human_type(loc, value)
                return True
        except Exception:
            continue
    return False


NEXT_BUTTONS = [
    "#identifierNext button",
    "#identifierNext",
    "#passwordNext button",
    "#passwordNext",
    "#totpNext button",
    "#totpNext",
    'button:has-text("Next")',
    'button:has-text("下一步")',
    'button:has-text("Continue")',
    'button:has-text("继续")',
    'button:has-text("Verify")',
    'button:has-text("验证")',
    "#submit",
    'button[type="submit"]',
]

CONSENT_BUTTONS = [
    'button:has-text("Allow")',
    'button:has-text("允许")',
    'button:has-text("Continue")',
    'button:has-text("继续")',
    "#submit_approve_access",
    "#confirm",
]

TRY_ANOTHER = [
    'button:has-text("Try another way")',
    'button:has-text("尝试其他方式")',
    'button:has-text("Try another method")',
    'text=Try another way',
    'text=尝试其他方式',
]

AUTHENTICATOR_CHOICES = [
    'div[role="link"]:has-text("Google Authenticator")',
    'div[role="link"]:has-text("Authenticator")',
    'div[role="link"]:has-text("身份验证器")',
    'li:has-text("Google Authenticator")',
    'li:has-text("Authenticator app")',
    'li:has-text("身份验证器应用")',
    'div:has-text("Enter a verification code from the Authenticator app")',
    'text=Get a verification code from the Google Authenticator app',
]


async def complete_google_login(
    page: Page,
    email: str,
    password: str,
    totp_secret: str,
    log: LogFn,
    timeout: float = 180.0,
) -> str:
    email_filled = False
    password_filled = False
    totp_filled = False
    another_clicked = False
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        url = page.url
        code = code_from_url(url)
        if code:
            log("OAuth code captured from browser URL")
            return code

        body = await _text(page)

        if any(s in body for s in [
            "couldn't sign you in",
            "this browser or app may not be secure",
            "此浏览器或应用可能不安全",
            "无法登录",
        ]):
            raise RuntimeError("Google blocked this browser (not secure). Use --channel chrome and headed mode.")

        if any(s in body for s in [
            "not eligible for antigravity",
            "age unverified",
            "couldn't verify your info",
            "当前账号不符合",
        ]):
            raise RuntimeError("Account not eligible for Antigravity")

        if "captcha" in url or "recaptcha" in body:
            log("CAPTCHA shown, waiting for manual solve in the open window")
            await page.wait_for_timeout(3000)
            continue

        if not email_filled:
            if await _fill_if_empty(page, ['input[type="email"]', "#identifierId", 'input[name="identifier"]'], email):
                email_filled = True
                log(f"filled email {email}")
                await page.wait_for_timeout(400)
                await _click_first(page, NEXT_BUTTONS)
                await page.wait_for_timeout(1200)
                continue

        if not password_filled:
            if await _fill_if_empty(page, ['input[name="Passwd"]', 'input[type="password"]', 'input[name="password"]'], password):
                password_filled = True
                log("filled password")
                await page.wait_for_timeout(400)
                await _click_first(page, NEXT_BUTTONS)
                await page.wait_for_timeout(1500)
                continue

        if totp_secret and not totp_filled:
            totp_visible = await _visible(page, 'input[name="totpPin"]') or await _visible(page, "#totpPin")
            if totp_visible or "authenticator" in body or "验证器" in body or "verification code" in body:
                if not totp_visible and not another_clicked:
                    if await _click_first(page, TRY_ANOTHER):
                        another_clicked = True
                        log("clicked try another way")
                        await page.wait_for_timeout(800)
                    await _click_first(page, AUTHENTICATOR_CHOICES)
                    await page.wait_for_timeout(800)

                code6 = current_code(totp_secret)
                if await _fill_if_empty(page, ['input[name="totpPin"]', "#totpPin", 'input[autocomplete="one-time-code"]'], code6):
                    totp_filled = True
                    log(f"filled TOTP {code6}")
                    await page.wait_for_timeout(300)
                    await _click_first(page, NEXT_BUTTONS)
                    await page.wait_for_timeout(1500)
                    continue

        if any(s in body for s in ["confirm your recovery", "recovery email", "辅助邮箱", "验证身份"]):
            log("recovery / extra identity challenge, waiting for manual action")

        if any(s in body for s in ["passkey", "使用通行密钥", "use your passkey"]):
            if await _click_first(page, TRY_ANOTHER + ['button:has-text("Not now")', 'button:has-text("以后再说")', 'button:has-text("Cancel")']):
                log("skipped passkey prompt")
                await page.wait_for_timeout(800)
                continue

        if await _click_first(page, [
            'button:has-text("I understand")',
            'button:has-text("Not now")',
            'button:has-text("Skip")',
            'button:has-text("以后再说")',
            'button:has-text("跳过")',
            'button:has-text("取消")',
        ]):
            await page.wait_for_timeout(600)

        if "consent" in url or "access" in body and ("google will allow" in body or "want to access" in body or "将允许" in body or "要访问" in body):
            if await _click_first(page, CONSENT_BUTTONS):
                log("clicked OAuth consent")
                await page.wait_for_timeout(1200)
                continue

        await page.wait_for_timeout(700)

    raise TimeoutError("Google login did not finish before timeout")
