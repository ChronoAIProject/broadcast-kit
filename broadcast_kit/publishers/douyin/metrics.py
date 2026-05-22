from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .config import Settings


logger = logging.getLogger(__name__)


METRICS_SELECTORS = {
    "video_cards": "[data-e2e*='video'], .video-card, .content-card, tr",
    "title": "[class*='title'], [data-e2e*='title']",
    "publish_time": "text=/\\d{4}-\\d{2}-\\d{2}|\\d+天前|昨天|今天/",
    "play_count": "text=/播放|浏览/",
    "likes": "text=/点赞/",
    "comments": "text=/评论/",
    "shares": "text=/分享/",
    "favorites": "text=/收藏/",
    "completion_rate": "text=/完播率/",
    "profile_visits": "text=/主页访问/",
    "follower_growth": "text=/粉丝增长/",
    "follow_conversion": "text=/关注转化/",
    "comment_items": "[class*='comment'], [data-e2e*='comment']",
    "login_markers": "登录|扫码登录|请登录",
}

DATA_CENTER_URL = "https://creator.douyin.com/creator-micro/data-center"
CONTENT_MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"

METRIC_LABELS = {
    "play_count": "播放",
    "avg_play_duration": "平均播放时长",
    "cover_click_rate": "封面点击率",
    "likes": "点赞",
    "comments_count": "评论",
    "shares": "分享",
    "favorites": "收藏",
    "danmaku": "弹幕",
}


class MetricsError(RuntimeError):
    pass


def _text_or_none(page: Page, selector: str) -> str | None:
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return None
        return locator.inner_text(timeout=1200).strip()
    except Exception:
        return None


def _any_text_visible(page: Page, markers: str) -> bool:
    for marker in markers.split("|"):
        try:
            locator = page.locator(f"text={marker}")
            if locator.count() > 0 and locator.first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


def _collect_comments(page: Page) -> list[str]:
    comments: list[str] = []
    try:
        locator = page.locator(METRICS_SELECTORS["comment_items"])
        for index in range(min(locator.count(), 30)):
            text = locator.nth(index).inner_text(timeout=500).strip()
            if text:
                comments.append(text)
    except Exception:
        pass
    return comments[:30]


def _partial_snapshot(page: Page, account: str, days: int) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "account": account,
        "snapshot_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "days": days,
        "video_id": None,
        "title": _text_or_none(page, METRICS_SELECTORS["title"]),
        "publish_time": _text_or_none(page, METRICS_SELECTORS["publish_time"]),
        "play_count": _text_or_none(page, METRICS_SELECTORS["play_count"]),
        "likes": _text_or_none(page, METRICS_SELECTORS["likes"]),
        "comments_count": _text_or_none(page, METRICS_SELECTORS["comments"]),
        "shares": _text_or_none(page, METRICS_SELECTORS["shares"]),
        "favorites": _text_or_none(page, METRICS_SELECTORS["favorites"]),
        "completion_rate": _text_or_none(page, METRICS_SELECTORS["completion_rate"]),
        "profile_visits": _text_or_none(page, METRICS_SELECTORS["profile_visits"]),
        "follower_growth": _text_or_none(page, METRICS_SELECTORS["follower_growth"]),
        "follow_conversion": _text_or_none(page, METRICS_SELECTORS["follow_conversion"]),
        "top_comments": _collect_comments(page),
        "partial": False,
    }
    required = ("play_count", "likes", "comments_count", "completion_rate")
    if any(snapshot.get(key) is None for key in required):
        snapshot["partial"] = True
    return snapshot


def _body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""


