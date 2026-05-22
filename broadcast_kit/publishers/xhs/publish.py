from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .config import Settings


logger = logging.getLogger(__name__)


SELECTORS = {
    "image_inputs": "input[type='file'][accept*='image'], input[type='file'][accept*='jpg'], input[type='file'][accept*='jpeg'], input[type='file'][accept*='png'], input[type='file'][accept*='webp']",
    "video_inputs": "input[type='file'][accept*='video']",
    "title_input": "input[placeholder*='标题'], input[placeholder*='起一个'], input[placeholder*='点击输入标题']",
    "body_editor": "[contenteditable='true'], textarea[placeholder*='正文'], textarea[placeholder*='添加正文'], [data-placeholder*='添加正文']",
    "topic_button": "text=话题, button:has-text('话题'), [class*='topic-btn']",
    "topic_input": "input[placeholder*='话题'], input[placeholder*='输入话题']",
    "topic_candidates": "[class*='topic-item'], [class*='topic-option'], li:has-text('#')",
    "publish_button": "button:has-text('发布'), text=发布, .xhs-publish-btn, [class*='publish-btn']",
    "login_markers": "扫码登录|请登录|手机号登录|登录抖音",
    "success_markers": "发布成功|笔记发布成功|published",
    "upload_tab_image": "text=上传图文, text=图文",
    "upload_tab_video": "text=上传视频, text=视频",
}


class XhsError(RuntimeError):
    pass


class XhsLoginExpiredError(XhsError):
    """Storage state is present but no longer accepted by creator.xiaohongshu.com.

    Caller should run `python -m broadcast_kit.publishers.xhs.cli login --fresh`
    (or the equivalent in their own wrapper) and retry.
    """


@dataclass(frozen=True)
class XhsUploadResult:
    verdict: str
    detail: str
    screenshots: list[Path]
    submitted: bool
    note_url: str | None
    selected_topics: list[str] = field(default_factory=list)
    submit_requested: bool = False
    submit_effective: bool = False


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _screenshot(page: Page, settings: Settings, stage: str, timestamp: str) -> Path:
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = (settings.screenshot_dir / f"{stage}-{timestamp}.png").resolve()
    try:
        page.screenshot(path=str(path), full_page=True, timeout=10000)
    except Exception as exc:
        logger.warning("xhs screenshot skipped at %s: %s", stage, exc)
        try:
            page.screenshot(path=str(path), full_page=False, timeout=3000)
        except Exception:
            path.write_bytes(b"")
    logger.info("xhs screenshot %s: %s", stage, path)
    return path


def _first_visible(page: Page, selector: str) -> bool:
    if "|" in selector:
        return any(_first_visible(page, f"text={item}") for item in selector.split("|"))
    try:
        locator = page.locator(selector)
        if locator.count() == 0:
            return False
        return locator.first.is_visible(timeout=1500)
    except PlaywrightTimeoutError:
        return False


def _body_text(page: Page, timeout: int = 8000) -> str:
    try:
        return page.locator("body").inner_text(timeout=timeout)
    except Exception:
        return ""


def _wait_for_publish_app_ready(page: Page) -> None:
    """Wait for the XHS app shell to hydrate; reload once if it stays blank."""
    markers = ("上传图文", "上传视频", "草稿箱", "扫码登录", "请登录")
    for attempt in range(2):
        for _ in range(12):
            body = _body_text(page, timeout=3000)
            if any(marker in body for marker in markers):
                return
            page.wait_for_timeout(1000)
        if attempt == 0:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)


def check_login_valid(settings: Settings) -> bool:
    """Verify the saved XHS cookie still works against the live creator center.

    This is NOT a local file check. It launches a headless Chromium, navigates
    to ``settings.creator_publish_url`` (creator.xiaohongshu.com), waits for the
    DOM, and inspects the page for login markers. Expect 5-15 seconds of
    wall-clock cost plus network dependency on Xiaohongshu's edge.

    Failure modes the caller should expect:

    - Network unreachable / DNS / TLS errors against ``creator.xiaohongshu.com``
    - Playwright/Chromium not installed (``python -m playwright install chromium``)
    - XHS rev'ing the login-marker selectors out from under us (returns False
      even though the cookie is fine — re-login via ``xhs login --fresh`` will
      surface this)

    For a fast file-stat that only answers "has the user finished the first
    interactive login yet?" without paying for a Chromium startup, use
    :func:`broadcast_kit.publishers.xhs.config.is_auth_state_present` instead.
    """

    if not settings.xhs_auth_state.exists():
        return False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(settings.xhs_auth_state))
        page = context.new_page()
        page.goto(settings.creator_publish_url, wait_until="domcontentloaded", timeout=60000)
        _wait_for_publish_app_ready(page)
        valid = bool(_body_text(page, timeout=3000).strip()) and not _first_visible(page, SELECTORS["login_markers"])
        browser.close()
    return valid


