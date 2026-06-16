from __future__ import annotations

import unittest

from broadcast_kit.public_guard import (
    PublicContentError,
    PublicCopyGateConfig,
    PublicCopyGateError,
    assert_manifest_public_ready,
    assert_public_copy_gate,
)
from broadcast_kit.publishers.discourse.manifest_schema import (
    ManifestError as DiscourseManifestError,
    parse_manifest as parse_discourse,
)
from broadcast_kit.publishers.reddit.manifest_schema import (
    ManifestError as RedditManifestError,
    parse_manifest as parse_reddit,
)
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

    def test_reddit_manifest_ignores_test_in_thread_url(self) -> None:
        item = parse_reddit(
            {
                "id": "reddit-1",
                "platform": "reddit",
                "thread_url": "https://old.reddit.com/r/test/comments/abc123/test_thread/",
                "body": "This is a substantial peer-help reply body.",
            }
        )
        self.assertEqual(item.platform, "reddit")

    def test_reddit_manifest_still_blocks_internal_test_wording_in_body(self) -> None:
        with self.assertRaises(RedditManifestError):
            parse_reddit(
                {
                    "id": "reddit-2",
                    "platform": "reddit",
                    "thread_url": "https://old.reddit.com/r/python/comments/abc123/thread/",
                    "body": "This is a Broadcast Test reply body.",
                }
            )

    def test_discourse_manifest_ignores_test_in_topic_url(self) -> None:
        item = parse_discourse(
            {
                "id": "discourse-1",
                "platform": "discourse",
                "instance_url": "https://community.n8n.io",
                "topic_url": "https://community.n8n.io/t/test-topic/123",
                "body": "This is a substantial peer-help reply body.",
            }
        )
        self.assertEqual(item.platform, "discourse")

    def test_discourse_manifest_still_blocks_internal_test_wording_in_body(self) -> None:
        with self.assertRaises(DiscourseManifestError):
            parse_discourse(
                {
                    "id": "discourse-2",
                    "platform": "discourse",
                    "instance_url": "https://community.n8n.io",
                    "topic_url": "https://community.n8n.io/t/real-topic/123",
                    "body": "This is a test reply body that should be blocked.",
                }
            )

    def test_public_copy_gate_blocks_thin_caption_and_weak_topics(self) -> None:
        config = PublicCopyGateConfig(
            min_compact_chars=90,
            required_any=("论文", "数学", "证据"),
            explanatory_markers=("为什么", "不是", "而是", "真正", "问题", "结构", "证据"),
            min_explanatory_markers=2,
            allowed_topics=("数学", "科普", "学术", "逻辑"),
            forbidden_topic_terms=("Omega", "宇宙回声"),
        )
        with self.assertRaises(PublicCopyGateError) as ctx:
            assert_public_copy_gate(
                title="Cayley Chebyshev Poisson Ent",
                caption="这条把论文里最硬的结构问题讲成一个可以顺着听完的版本。",
                topics=["Omega", "宇宙回声", "学术"],
                config=config,
            )
        codes = {issue.code for issue in ctx.exception.issues}
        self.assertIn("caption_too_thin", codes)
        self.assertIn("topic_not_allowed", codes)

    def test_public_copy_gate_allows_substantive_chinese_caption(self) -> None:
        config = PublicCopyGateConfig(
            min_compact_chars=90,
            required_any=("论文", "数学", "证据"),
            explanatory_markers=("为什么", "不是", "而是", "真正", "问题", "结构", "证据"),
            min_explanatory_markers=2,
            allowed_topics=("数学", "科普", "学术", "逻辑"),
            forbidden_topic_terms=("Omega", "宇宙回声"),
            forbid_latin_ratio_above=0.5,
        )
        assert_public_copy_gate(
            title="边界信息为什么会变清楚？",
            caption=(
                "宇宙回声用 Omega 视角读一篇数学论文：问题不是某个公式有多漂亮，"
                "而是为什么换一种观察坐标后，原本藏在边界里的信息会变成可以检查的结构证据。"
                "真正要看的，是这个转换如何改变我们能证明什么。"
            ),
            topics=["数学", "科普", "学术", "逻辑"],
            config=config,
        )


if __name__ == "__main__":
    unittest.main()
