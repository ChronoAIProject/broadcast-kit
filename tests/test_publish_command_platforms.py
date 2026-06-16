from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from broadcast_kit.commands.publish import run


class PublishCommandPlatformTest(unittest.TestCase):
    def _temp_manifest(self, data: dict[str, object]) -> Path:
        temp_dir = Path(tempfile.mkdtemp())
        path = temp_dir / "manifest.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_top_level_publish_accepts_reddit_manifest(self) -> None:
        manifest = self._temp_manifest(
            {
                "id": "reddit-1",
                "platform": "reddit",
                "thread_url": "https://old.reddit.com/r/test/comments/abc123/test_thread/",
                "body": "This is a substantial peer-help reply body.",
            }
        )
        with patch(
            "broadcast_kit.commands.publish.publishers.publish",
            return_value={"platform": "reddit", "status": "dry_run"},
        ) as mock_publish:
            result = run("reddit", manifest, True, "default")
        mock_publish.assert_called_once()
        self.assertEqual(result["platform"], "reddit")
        self.assertEqual(result["status"], "dry_run")

    def test_top_level_publish_accepts_discourse_manifest(self) -> None:
        manifest = self._temp_manifest(
            {
                "id": "discourse-1",
                "platform": "discourse",
                "instance_url": "https://community.n8n.io",
                "topic_url": "https://community.n8n.io/t/test-topic/123",
                "body": "This is a substantial peer-help reply body.",
            }
        )
        with patch(
            "broadcast_kit.commands.publish.publishers.publish",
            return_value={"platform": "discourse", "status": "dry_run"},
        ) as mock_publish:
            result = run("discourse", manifest, True, "default")
        mock_publish.assert_called_once()
        self.assertEqual(result["platform"], "discourse")
        self.assertEqual(result["status"], "dry_run")


if __name__ == "__main__":
    unittest.main()