def interactive_login(
    settings: Settings,
    fresh: bool = False,
    on_ready_to_save: Callable[[], None] | None = None,
) -> Path:
    """Open a visible browser, let the user scan the QR + land on publish page, save storage state.

    Args:
        settings: XHS Settings (provides auth_state path + creator_publish_url).
        fresh: If True, delete any existing auth state before launching.
        on_ready_to_save: Optional callback to signal "user has finished login,
            save storage state now." Contract: the callback MUST block until the
            orchestrator confirms the user has finished QR scanning and is landed
            on the publish page; it may return synchronously when ready. If None
            (default), falls back to the legacy CLI behavior: prints a prompt and
            blocks on `input()`. Passing a callback unblocks higher-level
            orchestrators (custom UI, scheduled-refresh daemons, multi-account
            parallel logins) that can't use stdin.

    Returns:
        Resolved Path to the saved storage_state JSON file.
    """
    settings.xhs_auth_state.parent.mkdir(parents=True, exist_ok=True)
    if fresh and settings.xhs_auth_state.exists():
        settings.xhs_auth_state.unlink()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.creator_publish_url, wait_until="domcontentloaded", timeout=60000)
        if on_ready_to_save is None:
            print("请在打开的浏览器中扫码登录小红书创作中心。看到发布页后,回到终端按 Enter。")
            input()
        else:
            on_ready_to_save()
        context.storage_state(path=str(settings.xhs_auth_state))
        browser.close()
    logger.info("xhs auth state saved: %s", settings.xhs_auth_state)
    return settings.xhs_auth_state.resolve()


def _select_upload_tab(page: Page, asset_kind: str) -> None:
    selector = SELECTORS["upload_tab_image"] if asset_kind == "image" else SELECTORS["upload_tab_video"]
    input_selector = SELECTORS["image_inputs"] if asset_kind == "image" else SELECTORS["video_inputs"]
    for chunk in selector.split(", "):
        try:
            locator = page.locator(chunk.strip())
            count = locator.count()
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                if not candidate.is_visible(timeout=500):
                    continue
                box = candidate.bounding_box(timeout=1000)
                if not box or box["x"] < 0 or box["y"] < 0:
                    continue
                candidate.click(timeout=3000, force=True)
                page.wait_for_timeout(1500)
                if page.locator(input_selector).count() > 0:
                    return
        except Exception:
            continue
    raise XhsError(f"upload tab not selected for kind={asset_kind}")


