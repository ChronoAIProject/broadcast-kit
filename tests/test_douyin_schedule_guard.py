from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from broadcast_kit.publishers.douyin.publish import (
    DOUYIN_SCHEDULE_MAX_LEAD,
    DouyinError,
    _ensure_schedule_window,
    _pre_submit_upload_failed,
    _schedule_markers,
)


class FakePage:
    def __init__(self, evidence: dict[str, bool]):
        self.evidence = evidence

    def evaluate(self, _script: str) -> dict[str, bool]:
        return self.evidence


class DouyinScheduleGuardTest(unittest.TestCase):
    def test_rejects_schedule_outside_14_day_window(self) -> None:
        now = datetime(2026, 5, 21, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        with self.assertRaises(DouyinError):
            _ensure_schedule_window(now + DOUYIN_SCHEDULE_MAX_LEAD + timedelta(minutes=1), now=now)

    def test_accepts_schedule_inside_14_day_window(self) -> None:
        now = datetime(2026, 5, 21, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        _ensure_schedule_window(now + DOUYIN_SCHEDULE_MAX_LEAD, now=now)

    def test_rejects_schedule_too_soon(self) -> None:
        now = datetime(2026, 5, 21, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        with self.assertRaises(DouyinError):
            _ensure_schedule_window(now + timedelta(minutes=30), now=now)

    def test_schedule_markers_include_douyin_visible_format(self) -> None:
        scheduled = datetime(2026, 6, 4, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        markers = _schedule_markers(scheduled)
        self.assertIn("2026年06月04日 20:00", markers)
        self.assertIn("2026年6月4日 20:00", markers)

    def test_upload_progress_text_overrides_failure_marker(self) -> None:
        body = "上传失败 上传过程中 当前速度 剩余时间"
        page = FakePage({"running": True, "failed": True})
        self.assertFalse(_pre_submit_upload_failed(page, body))  # type: ignore[arg-type]

    def test_upload_failure_marker_without_progress_fails(self) -> None:
        body = "上传失败 请重新上传"
        page = FakePage({"running": False, "failed": True})
        self.assertTrue(_pre_submit_upload_failed(page, body))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
