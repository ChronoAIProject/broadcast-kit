from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_INTERNAL_TERMS: tuple[str, ...] = (
    r"\bA/B\b",
    r"\bab\s*test\b",
    r"\bexperiment\b",
    r"\btest\b",
    r"Broadcast Test",
    r"测试",
    r"测试样",
    r"短图文版本",
    r"学术解释格式",
)


@dataclass(frozen=True)
class PublicContentIssue:
    field: str
    term: str
    excerpt: str


class PublicContentError(ValueError):
    def __init__(self, issues: Sequence[PublicContentIssue]) -> None:
        self.issues = list(issues)
        detail = "; ".join(
            f"{issue.field}: matched {issue.term!r} near {issue.excerpt!r}"
            for issue in self.issues
        )
        super().__init__(f"public content guard failed: {detail}")


@dataclass(frozen=True)
class PublicCopyGateConfig:
    """Structured public-copy release criteria for platform captions."""

    min_compact_chars: int = 0
    required_any: tuple[str, ...] = ()
    explanatory_markers: tuple[str, ...] = ()
    min_explanatory_markers: int = 0
    allowed_topics: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    forbidden_topic_terms: tuple[str, ...] = ()
    forbid_latin_ratio_above: float | None = None


@dataclass(frozen=True)
class PublicCopyGateIssue:
    code: str
    detail: str


class PublicCopyGateError(ValueError):
    def __init__(self, issues: Sequence[PublicCopyGateIssue]) -> None:
        self.issues = list(issues)
        detail = "; ".join(f"{issue.code}: {issue.detail}" for issue in self.issues)
        super().__init__(f"public copy gate failed: {detail}")


def _excerpt(value: str, start: int, end: int, radius: int = 24) -> str:
    left = max(0, start - radius)
    right = min(len(value), end + radius)
    return value[left:right].replace("\n", " ").strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _normalize_topic(value: object) -> str:
    return re.sub(r"\s+", "", str(value).strip().strip("#"))


def _latin_ratio(value: str) -> float:
    compact = _compact(value)
    if not compact:
        return 0.0
    latin = sum(1 for char in compact if ("A" <= char <= "Z") or ("a" <= char <= "z"))
    return latin / len(compact)


def find_public_copy_gate_issues(
    *,
    title: object = "",
    caption: object = "",
    topics: Iterable[object] | None = None,
    config: PublicCopyGateConfig,
) -> list[PublicCopyGateIssue]:
    """Return deterministic public-copy release-gate issues.

    This is intentionally platform-neutral. Consuming repos provide the
    account-specific markers and topic allowlist.
    """
    title_text = str(title or "")
    caption_text = str(caption or "")
    compact_caption = _compact(caption_text)
    topic_names = [_normalize_topic(topic) for topic in (topics or []) if _normalize_topic(topic)]
    issues: list[PublicCopyGateIssue] = []

    if config.min_compact_chars and len(compact_caption) < config.min_compact_chars:
        issues.append(
            PublicCopyGateIssue(
                "caption_too_thin",
                f"{len(compact_caption)} chars < {config.min_compact_chars}",
            )
        )
    if config.required_any and not any(marker in caption_text for marker in config.required_any):
        issues.append(
            PublicCopyGateIssue(
                "caption_missing_required_context",
                f"need one of {list(config.required_any)!r}",
            )
        )
    if config.explanatory_markers:
        count = sum(1 for marker in config.explanatory_markers if marker in caption_text)
        if count < config.min_explanatory_markers:
            issues.append(
                PublicCopyGateIssue(
                    "caption_low_explanatory_density",
                    f"{count} markers < {config.min_explanatory_markers}",
                )
            )
    for term in config.forbidden_terms:
        if term and (term in title_text or term in caption_text):
            issues.append(PublicCopyGateIssue("forbidden_public_term", term))
    if config.forbid_latin_ratio_above is not None:
        ratio = max(_latin_ratio(title_text), _latin_ratio(caption_text))
        if ratio > config.forbid_latin_ratio_above:
            issues.append(
                PublicCopyGateIssue(
                    "latin_ratio_too_high",
                    f"{ratio:.3f} > {config.forbid_latin_ratio_above:.3f}",
                )
            )
    if config.allowed_topics:
        allowed = {_normalize_topic(topic) for topic in config.allowed_topics}
        weak = sorted(topic for topic in topic_names if topic not in allowed)
        if weak:
            issues.append(PublicCopyGateIssue("topic_not_allowed", f"weak={weak!r}"))
    for term in config.forbidden_topic_terms:
        if term and term in topic_names:
            issues.append(PublicCopyGateIssue("forbidden_topic", term))
    return issues


def assert_public_copy_gate(
    *,
    title: object = "",
    caption: object = "",
    topics: Iterable[object] | None = None,
    config: PublicCopyGateConfig,
) -> None:
    issues = find_public_copy_gate_issues(title=title, caption=caption, topics=topics, config=config)
    if issues:
        raise PublicCopyGateError(issues)


def find_internal_terms(
    fields: Mapping[str, object],
    *,
    terms: Iterable[str] = DEFAULT_INTERNAL_TERMS,
) -> list[PublicContentIssue]:
    issues: list[PublicContentIssue] = []
    compiled = [(term, re.compile(term, re.IGNORECASE)) for term in terms]
    for field, raw in fields.items():
        if raw is None:
            continue
        if isinstance(raw, (str, int, float)):
            value = str(raw)
        else:
            continue
        for term, pattern in compiled:
            match = pattern.search(value)
            if match:
                issues.append(
                    PublicContentIssue(
                        field=field,
                        term=term,
                        excerpt=_excerpt(value, match.start(), match.end()),
                    )
                )
    return issues


def assert_no_internal_terms(
    fields: Mapping[str, object],
    *,
    terms: Iterable[str] = DEFAULT_INTERNAL_TERMS,
) -> None:
    issues = find_internal_terms(fields, terms=terms)
    if issues:
        raise PublicContentError(issues)


def public_text_fields_from_manifest(data: Mapping[str, object], platform: str) -> dict[str, object]:
    if platform == "xhs":
        return {
            "title": data.get("title"),
            "body": data.get("body"),
            "topics": " ".join(str(item) for item in data.get("topics", []) or []),
        }
    if platform == "douyin":
        return {
            "title": data.get("title"),
            "caption": data.get("caption"),
            "topics": " ".join(str(item) for item in data.get("topics", []) or []),
        }
    if platform == "reddit":
        return {
            "body": data.get("body"),
        }
    if platform == "discourse":
        return {
            "body": data.get("body"),
        }
    return {key: value for key, value in data.items() if isinstance(value, str)}


def assert_manifest_public_ready(data: Mapping[str, object], platform: str) -> None:
    assert_no_internal_terms(public_text_fields_from_manifest(data, platform))


def assert_text_files_public_ready(paths: Iterable[Path]) -> None:
    fields: dict[str, object] = {}
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        fields[str(path)] = path.read_text(encoding="utf-8")
    assert_no_internal_terms(fields)