def _upload_assets(page: Page, asset_paths: list[Path], asset_kind: str) -> None:
    selector = SELECTORS["video_inputs"] if asset_kind == "video" else SELECTORS["image_inputs"]
    try:
        page.wait_for_selector(selector, state="attached", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    locator = page.locator(selector)
    count = locator.count()
    if count == 0:
        raise XhsError(f"asset file input not found for kind={asset_kind}")
    target = locator.first
    if asset_kind == "image":
        for index in range(count):
            candidate = locator.nth(index)
            try:
                accept = (candidate.get_attribute("accept", timeout=1000) or "").lower()
            except Exception:
                accept = ""
            if any(ext in accept for ext in ("image", "jpg", "jpeg", "png", "webp")):
                target = candidate
                break
    target.set_input_files([str(path) for path in asset_paths])
    page.wait_for_timeout(4000)


def _fill_title(page: Page, title: str) -> None:
    for chunk in SELECTORS["title_input"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.fill(title, timeout=3000)
            return
        except Exception:
            continue
    raise XhsError("title input not found")


def _fill_body(page: Page, body: str) -> None:
    for chunk in SELECTORS["body_editor"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.click(timeout=2500)
            page.keyboard.insert_text(body)
            return
        except Exception:
            continue
    raise XhsError("body editor not found")


def _select_topics(page: Page, topics: list[str]) -> list[str]:
    selected: list[str] = []
    if not topics:
        return selected
    for topic in topics:
        clicked_topic_button = False
        for chunk in SELECTORS["topic_button"].split(", "):
            try:
                locator = page.locator(chunk.strip())
                if locator.count() > 0 and locator.first.is_visible(timeout=1500):
                    locator.first.click(timeout=2500)
                    clicked_topic_button = True
                    break
            except Exception:
                continue
        if not clicked_topic_button:
            logger.warning("xhs topic button not found, skipping topic %s", topic)
            continue
        try:
            page.locator(SELECTORS["topic_input"]).first.fill(topic, timeout=2500)
            page.wait_for_timeout(1500)
        except Exception:
            continue
        try:
            page.locator(SELECTORS["topic_candidates"]).first.click(timeout=3000)
            selected.append(topic)
            page.wait_for_timeout(800)
        except Exception:
            logger.warning("xhs topic candidate not clickable: %s", topic)
    return selected


def _click_publish(page: Page) -> None:
    for chunk in SELECTORS["publish_button"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            count = locator.count()
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                if not candidate.is_visible(timeout=500):
                    continue
                candidate.scroll_into_view_if_needed(timeout=2000)
                candidate.click(timeout=10000, force=True)
                return
        except Exception:
            continue
    raise XhsError("xhs publish button not found")


def _detect_success(page: Page) -> tuple[bool, str | None]:
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""
    success_marker_hit = any(marker in body for marker in SELECTORS["success_markers"].split("|"))
    url = page.url if "published=true" in page.url else None
    return (success_marker_hit or url is not None), url


def upload_note(
    settings: Settings,
    asset_paths: list[Path],
    title: str,
    body: str,
    topics: list[str],
    asset_kind: str = "image",
    submit_publish: bool = False,
) -> XhsUploadResult:
    settings.ensure_runtime_dirs()
    for asset in asset_paths:
        if not asset.exists():
            raise XhsError(f"asset not found: {asset}")
    submit_requested = bool(submit_publish)
    submit = submit_publish and not settings.xhs_skip_submit and os.getenv("XHS_SKIP_SUBMIT", "0") != "1"
    submit_effective = bool(submit)
    timestamp = _timestamp()
    screenshots: list[Path] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context_kwargs = {}
        if settings.xhs_auth_state.exists():
            context_kwargs["storage_state"] = str(settings.xhs_auth_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(settings.creator_publish_url, wait_until="domcontentloaded", timeout=60000)
        _wait_for_publish_app_ready(page)
        if _first_visible(page, SELECTORS["login_markers"]):
            raise XhsLoginExpiredError("登录态失效,请运行 xhs login --fresh")

        _select_upload_tab(page, asset_kind)
        screenshots.append(_screenshot(page, settings, "tab-selected", timestamp))

        _upload_assets(page, asset_paths, asset_kind)
        screenshots.append(_screenshot(page, settings, "upload-after", timestamp))

        _fill_title(page, title)
        _fill_body(page, body)
        page.wait_for_timeout(1000)
        screenshots.append(_screenshot(page, settings, "meta-after", timestamp))

        selected_topics = _select_topics(page, topics)
        page.wait_for_timeout(1000)
        screenshots.append(_screenshot(page, settings, "topics-after", timestamp))

        if not submit:
            detail = "dry-run: 未点击最终发布。topics={}".format(selected_topics)
            if settings.xhs_keep_open:
                print("XHS_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
                input()
            browser.close()
            print("JUDGEMENT: not_submitted")
            print(f"DETAIL: {detail}")
            return XhsUploadResult(
                "not_submitted",
                detail,
                screenshots,
                False,
                None,
                selected_topics=selected_topics,
                submit_requested=submit_requested,
                submit_effective=submit_effective,
            )

        _click_publish(page)
        page.wait_for_timeout(6000)
        screenshots.append(_screenshot(page, settings, "publish-after", timestamp))
        success, note_url = _detect_success(page)

        if settings.xhs_keep_open:
            print("XHS_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
            input()
        browser.close()
        if success:
            detail = f"published=true reached. selected_topics={selected_topics}"
            print("JUDGEMENT: success")
            print(f"DETAIL: {detail}")
            return XhsUploadResult(
                "success",
                detail,
                screenshots,
                True,
                note_url,
                selected_topics=selected_topics,
                submit_requested=submit_requested,
                submit_effective=submit_effective,
            )
        detail = "publish click made but no success marker observed"
        print("JUDGEMENT: failed")
        print(f"DETAIL: {detail}")
        return XhsUploadResult(
            "failed",
            detail,
            screenshots,
            True,
            None,
            selected_topics=selected_topics,
            submit_requested=submit_requested,
            submit_effective=submit_effective,
        )
