from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .config import Settings


logger = logging.getLogger(__name__)


PUBLISH_URL_FALLBACK = "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page"
SCREENSHOT_STAGES = ("upload-after", "upload-meta", "cover-after", "publish-before", "publish-after")

SELECTORS = {
    "video_inputs": "input[type='file']",
    "title_inputs": "input[placeholder*='标题'], textarea[placeholder*='标题'], [contenteditable='true']:has-text('填写作品标题'), input",
    "description_inputs": "textarea[placeholder*='简介'], textarea[placeholder*='描述'], [contenteditable='true']:has-text('添加作品简介'), [contenteditable='true'], textarea",
    "cover_buttons": "text=选择封面, text=设置封面, text=编辑封面",
    "image_inputs": "input[type='file'][accept*='image'], input[type='file'][accept*='png'], input[type='file'][accept*='jpg']",
    "publish_buttons": "button:has-text('发布'), button:has-text('立即发布')",
    "login_markers": "登录|扫码登录|请登录",
    "success_markers": "审核中|正在发布|发布成功",
    "scheduled_toggle": "label:has-text('定时发布'), text=定时发布, [role='radio']:has-text('定时'), text=定时",
    "schedule_date_input": "input[placeholder*='日期'], input[placeholder*='发布时间'], input[placeholder*='选择日期'], input[type='date'], input",
    "schedule_time_input": "input[placeholder*='时间'], input[placeholder*='选择时间'], input[type='time']",
    "schedule_confirm_button": "button:has-text('确定'), button:has-text('确认')",
    "cover_done_buttons": "button:has-text('保存'), button:has-text('我知道了'), button:has-text('暂不设置'), button:has-text('完成'), button:has-text('确定')",
}


class DouyinError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadResult:
    verdict: str
    detail: str
    screenshots: list[Path]
    submitted: bool
    cover_verified: bool
    queue_verified: str = "not_checked"
    queue_evidence_txt: Path | None = None
    queue_evidence_png: Path | None = None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _screenshot(page: Page, settings: Settings, stage: str, timestamp: str) -> Path:
    if stage not in SCREENSHOT_STAGES:
        raise DouyinError(f"invalid screenshot stage: {stage}")
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = (settings.screenshot_dir / f"{stage}-{timestamp}.png").resolve()
    try:
        page.screenshot(path=str(path), full_page=True, timeout=10000)
    except Exception as exc:
        logger.warning("full-page screenshot skipped at %s: %s", stage, exc)
        try:
            page.screenshot(path=str(path), full_page=False, timeout=3000)
        except Exception as fallback_exc:
            logger.warning("viewport screenshot skipped at %s: %s", stage, fallback_exc)
            path.write_bytes(b"")
    logger.info("screenshot %s: %s", stage, path)
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


