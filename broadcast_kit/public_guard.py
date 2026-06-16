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


def _excerpt(value: str, start: int, end: int, radius: int = 24) -> str:
    left = max(0, start - radius)
    right = min(len(value), end + radius)
    return value[left:right].replace("\n", " ").strip()


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
