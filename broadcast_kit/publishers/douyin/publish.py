from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .config import Settings


logger = logging.getLogger(__name__)


PUBLISH_URL_FALLBACK = "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page"
DOUYIN_SCHEDULE_MIN_LEAD = timedelta(hours=2)
DOUYIN_SCHEDULE_MAX_LEAD = timedelta(days=14)
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
    if not accept_image:
        try:
            page.wait_for_selector(selector, state="attached", timeout=15000)
        except PlaywrightTimeoutError:
            try:
                page.get_by_role("button", name="上传视频").click(timeout=3000)
                page.wait_for_selector(selector, state="attached", timeout=10000)
            except Exception:
                pass
    locator = page.locator(selector)
    count = locator.count()
    if count == 0:
        raise DouyinError(f"file input not found for {file_path}")
    if not accept_image:
        for index in range(count):
            candidate = locator.nth(index)
            try:
                accept = (candidate.get_attribute("accept", timeout=1000) or "").lower()
            except Exception:
                accept = ""
            if "image" in accept or "png" in accept or "jpg" in accept or "jpeg" in accept:
                continue
            candidate.set_input_files(str(file_path))
            return
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


def _cover_slots_visible(page: Page) -> tuple[bool, bool]:
    """Conservative DOM-level evidence that both Douyin cover slots are present."""
    body = _body_text(page, timeout=5000)
    has_horizontal = "横封面4:3" in body or ("横封面" in body and "4:3" in body)
    has_vertical = "竖封面3:4" in body or ("竖封面" in body and "3:4" in body)
    return has_horizontal, has_vertical


def _cover_image_evidence(page: Page) -> dict[str, int | bool]:
    """Verify that the cover area contains two non-empty rendered thumbnails.

    Douyin has changed this widget several times: sometimes thumbnails are
    normal ``img`` nodes, sometimes CSS backgrounds under nested divs. The
    invariant we rely on is stricter than "file input accepted" but less brittle
    than one class name: after both uploads, the section that contains
    横封面4:3/竖封面3:4 must contain at least two visible image-like boxes.
    """
    try:
        raw = page.evaluate(
            """() => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, "");
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 12 && rect.height > 12 && style.display !== "none" && style.visibility !== "hidden";
                };
                const nodes = Array.from(document.querySelectorAll("body *"));
                const textNodes = nodes.filter((el) => {
                    if (!isVisible(el)) return false;
                    const text = normalize(el.innerText || el.textContent || "");
                    return text.length > 0 && text.length <= 80;
                });
                const horizontalLabel = textNodes.find((el) => normalize(el.innerText || el.textContent || "").includes("横封面4:3"));
                const verticalLabel = textNodes.find((el) => normalize(el.innerText || el.textContent || "").includes("竖封面3:4"));
                if (!horizontalLabel || !verticalLabel) {
                    return {horizontal: false, vertical: false, thumbnail_count: 0};
                }
                const hBox = horizontalLabel.getBoundingClientRect();
                const vBox = verticalLabel.getBoundingClientRect();
                const left = Math.min(hBox.left, vBox.left) - 30;
                const right = Math.max(hBox.right, vBox.right) + 30;
                const top = Math.min(hBox.top, vBox.top) - 180;
                const bottom = Math.max(hBox.bottom, vBox.bottom) + 20;

                const imageLike = nodes.filter((el) => {
                    if (!isVisible(el)) return false;
                    const box = el.getBoundingClientRect();
                    const centerX = (box.left + box.right) / 2;
                    const centerY = (box.top + box.bottom) / 2;
                    if (centerX < left || centerX > right || centerY < top || centerY > bottom) return false;
                    if (box.width < 40 || box.height < 40) return false;
                    const style = window.getComputedStyle(el);
                    if (style.backgroundImage && style.backgroundImage !== "none") return true;
                    const tag = el.tagName.toLowerCase();
                    if (tag === "canvas" || tag === "video") return true;
                    if (tag === "img") {
                        const img = el;
                        return Boolean((img.currentSrc || img.src) && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0);
                    }
                    const aria = normalize(el.getAttribute("aria-label") || el.getAttribute("title") || "");
                    return aria.includes("封面") && box.width >= 40 && box.height >= 40;
                });
                const unique = [];
                for (const el of imageLike) {
                    const box = el.getBoundingClientRect();
                    const key = `${Math.round(box.left)}:${Math.round(box.top)}:${Math.round(box.width)}:${Math.round(box.height)}`;
                    if (!unique.includes(key)) unique.push(key);
                }
                return {
                    horizontal: unique.length >= 1,
                    vertical: unique.length >= 2,
                    thumbnail_count: unique.length,
                };
            }"""
        )
    except Exception as exc:
        logger.warning("cover image evidence probe failed: %s", exc)
        return {"horizontal": False, "vertical": False, "thumbnail_count": 0}
    return {
        "horizontal": bool(raw.get("horizontal")) if isinstance(raw, dict) else False,
        "vertical": bool(raw.get("vertical")) if isinstance(raw, dict) else False,
        "thumbnail_count": int(raw.get("thumbnail_count") or 0) if isinstance(raw, dict) else 0,
    }


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