def check_login_valid(settings: Settings) -> bool:
    """Verify the saved Douyin cookie still works against the live creator center.

    This is NOT a local file check. It launches a headless Chromium, navigates
    to ``settings.douyin_publish_url`` (creator.douyin.com), waits for the DOM,
    and inspects the page for login markers. Expect 5-15 seconds of wall-clock
    cost plus network dependency on Douyin's edge.

    Failure modes the caller should expect:

    - Network unreachable / DNS / TLS errors against ``creator.douyin.com``
    - Playwright/Chromium not installed (``python -m playwright install chromium``)
    - Douyin rev'ing the login-marker selectors out from under us (returns False
      even though the cookie is fine — re-login via ``douyin login --fresh``
      will surface this)

    For a fast file-stat that only answers "has the user finished the first
    interactive login yet?" without paying for a Chromium startup, use
    :func:`broadcast_kit.publishers.douyin.config.is_auth_state_present`
    instead.
    """

    if not settings.douyin_auth_state.exists():
        return False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(settings.douyin_auth_state))
        page = context.new_page()
        page.goto(settings.douyin_publish_url or PUBLISH_URL_FALLBACK, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        valid = not _first_visible(page, SELECTORS["login_markers"])
        browser.close()
    return valid


def interactive_login(
    settings: Settings,
    fresh: bool = False,
    on_ready_to_save: Callable[[], None] | None = None,
) -> Path:
    """Open a visible browser, let the user complete Douyin login, save storage state.

    Args:
        settings: Douyin Settings (provides auth_state path + publish url).
        fresh: If True, delete any existing auth state before launching.
        on_ready_to_save: Optional callback to signal "user has finished login,
            save storage state now." Contract: the callback MUST block until
            the orchestrator confirms the user has finished login and is landed
            on the publish page; it may return synchronously when ready. If
            None (default), falls back to the legacy CLI behavior: prints a
            prompt and blocks on `input()`. Passing a callback unblocks
            higher-level orchestrators (custom UI, scheduled-refresh daemons,
            multi-account parallel logins) that can't use stdin.

    Returns:
        Resolved Path to the saved storage_state JSON file.
    """
    settings.douyin_auth_state.parent.mkdir(parents=True, exist_ok=True)
    if fresh and settings.douyin_auth_state.exists():
        settings.douyin_auth_state.unlink()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.douyin_publish_url or PUBLISH_URL_FALLBACK, wait_until="domcontentloaded", timeout=60000)
        if on_ready_to_save is None:
            print("请在打开的浏览器中完成抖音登录。登录完成并看到发布页后,回到终端按 Enter。")
            input()
        else:
            on_ready_to_save()
        context.storage_state(path=str(settings.douyin_auth_state))
        browser.close()
    logger.info("auth state saved: %s", settings.douyin_auth_state)
    return settings.douyin_auth_state.resolve()


def _set_first_file_input(page: Page, file_path: Path, accept_image: bool = False) -> None:
    selector = SELECTORS["image_inputs"] if accept_image else SELECTORS["video_inputs"]
    locator = page.locator(selector)
    count = locator.count()
    if count == 0 and not accept_image:
        try:
            page.get_by_role("button", name="上传视频").click(timeout=3000)
            page.wait_for_timeout(1500)
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            pass
    if count == 0:
        raise DouyinError(f"file input not found for {file_path}")
    locator.nth(count - 1).set_input_files(str(file_path))


def _dismiss_unsubmitted_draft_prompt(page: Page) -> None:
    try:
        if page.locator("text=你还有上次未发布的视频").count() == 0:
            return
        abandon = page.get_by_role("button", name="放弃")
        if abandon.count() == 0:
            abandon = page.locator("text=放弃")
        abandon.first.click(timeout=3000)
        page.wait_for_timeout(2500)
    except Exception:
        return


def _fill_first(page: Page, selector: str, value: str) -> None:
    locator = page.locator(selector)
    count = locator.count()
    if count == 0:
        raise DouyinError(f"input not found for selector: {selector}")
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible(timeout=500):
                candidate.fill(value)
                return
        except PlaywrightTimeoutError:
            continue
    locator.first.fill(value)


def _fill_publish_text_fields(page: Page, title: str, description: str) -> None:
    try:
        page.get_by_placeholder("填写作品标题,为作品获得更多流量").fill(title, timeout=3000)
    except Exception:
        _fill_first(page, SELECTORS["title_inputs"], title)

    try:
        page.get_by_placeholder("添加作品简介").fill(description, timeout=3000)
    except Exception:
        try:
            page.locator("text=添加作品简介").first.click(timeout=2500)
            page.keyboard.insert_text(description)
        except Exception:
            _fill_first(page, SELECTORS["description_inputs"], description)


def _upload_cover_axis(page: Page, cover_path: Path, axis_name: str) -> bool:
    before_count = page.locator(SELECTORS["image_inputs"]).count()
    try:
        for text_selector in SELECTORS["cover_buttons"].split(", "):
            locator = page.locator(text_selector)
            if locator.count() > 0:
                locator.first.click(timeout=3000)
                page.wait_for_timeout(1000)
                break
    except PlaywrightTimeoutError:
        pass
    try:
        after_locator = page.locator(SELECTORS["image_inputs"])
        after_count = after_locator.count()
        target_index = max(after_count - 1, 0)
        if after_count == 0:
            return False
        after_locator.nth(target_index).set_input_files(str(cover_path))
        page.wait_for_timeout(1800)
        logger.info("cover axis uploaded: %s count_before=%s", axis_name, before_count)
        return True
    except Exception as exc:
        logger.error("cover axis upload failed: %s %s", axis_name, exc)
        return False


