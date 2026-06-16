"""Reddit publisher core: stealth + storage_state + old.reddit OP reply submit.

Strategy:
- old.reddit.com for stability(new Reddit React UI changes frequently)
- playwright-stealth to bypass Cloudflare browser-integrity check
- storage_state JSON per account
- OP-level reply only(not nested comment reply · keeps publisher simple)
- 5-min anonymous fetch shadowban detection
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

try:
    from playwright_stealth import stealth_sync  # type: ignore
except ImportError:  # pragma: no cover
    stealth_sync = None  # type: ignore

from .config import Settings


logger = logging.getLogger(__name__)


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


SELECTORS = {
    # Logged-in indicators(old.reddit)
    "user_widget": "#header-bottom-right a.user, .user a[href*='/user/']",
    # OP-level reply form(at top of .commentarea)
    "op_reply_textarea": ".commentarea > .usertext .usertext-edit textarea[name='text']",
    "op_reply_save_btn": ".commentarea > .usertext button.save, .commentarea > .usertext input[type='submit'][value='save']",
    # Comment listing
    "first_comment": ".commentarea .comment",
    "comment_permalink": "a.bylink",
    # Login marker · if we see this after profile-restore · session expired
    "login_link": "a[href*='/login']",
}


class RedditError(RuntimeError):
    pass


class RedditLoginExpiredError(RedditError):
    """Storage state is present but Reddit no longer accepts it.

    Caller should re-run `python -m broadcast_kit.publishers.reddit.cli login --fresh --account <handle>`.
    """


@dataclass(frozen=True)
class RedditPublishResult:
    status: str  # "success" | "failed" | "session-expired"
    posted_url: str | None
    detail: str | None = None


def _to_old_reddit(url: str) -> str:
    return re.sub(
        r"https?://(?:www\.|new\.|np\.)?reddit\.com",
        "https://old.reddit.com",
        url,
        flags=re.IGNORECASE,
    )


def _apply_stealth(page: Page) -> None:
    """Apply stealth patches if playwright-stealth is installed."""
    if stealth_sync is None:
        logger.warning(
            "playwright-stealth not installed · Reddit may block via Cloudflare. "
            "Install with: pip install playwright-stealth"
        )
        return
    stealth_sync(page)


def _detect_logged_in(page: Page) -> bool:
    """Check if current page shows logged-in user."""
    try:
        return page.locator(SELECTORS["user_widget"]).count() > 0
    except Exception:
        return False


def check_login_valid(settings: Settings) -> bool:
    """Verify saved Reddit cookies still work.

    Launches headless Chromium · navigates to /me/ · checks for redirect to user page.
    Returns False if storage_state missing or session expired.
    """
    if not settings.reddit_auth_state.exists():
        return False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(settings.reddit_auth_state),
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            page.goto(settings.logged_in_check_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
            valid = _detect_logged_in(page)
        except Exception as exc:
            logger.warning("check_login_valid: navigation failed · %s", exc)
            valid = False
        finally:
            browser.close()
        return valid


def interactive_login(
    settings: Settings,
    fresh: bool = False,
    on_ready_to_save: Callable[[], None] | None = None,
) -> Path:
    """Open a visible Chromium · let user log in · save storage_state.

    Args:
        settings: Reddit Settings(provides auth_state path + login_url).
        fresh: If True · delete any existing auth state before launching.
        on_ready_to_save: Optional callback to signal "user finished login · save now".
                          Must block until ready. If None · falls back to input() prompt.
    Returns:
        Path to saved storage_state JSON.
    """
    settings.reddit_auth_state.parent.mkdir(parents=True, exist_ok=True)
    if fresh and settings.reddit_auth_state.exists():
        settings.reddit_auth_state.unlink()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(user_agent=DEFAULT_UA, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        _apply_stealth(page)
        page.goto(settings.login_url, wait_until="domcontentloaded", timeout=60000)
        if on_ready_to_save is None:
            print(
                f"\n[reddit/{settings.account}] login in the headed Chromium window · "
                f"close window OR press Enter here when done...\n"
            )
            try:
                input()
            except EOFError:
                pass
        else:
            on_ready_to_save()
        context.storage_state(path=str(settings.reddit_auth_state))
        browser.close()
    return settings.reddit_auth_state


def submit_comment(
    *,
    settings: Settings,
    thread_url: str,
    body: str,
    dry_run: bool = False,
    nav_timeout_ms: int = 30000,
    reply_wait_ms: int = 10000,
) -> RedditPublishResult:
    """Submit an OP-level reply comment to a Reddit thread.

    Returns RedditPublishResult with posted_url(permalink to the new comment).
    Raises RedditLoginExpiredError if session no longer valid.
    Raises RedditError on other failures.
    """
    if not settings.reddit_auth_state.exists():
        raise RedditError(
            f"auth_state not found at {settings.reddit_auth_state} · "
            f"run: python -m broadcast_kit.publishers.reddit.cli login --fresh --account {settings.account}"
        )

    old_url = _to_old_reddit(thread_url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(settings.reddit_auth_state),
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            page.goto(old_url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            time.sleep(1.0)

            # logged-in check
            if not _detect_logged_in(page):
                if page.locator(SELECTORS["login_link"]).count() > 0:
                    raise RedditLoginExpiredError(
                        f"session expired · cookie no longer valid for {settings.account}"
                    )
                raise RedditError(
                    "user widget not found and no login link · page state ambiguous"
                )

            # find OP-level reply textarea
            textarea = page.locator(SELECTORS["op_reply_textarea"]).first
            textarea.wait_for(timeout=reply_wait_ms)

            if dry_run:
                return RedditPublishResult(
                    status="success",
                    posted_url="DRY_RUN",
                    detail="dry_run · textarea found · no submit",
                )

            textarea.fill(body)
            time.sleep(0.8)

            save_btn = page.locator(SELECTORS["op_reply_save_btn"]).first
            save_btn.click()
            time.sleep(3.5)  # let new comment render

            # extract permalink of newest comment
            try:
                first_comment = page.locator(SELECTORS["first_comment"]).first
                permalink = first_comment.locator(SELECTORS["comment_permalink"]).first.get_attribute("href")
            except Exception:
                permalink = None

            if not permalink:
                raise RedditError(
                    "submit done but permalink not found · likely AutoMod removed immediately"
                )
            posted_url = permalink if permalink.startswith("http") else f"https://old.reddit.com{permalink}"
            return RedditPublishResult(status="success", posted_url=posted_url)

        except (RedditLoginExpiredError, RedditError):
            raise
        except PlaywrightTimeoutError as exc:
            raise RedditError(f"playwright timeout: {exc}") from exc
        except Exception as exc:
            raise RedditError(f"unexpected: {exc}") from exc
        finally:
            browser.close()


def shadowban_check(posted_url: str, _account: str | None = None) -> dict:
    """Anonymous fetch posted_url · check if shadowbanned by AutoMod or removed.

    Returns dict:
        ok: bool
        suspected_shadowban: bool
        status: HTTP status code(if available)
        reason: text describing detection signal

    Method: launches anon Chromium · navigates posted_url · checks for "[removed]"
    / "removed by mod" / "page not found" patterns in body text. 5-min wait
    before calling this is recommended (lets AutoMod settle).
    """
    tmp_state = f"/tmp/bk-anon-{int(time.time() * 1000)}.json"
    Path(tmp_state).write_text("{}", encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            resp = page.goto(posted_url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else 0
            if status >= 400:
                return {
                    "ok": False,
                    "suspected_shadowban": True,
                    "status": status,
                    "reason": f"HTTP {status}",
                }
            time.sleep(1.0)
            body_text = page.locator("body").text_content(timeout=5000) or ""
            if re.search(
                r"\[removed\]|removed by moderators|This (post|thread|comment) was removed|page not found",
                body_text,
                re.IGNORECASE,
            ):
                return {
                    "ok": False,
                    "suspected_shadowban": True,
                    "status": status,
                    "reason": "removed-text detected in anon view",
                }
            return {"ok": True, "suspected_shadowban": False, "status": status}
        except Exception as exc:
            return {
                "ok": False,
                "suspected_shadowban": False,
                "error": str(exc)[:200],
            }
        finally:
            browser.close()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
