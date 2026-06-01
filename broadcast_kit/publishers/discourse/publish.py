"""Discourse publisher core · generic across instances.

Strategy:
- Generic Discourse selectors (.btn.create / .d-editor-input / .save-or-cancel)
  work across community.n8n.io / discuss.huggingface.co / etc.
- playwright-stealth for occasional Cloudflare-fronted instances
- storage_state per (account · instance_host) tuple
- Shadowban detect via Topic JSON API: fetch `/t/<topic_id>.json` anon ·
  count posts · check if account's username appears in post_stream.posts.
  Much more accurate than text-match because Discourse hides staged posts
  without leaving "removed" text in HTML.

Anti-spam reality:
- New accounts on most Discourse instances get auto-staged for staff review
- First few posts often hidden from anon view until approved (1-3 days)
- Our publish call returns success(submit went through) but shadowban_check
  catches this case
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import (
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
    # Logged-in indicator(Discourse current-user widget in header)
    "user_widget": ".current-user, .header-dropdown-toggle.current-user, [class*='current-user']",
    # Login presence
    "login_button": ".login-button, button.login-button, a[href*='/login']",
    # Topic footer Reply button(multiple fallback selectors across Discourse versions)
    "reply_btn": (
        "#topic-footer-buttons button.create, "
        ".topic-footer-main-buttons button.create, "
        "button.btn-primary.create.reply-to-post, "
        "button[title='Reply']"
    ),
    # Compose editor textarea
    "editor": "textarea.d-editor-input, .d-editor-input",
    # Submit button in composer
    "submit_btn": (
        ".save-or-cancel button.btn-primary, "
        ".composer-controls button.create, "
        "#reply-control button.btn-primary, "
        ".composer-action-title button.btn-primary"
    ),
    # Per-post permalink anchor(in .topic-post)
    "topic_post": ".topic-post",
    "post_date_link": ".post-info .post-date a, a.post-date",
}


class DiscourseError(RuntimeError):
    pass


class DiscourseLoginExpiredError(DiscourseError):
    """storage_state present but no longer accepted by the Discourse instance."""


@dataclass(frozen=True)
class DiscoursePublishResult:
    status: str  # "success" | "failed" | "session-expired"
    posted_url: str | None
    detail: str | None = None


def _apply_stealth(page: Page) -> None:
    if stealth_sync is None:
        logger.warning(
            "playwright-stealth not installed · some Cloudflare-fronted Discourse "
            "instances may block. Install with: pip install playwright-stealth"
        )
        return
    stealth_sync(page)


def _detect_logged_in(page: Page) -> bool:
    try:
        return page.locator(SELECTORS["user_widget"]).count() > 0
    except Exception:
        return False


def _extract_topic_id(topic_url: str) -> str | None:
    m = re.search(r"/t/[^/]+/(\d+)", topic_url)
    return m.group(1) if m else None


def check_login_valid(settings: Settings) -> bool:
    """Verify saved cookies still valid for the configured Discourse instance."""
    if not settings.discourse_auth_state.exists():
        return False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(settings.discourse_auth_state),
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            page.goto(settings.instance_url + "/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2.0)  # let Ember render
            valid = _detect_logged_in(page)
        except Exception as exc:
            logger.warning("check_login_valid: %s", exc)
            valid = False
        finally:
            browser.close()
        return valid


def interactive_login(
    settings: Settings,
    fresh: bool = False,
    on_ready_to_save: Callable[[], None] | None = None,
) -> Path:
    """Open headed Chromium to settings.instance_login_url · save storage_state on close.

    Discourse instances support varied login providers(email/password ·
    Google · GitHub · Discord · etc.). User picks whichever works.
    Note: Google OAuth often blocks automation-detected browsers even with
    stealth · prefer email/password or other OAuth providers.
    """
    settings.discourse_auth_state.parent.mkdir(parents=True, exist_ok=True)
    if fresh and settings.discourse_auth_state.exists():
        settings.discourse_auth_state.unlink()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(user_agent=DEFAULT_UA, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        _apply_stealth(page)
        page.goto(settings.instance_login_url, wait_until="domcontentloaded", timeout=60000)
        if on_ready_to_save is None:
            print(
                f"\n[discourse/{settings.account}@{urlparse(settings.instance_url).netloc}] "
                f"login in the headed window · "
                f"close window OR press Enter here when done...\n"
            )
            try:
                input()
            except EOFError:
                pass
        else:
            on_ready_to_save()
        context.storage_state(path=str(settings.discourse_auth_state))
        browser.close()
    return settings.discourse_auth_state


def submit_reply(
    *,
    settings: Settings,
    topic_url: str,
    body: str,
    dry_run: bool = False,
    nav_timeout_ms: int = 30000,
    reply_wait_ms: int = 15000,
) -> DiscoursePublishResult:
    """Submit a reply to a Discourse topic.

    Returns DiscoursePublishResult with posted_url(may be topic-level if
    permalink extraction fails · shadowban_check is the authoritative
    presence check).

    Raises DiscourseLoginExpiredError if session expired ·
    raises DiscourseError on other failures.
    """
    if not settings.discourse_auth_state.exists():
        raise DiscourseError(
            f"auth_state not found at {settings.discourse_auth_state} · "
            f"run: python -m broadcast_kit.publishers.discourse.cli login --fresh "
            f"--account {settings.account} --instance {settings.instance_url}"
        )

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(settings.discourse_auth_state),
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            page.goto(topic_url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            time.sleep(2.5)  # Ember render

            if not _detect_logged_in(page):
                if page.locator(SELECTORS["login_button"]).count() > 0 or "/login" in page.url:
                    raise DiscourseLoginExpiredError(
                        f"session expired · cookie no longer valid for {settings.account}@{urlparse(settings.instance_url).netloc}"
                    )
                raise DiscourseError(
                    f"user widget not found · page state ambiguous · current_url={page.url}"
                )

            reply_btn = page.locator(SELECTORS["reply_btn"]).first
            reply_btn.wait_for(timeout=reply_wait_ms)
            reply_btn.click()
            time.sleep(1.5)  # composer animate in

            editor = page.locator(SELECTORS["editor"]).first
            editor.wait_for(timeout=reply_wait_ms)

            if dry_run:
                return DiscoursePublishResult(
                    status="success",
                    posted_url="DRY_RUN",
                    detail="dry_run · editor found · no submit",
                )

            editor.fill(body)
            time.sleep(1.0)

            submit_btn = page.locator(SELECTORS["submit_btn"]).first
            submit_btn.click()
            time.sleep(4.0)  # let post render

            # Try extract permalink from last post
            try:
                last_post = page.locator(SELECTORS["topic_post"]).last
                link_el = last_post.locator(SELECTORS["post_date_link"]).first
                permalink = link_el.get_attribute("href")
            except Exception:
                permalink = None

            if permalink:
                posted_url = permalink if permalink.startswith("http") else f"{settings.instance_url}{permalink}"
            else:
                # Fallback: topic URL itself · shadowban_check will determine real status
                posted_url = topic_url
            return DiscoursePublishResult(status="success", posted_url=posted_url)

        except (DiscourseLoginExpiredError, DiscourseError):
            raise
        except PlaywrightTimeoutError as exc:
            raise DiscourseError(f"playwright timeout: {exc}") from exc
        except Exception as exc:
            raise DiscourseError(f"unexpected: {exc}") from exc
        finally:
            browser.close()


def shadowban_check(posted_url: str, account: str | None = None) -> dict:
    """Anonymous Topic JSON API check · most accurate Discourse presence detection.

    Method:
      1. Extract topic_id from posted_url
      2. anon GET <instance>/t/<topic_id>.json (no auth · just public read)
      3. Look for `account` username in post_stream.posts list
      4. If not present → suspected staged-for-review / shadowban
      5. If present but hidden=true / deleted_at!=null → also suspected

    Why JSON API not HTML scrape:
      Discourse staged posts are completely absent from anon HTML(no
      "removed" text · no placeholder)so text-match misses them.

    Returns dict:
        ok / suspected_shadowban / reason / status / post_number(if found)
    """
    topic_id = _extract_topic_id(posted_url)
    if not topic_id:
        return {
            "ok": False,
            "suspected_shadowban": False,
            "reason": "unable to extract topic_id from URL · skip check",
        }
    # build instance JSON URL: take host from posted_url
    parsed = urlparse(posted_url)
    json_url = f"{parsed.scheme}://{parsed.netloc}/t/{topic_id}.json"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        _apply_stealth(page)
        try:
            resp = page.goto(json_url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else 0
            if status >= 400:
                return {
                    "ok": False,
                    "suspected_shadowban": True,
                    "status": status,
                    "reason": f"JSON API HTTP {status}",
                }
            body_text = page.locator("body").text_content(timeout=5000) or ""
            try:
                data = json.loads(body_text)
            except Exception:
                return {
                    "ok": False,
                    "suspected_shadowban": False,
                    "error": "JSON parse fail · possibly Discourse returned HTML",
                }
            posts = data.get("post_stream", {}).get("posts", [])
            if not posts:
                return {
                    "ok": False,
                    "suspected_shadowban": True,
                    "reason": "topic has zero posts in API · topic may be deleted",
                }
            if account:
                me = next(
                    (p for p in posts if str(p.get("username", "")).lower() == account.lower()),
                    None,
                )
                if me is None:
                    usernames = ", ".join(str(p.get("username")) for p in posts[:10])
                    return {
                        "ok": False,
                        "suspected_shadowban": True,
                        "reason": (
                            f"@{account} not in topic {topic_id} post list "
                            f"({len(posts)} posts: {usernames[:100]}) · "
                            f"most likely staged for staff review"
                        ),
                    }
                if me.get("hidden") or me.get("deleted_at"):
                    return {
                        "ok": False,
                        "suspected_shadowban": True,
                        "reason": f"post #{me.get('post_number')} hidden={me.get('hidden')} deleted_at={me.get('deleted_at')}",
                    }
                return {
                    "ok": True,
                    "suspected_shadowban": False,
                    "post_number": me.get("post_number"),
                }
            # No account specified: just check topic accessibility
            return {"ok": True, "suspected_shadowban": False}
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