def _close_cover_dialog_if_open(page: Page) -> None:
    for _ in range(4):
        clicked = False
        for chunk in SELECTORS["cover_done_buttons"].split(", "):
            try:
                locator = page.locator(chunk.strip())
                count = locator.count()
                if count == 0:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    if not candidate.is_visible(timeout=500):
                        continue
                    if candidate.evaluate("el => el.disabled || el.getAttribute('aria-disabled') === 'true'"):
                        continue
                    candidate.click(timeout=3000)
                    page.wait_for_timeout(1600)
                    clicked = True
                    break
                if clicked:
                    break
            except Exception:
                continue
        if not clicked:
            return


def _page_contains_success(page: Page) -> bool:
    body = page.locator("body").inner_text(timeout=5000)
    return "审核中" in body or "正在发布" in body or "发布成功" in body


def _click_submit_publish_button(page: Page) -> None:
    candidates = page.get_by_role("button", name="发布")
    count = candidates.count()
    if count == 0:
        candidates = page.locator(SELECTORS["publish_buttons"])
        count = candidates.count()
    for index in range(count - 1, -1, -1):
        candidate = candidates.nth(index)
        try:
            if not candidate.is_visible(timeout=500):
                continue
            box = candidate.bounding_box(timeout=1000)
            if box and box["x"] < 200:
                continue
            candidate.scroll_into_view_if_needed(timeout=2000)
            candidate.click(timeout=10000)
            return
        except Exception:
            continue
    raise DouyinError("publish submit button not found")