def _body_text(page: Page, timeout: int = 5000) -> str:
    try:
        return page.locator("body").inner_text(timeout=timeout)
    except Exception:
        return ""


def _ensure_schedule_window(scheduled_at: datetime, now: datetime | None = None) -> None:
    if scheduled_at.tzinfo is None:
        raise DouyinError("scheduled publish time must include timezone")
    current = now or datetime.now(scheduled_at.tzinfo)
    if current.tzinfo is None:
        current = current.replace(tzinfo=scheduled_at.tzinfo)
    current = current.astimezone(scheduled_at.tzinfo)
    lead = scheduled_at - current
    if lead < DOUYIN_SCHEDULE_MIN_LEAD:
        raise DouyinError(
            "scheduled publish time is too soon for Douyin "
            f"(lead={lead}, minimum={DOUYIN_SCHEDULE_MIN_LEAD})"
        )
    if lead > DOUYIN_SCHEDULE_MAX_LEAD:
        raise DouyinError(
            "scheduled publish time is outside Douyin's 14-day scheduling window "
            f"(lead={lead}, maximum={DOUYIN_SCHEDULE_MAX_LEAD})"
        )


def _schedule_markers(scheduled_at: datetime) -> list[str]:
    compact_month = f"{scheduled_at.month}月{scheduled_at.day}日 {scheduled_at:%H:%M}"
    padded_month = scheduled_at.strftime("%m月%d日 %H:%M")
    return [
        scheduled_at.strftime("%Y-%m-%d %H:%M"),
        scheduled_at.strftime("%Y-%m-%d %H:%M:%S"),
        scheduled_at.strftime("%Y年%m月%d日 %H:%M"),
        f"{scheduled_at.year}年{compact_month}",
        padded_month,
        compact_month,
    ]


def _schedule_bound_to_page(page: Page, scheduled_at: datetime) -> bool:
    body = _body_text(page, timeout=8000)
    if not any(marker in body for marker in ("定时发布", "定时发布中", "修改定时", "发布时间")):
        return False
    return any(marker in body for marker in _schedule_markers(scheduled_at))


def _upload_still_running(body: str) -> bool:
    return any(marker in body for marker in ("作品上传中", "请勿关闭页面"))


def _pre_submit_upload_still_running(body: str) -> bool:
    return any(
        marker in body
        for marker in (
            "上传过程中",
            "当前速度",
            "剩余时间",
            "取消上传",
            "已上传：",
            "已上传:",
        )
    )


def _pre_submit_upload_failed(body: str) -> bool:
    return "上传失败" in body


def _wait_for_upload_ready(page: Page, timeout_seconds: int = 1800) -> None:
    """Wait until Douyin's video upload panel no longer reports active upload."""
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    stable_count = 0
    while time.monotonic() < deadline:
        body = _body_text(page, timeout=8000)
        if _pre_submit_upload_failed(body):
            raise DouyinError("video upload failed before submit")
        active = _pre_submit_upload_still_running(body)
        status = "uploading" if active else "ready"
        if status != last_status:
            logger.info("pre-submit upload wait: %s", status)
            last_status = status
        if active:
            stable_count = 0
        else:
            stable_count += 1
            if stable_count >= 3:
                return
        page.wait_for_timeout(5000)
    raise DouyinError(f"video upload did not complete within {timeout_seconds}s before submit")


def _page_contains_success(page: Page, title: str | None = None) -> bool:
    body = _body_text(page, timeout=5000)
    if title and title in body and not _upload_still_running(body):
        return True
    return "发布成功" in body or "正在发布" in body