def _is_duration_line(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", value.strip()))


def _parse_number(value: str | None) -> int | float | None:
    if not value or value == "-":
        return None
    raw = value.strip().replace(",", "")
    try:
        if raw.endswith("万"):
            return float(raw[:-1]) * 10000
        if raw.endswith("%"):
            return float(raw[:-1])
        if raw.endswith("秒"):
            return int(float(raw[:-1]))
        if raw.endswith("分钟"):
            return int(float(raw[:-2]) * 60)
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return None


def _split_title_caption(line: str, title_suffix: str | None) -> tuple[str, str | None]:
    """Optionally split a combined title+caption line.

    If DOUYIN_METRICS_TITLE_SUFFIX is set (e.g. "Series Name"), the parser
    looks for "<suffix>" or "：<suffix>" / ": <suffix>" inside the line; the
    title is everything up to and including the suffix, the caption is what
    follows. If no suffix is configured, the entire line is the title and
    caption is None.
    """
    if not title_suffix:
        return line.strip(), None
    markers = (f"：{title_suffix}", f": {title_suffix}", title_suffix)
    for marker in markers:
        if marker in line:
            end = line.index(marker) + len(marker)
            title = line[:end].strip()
            caption = line[end:].strip() or None
            return title, caption
    return line.strip(), None


def _metric_after(block: list[str], label: str) -> str | None:
    for index, item in enumerate(block):
        if item == label and index + 1 < len(block):
            return block[index + 1]
    return None


def _parse_work_block(block: list[str], account: str, days: int, title_suffix: str | None) -> dict[str, Any] | None:
    if len(block) < 2:
        return None
    duration = block[0] if _is_duration_line(block[0]) else None
    title, caption = _split_title_caption(block[1], title_suffix)
    publish_time = None
    status = None
    for item in block:
        match = re.search(r"(?:定时:\s*)?(\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2})", item)
        if match:
            publish_time = match.group(1)
        if item in {"已发布", "定时发布中", "审核中", "未通过"}:
            status = item

    snapshot: dict[str, Any] = {
        "account": account,
        "snapshot_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "days": days,
        "source": "content_manage",
        "video_id": None,
        "title": title,
        "caption": caption,
        "duration": duration,
        "publish_time": publish_time,
        "status": status,
        "partial": False,
    }
    for key, label in METRIC_LABELS.items():
        raw = _metric_after(block, label)
        snapshot[key] = raw
        snapshot[f"{key}_value"] = _parse_number(raw)
    if snapshot.get("play_count") is None:
        snapshot["partial"] = True
    return snapshot


def _parse_content_manage_text(text: str, account: str, days: int, title_suffix: str | None) -> list[dict[str, Any]]:
    """Split the content manage page text into per-work blocks.

    A work block starts at a duration line (e.g. "1:23"). If a title_suffix
    is configured, only duration lines followed by a line containing that
    suffix are treated as block starts (filters out non-work UI noise). If
    no suffix is configured, every duration line is treated as a block
    start.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    starts: list[int] = []
    for index, line in enumerate(lines[:-1]):
        if not _is_duration_line(line):
            continue
        next_line = lines[index + 1]
        if title_suffix and title_suffix not in next_line:
            continue
        starts.append(index)
    snapshots: list[dict[str, Any]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        parsed = _parse_work_block(lines[start:end], account, days, title_suffix)
        if parsed:
            snapshots.append(parsed)
    return snapshots


def fetch_metrics(settings: Settings, days: int, account: str = "default") -> Path:
    if not settings.douyin_auth_state.exists():
        raise MetricsError("auth state missing; run douyin login --fresh first")
    out_dir = settings.metrics_dir / account
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (out_dir / f"{date.today().isoformat()}.jsonl").resolve()
    snapshots: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(settings.douyin_auth_state))
        page = context.new_page()
        page.goto(CONTENT_MANAGE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if _any_text_visible(page, METRICS_SELECTORS["login_markers"]):
            raise MetricsError("login state expired")
        body = _body_text(page)
        snapshots = _parse_content_manage_text(body, account, days, settings.metrics_title_suffix)
        if not snapshots:
            page.goto(DATA_CENTER_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            snapshots.append(_partial_snapshot(page, account, days))
        browser.close()

    with out_path.open("a", encoding="utf-8") as fh:
        for snapshot in snapshots:
            fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    logger.info("metrics written: %s", out_path)
    return out_path