def _try_set_scheduled_publish(page: Page, scheduled_at: datetime) -> bool:
    selectors = SELECTORS
    clicked = False
    try:
        radio = page.get_by_text("定时发布", exact=True)
        if radio.count() > 0:
            radio.first.scroll_into_view_if_needed(timeout=2000)
            radio.first.click(timeout=3000)
            clicked = True
    except Exception:
        clicked = False
    for chunk in selectors["scheduled_toggle"].split(", "):
        if clicked:
            break
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.scroll_into_view_if_needed(timeout=2000)
            locator.first.click(timeout=3000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        logger.error("scheduled toggle not found")
        return False
    page.wait_for_timeout(1200)
    date_str = scheduled_at.strftime("%Y-%m-%d")
    time_str = scheduled_at.strftime("%H:%M")
    combined = f"{date_str} {time_str}"
    filled = False
    for chunk in selectors["schedule_date_input"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.fill(combined, timeout=2500)
            filled = True
            break
        except Exception:
            continue
    if not filled:
        for chunk in selectors["schedule_date_input"].split(", "):
            try:
                locator = page.locator(chunk.strip())
                if locator.count() == 0:
                    continue
                locator.first.fill(date_str, timeout=2500)
                filled = True
                break
            except Exception:
                continue
    for chunk in selectors["schedule_time_input"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.fill(time_str, timeout=2500)
            break
        except Exception:
            continue
    for chunk in selectors["schedule_confirm_button"].split(", "):
        try:
            locator = page.locator(chunk.strip())
            if locator.count() == 0:
                continue
            locator.first.click(timeout=2000)
            break
        except Exception:
            continue
    page.wait_for_timeout(1500)
    return filled


def upload_video(
    settings: Settings,
    video_path: str | Path,
    title: str,
    description: str,
    cover_horizontal: str | Path | None = None,
    cover_vertical: str | Path | None = None,
    submit_publish: bool = False,
    scheduled_publish_at: datetime | None = None,
    queue_verify_title: str | None = None,
    queue_verify_slug: str | None = None,
) -> UploadResult:
    settings.ensure_runtime_dirs()
    video = Path(video_path).expanduser().resolve()
    if not video.exists():
        raise DouyinError(f"video not found: {video}")
    horizontal = Path(cover_horizontal).expanduser().resolve() if cover_horizontal else None
    vertical = Path(cover_vertical).expanduser().resolve() if cover_vertical else None
    for cover in (horizontal, vertical):
        if cover and not cover.exists():
            raise DouyinError(f"cover not found: {cover}")
    submit = submit_publish and not settings.douyin_skip_submit and os.getenv("DOUYIN_SKIP_SUBMIT", "0") != "1"
    timestamp = _timestamp()
    screenshots: list[Path] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context_kwargs = {}
        if settings.douyin_auth_state.exists():
            context_kwargs["storage_state"] = str(settings.douyin_auth_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(settings.douyin_publish_url or PUBLISH_URL_FALLBACK, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        if _first_visible(page, SELECTORS["login_markers"]):
            raise DouyinError("登录态失效,请先运行 douyin login --fresh")
        _dismiss_unsubmitted_draft_prompt(page)

        _set_first_file_input(page, video, accept_image=False)
        page.wait_for_timeout(5000)
        screenshots.append(_screenshot(page, settings, "upload-after", timestamp))

        _fill_publish_text_fields(page, title, description)
        page.wait_for_timeout(1000)
        screenshots.append(_screenshot(page, settings, "upload-meta", timestamp))

        horizontal_ok = _upload_cover_axis(page, horizontal, "横封") if horizontal else True
        vertical_ok = _upload_cover_axis(page, vertical, "竖封") if vertical else True
        _close_cover_dialog_if_open(page)
        cover_verified = bool(horizontal_ok and vertical_ok)
        print(f"COVER_VERIFY: {cover_verified} | 双轴 DOM 已兜底检查")
        screenshots.append(_screenshot(page, settings, "cover-after", timestamp))
        if not cover_verified:
            raise DouyinError("COVER_VERIFY failed: horizontal or vertical cover upload was not accepted")

        if scheduled_publish_at is not None:
            ok = _try_set_scheduled_publish(page, scheduled_publish_at)
            if not ok:
                if settings.douyin_keep_open:
                    print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
                    input()
                browser.close()
                raise DouyinError("scheduled publish toggle/time fill failed")

        screenshots.append(_screenshot(page, settings, "publish-before", timestamp))
        if not submit:
            detail = "未执行最终发布点击;dry-run 完成"
            if settings.douyin_keep_open:
                print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
                input()
            browser.close()
            print("JUDGEMENT: not_submitted")
            print(f"DETAIL: {detail}")
            return UploadResult("not_submitted", detail, screenshots, False, cover_verified)

        _click_submit_publish_button(page)
        page.wait_for_timeout(6000)
        screenshots.append(_screenshot(page, settings, "publish-after", timestamp))
        success = _page_contains_success(page)

        queue_status = "not_checked"
        queue_txt: Path | None = None
        queue_png: Path | None = None
        if success and queue_verify_title:
            try:
                from .queue_verify import verify_in_queue

                schedule_iso = scheduled_publish_at.isoformat() if scheduled_publish_at else None
                qv = verify_in_queue(page, settings, queue_verify_title, schedule_iso, slug=queue_verify_slug)
                queue_status = qv.status
                queue_txt = qv.archived_txt or qv.txt_path
                queue_png = qv.archived_png or qv.png_path
            except Exception as exc:
                logger.error("queue verify raised: %s", exc)
                queue_status = "false"

        if settings.douyin_keep_open:
            print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
            input()
        browser.close()
        if success:
            detail = "页面正文含成功/审核类提示: '审核中'"
            print("JUDGEMENT: success")
            print(f"DETAIL: {detail}")
            return UploadResult(
                "success",
                detail,
                screenshots,
                True,
                cover_verified,
                queue_verified=queue_status,
                queue_evidence_txt=queue_txt,
                queue_evidence_png=queue_png,
            )
        detail = "发布后页面未出现 审核中/正在发布/发布成功"
        print("JUDGEMENT: failed")
        print(f"DETAIL: {detail}")
        return UploadResult("failed", detail, screenshots, True, cover_verified)