def _wait_after_submit(page: Page, title: str, timeout_seconds: int = 120) -> bool:
    """Keep the browser alive until Douyin finishes the post-submit upload.

    Douyin can navigate to the manage page while a toast still says the work is
    uploading. Closing Chromium at that point cancels the upload, so the queue
    check must wait for the target title to appear without an active upload
    marker. Return False when the publish page gives no parseable settlement
    signal; callers should still run backend queue verification before failing.
    """
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        body = _body_text(page, timeout=8000)
        if title in body and not _upload_still_running(body):
            return True
        if "发布成功" in body and not _upload_still_running(body):
            return True
        status = "uploading" if _upload_still_running(body) else "waiting"
        if status != last_status:
            logger.info("post-submit wait: %s", status)
            last_status = status
        page.wait_for_timeout(5000)
    logger.info("post-submit wait: no page settlement within %ss; falling back to queue verify", timeout_seconds)
    return False


def _page_contains_success_legacy(page: Page) -> bool:
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
    _ensure_schedule_window(scheduled_at)
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
    return filled and _schedule_bound_to_page(page, scheduled_at)


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

    if scheduled_publish_at is not None:
        _ensure_schedule_window(scheduled_publish_at)

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
        horizontal_slot_visible, vertical_slot_visible = _cover_slots_visible(page)
        cover_image_evidence = _cover_image_evidence(page)
        cover_verified = bool(
            horizontal_ok
            and vertical_ok
            and horizontal_slot_visible
            and vertical_slot_visible
            and cover_image_evidence["horizontal"]
            and cover_image_evidence["vertical"]
        )
        print(
            f"COVER_VERIFY: {cover_verified} | "
            f"upload_ok={{'horizontal': {horizontal_ok}, 'vertical': {vertical_ok}}} "
            f"slots_visible={{'horizontal_4_3': {horizontal_slot_visible}, 'vertical_3_4': {vertical_slot_visible}}} "
            f"images_loaded={{'horizontal': {cover_image_evidence['horizontal']}, "
            f"'vertical': {cover_image_evidence['vertical']}, "
            f"'thumbnail_count': {cover_image_evidence['thumbnail_count']}}}"
        )
        screenshots.append(_screenshot(page, settings, "cover-after", timestamp))
        if not cover_verified:
            raise DouyinError(
                "COVER_VERIFY failed: cover upload was not accepted or both 4:3/3:4 cover slots were not visible"
            )

        if scheduled_publish_at is not None:
            ok = _try_set_scheduled_publish(page, scheduled_publish_at)
            if not ok:
                if settings.douyin_keep_open:
                    print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
                    input()
                browser.close()
                raise DouyinError("scheduled publish toggle/time fill failed or target time not visible before submit")

        _wait_for_upload_ready(page)
        if scheduled_publish_at is not None and not _schedule_bound_to_page(page, scheduled_publish_at):
            if settings.douyin_keep_open:
                print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
                input()
            browser.close()
            raise DouyinError("scheduled publish time is not visibly bound before submit; refusing to click publish")
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
        page_settled = _wait_after_submit(page, title)
        screenshots.append(_screenshot(page, settings, "publish-after", timestamp))
        success = page_settled and _page_contains_success(page, title=title)

        queue_status = "not_checked"
        queue_txt: Path | None = None
        queue_png: Path | None = None
        if queue_verify_title:
            try:
                from .queue_verify import verify_in_queue

                schedule_iso = scheduled_publish_at.isoformat() if scheduled_publish_at else None
                qv = verify_in_queue(page, settings, queue_verify_title, schedule_iso, slug=queue_verify_slug)
                queue_status = qv.status
                queue_txt = qv.archived_txt or qv.txt_path
                queue_png = qv.archived_png or qv.png_path
                if queue_status == "true":
                    success = True
            except Exception as exc:
                logger.error("queue verify raised: %s", exc)
                queue_status = "false"

        if settings.douyin_keep_open:
            print("DOUYIN_KEEP_OPEN=1,浏览器保持打开;按 Enter 关闭。")
            input()
        browser.close()
        if success:
            detail = (
                "后台队列核验成功"
                if queue_status == "true" and not page_settled
                else "页面正文含成功/审核类提示: '审核中'"
            )
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
