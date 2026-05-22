from __future__ import annotations

import unittest

from broadcast_kit.public_guard import PublicContentError, assert_manifest_public_ready
from broadcast_kit.publishers.xhs.manifest_schema import ManifestError, parse_manifest as parse_xhs


class PublicGuardTest(unittest.TestCase):
    def test_xhs_manifest_blocks_internal_test_wording(self) -> None:
        with self.assertRaises(ManifestError):
            parse_xhs(
                {
                    "id": "xhs-1",
                    "title": "正式标题",
                    "body": "这组图测试一个短图文版本。",
                    "asset_kind": "image",
                    "asset_paths": ["card.png"],
                }
            )

    def test_xhs_manifest_allows_formal_copy(self) -> None:
        item = parse_xhs(
            {
                "id": "xhs-2",
                "title": "正式标题",
                "body": "一个局部限制，会改变整个状态空间的规模。",
                "asset_kind": "image",
                "asset_paths": ["card.png"],
            }
        )
        self.assertEqual(item.title, "正式标题")

    def test_generic_guard_reports_field(self) -> None:
        with self.assertRaises(PublicContentError) as ctx:
            assert_manifest_public_ready(
                {
                    "title": "正式标题",
                    "body": "Internal Broadcast Test",
                },
                "xhs",
            )
        self.assertEqual(ctx.exception.issues[0].field, "body")


if __name__ == "__main__":
    unittest.main()
