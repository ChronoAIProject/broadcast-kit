from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from .config import Settings


logger = logging.getLogger(__name__)


QUEUE_URL = "https://creator.douyin.com/creator-micro/content/manage"

QUEUE_SELECTORS = {
    "scheduled_tab": "text=定时, text=待发布, text=已定时",
    "list_rows": "[class*='row'], [class*='list-item'], [class*='card'], tr",
    "title_cell": "[class*='title']",
    "time_cell": "[class*='time'], [class*='schedule']",
    "login_markers": "登录|扫码登录|请登录",
}


class QueueVerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueueVerifyResult:
    status: Literal["true", "false", "partial"]
    title: str
    schedule_at: str | None
    queue_url: str
    txt_path: Path
    png_path: Path
    archived_txt: Path | None
    archived_png: Path | None
    detail: str


def _any_text_visible(page: Page, markers: str) -> bool:
    for marker in markers.split("|"):
        try:
            locator = page.locator(f"text={marker}")
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


def _click_first_text(page: Page, css: str) -> bool:
    for selector in [item.strip() for item in css.split(",")]:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click(timeout=2500)
                page.wait_for_timeout(1500)
                return True
        except PlaywrightTimeoutError:
            continue
    return False


def _body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=8000)
    except Exception:
        return ""


def verify_in_queue(
    page: Page,
    settings: Settings,
    title: str,
    schedule_at: str | None,
    slug: str | None = None,
) -> QueueVerifyResult:
    queue_dir = settings.work_root / "queue_inspection_final"
    queue_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    txt_path = (queue_dir / "found_in_queue.txt").resolve()
    png_path = (queue_dir / "found_in_queue.png").resolve()

    page.goto(QUEUE_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(4000)
    if _any_text_visible(page, QUEUE_SELECTORS["login_markers"]):
        raise QueueVerifyError("queue page redirected to login")
    _click_first_text(page, QUEUE_SELECTORS["scheduled_tab"])

    body = _body_text(page)
    page.screenshot(path=str(png_path), full_page=True)
    txt_path.write_text(body, encoding="utf-8")

    title_found = title in body
    time_found = bool(schedule_at and any(
        marker in body for marker in _time_markers(schedule_at)
    ))

    if title_found and time_found:
        status: Literal["true", "false", "partial"] = "true"
        detail = "title and scheduled time both present in queue body"
    elif title_found:
        status = "partial"
        detail = "title present but scheduled time not matched"
    else:
        status = "false"
        detail = "title not present in queue body"

    archived_txt = archived_png = None
    if slug:
        archived_txt = (queue_dir / f"{slug}_found_in_queue_{timestamp}.txt").resolve()
        archived_png = (queue_dir / f"{slug}_found_in_queue_{timestamp}.png").resolve()
        shutil.copy2(txt_path, archived_txt)
        shutil.copy2(png_path, archived_png)
        logger.info("queue evidence archived: %s", archived_txt)

    print(f"QUEUE_VERIFY: {status.capitalize() if status != 'true' else 'True'}")
    print(f"QUEUE_DETAIL: {detail}")
    return QueueVerifyResult(
        status=status,
        title=title,
        schedule_at=schedule_at,
        queue_url=page.url,
        txt_path=txt_path,
        png_path=png_path,
        archived_txt=archived_txt,
        archived_png=archived_png,
        detail=detail,
    )


def _time_markers(schedule_at: str) -> list[str]:
    raw = schedule_at.strip()
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return [raw]
    candidates = {
        parsed.strftime("%Y-%m-%d %H:%M"),
        parsed.strftime("%Y-%m-%d %H:%M:%S"),
        parsed.strftime("%m-%d %H:%M"),
        parsed.strftime("%H:%M"),
    }
    return [item for item in candidates if item]
