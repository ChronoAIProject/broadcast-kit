from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from broadcast_kit.publishers.douyin.publish import (
    DOUYIN_SCHEDULE_MAX_LEAD,
    DouyinError,
    _ensure_schedule_window,
    _schedule_markers,
)


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


if __name__ == "__main__":
    unittest.main()
