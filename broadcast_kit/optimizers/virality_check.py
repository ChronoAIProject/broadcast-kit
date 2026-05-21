"""Pre-publish virality scoring layer.

Two optional scorers gated on their backend availability:

- :func:`bitgrit` — text scorer for X-style posts via the bitgrit
  ``x-virality-api`` HTTP endpoint. Free tier: 1000 calls/month, 10 rps.
  Activates only when ``BITGRIT_API_KEY`` is set.

- :func:`higgsfield` — short-video scorer that shells out to the
  ``higgsfield`` CLI. Activates only when the CLI is on PATH.

Both return a :class:`ViralityScore` with ``status="skipped"`` (never raise)
when their backend is unavailable, so they can be wired into a publisher
pipeline that opportunistically gathers signal where possible.

The :func:`score` dispatcher picks the right scorer for a given :class:`Draft`
and platform. :func:`rank_drafts` sorts a batch by score descending for
ordering / selection.

No new dependencies — only stdlib (urllib, subprocess, shutil, json).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import request as urllib_request

from .base import Draft


BITGRIT_ENDPOINT = "https://www.bitgritapi.net/x/x-virality-api"
HIGGSFIELD_CLI = "higgsfield"
HIGGSFIELD_INSTALL_HINT = "npm install -g @higgsfield/cli && higgsfield auth login"

ViralityStatus = Literal["ok", "skipped", "error"]


@dataclass
class ViralityScore:
    """Normalized virality scorer output.

    ``score`` is always on a 0-100 scale (or ``None`` when skipped/errored).
    ``sub_scores`` is source-specific (e.g. ``hook_score``, ``hold_rate``,
    ``viral_potential``). ``raw`` carries the unparsed API/CLI payload for
    callers that want to inspect it.
    """

    source: str
    status: ViralityStatus
    score: float | None
    sub_scores: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


def _skipped(source: str, reason: str) -> ViralityScore:
    return ViralityScore(source=source, status="skipped", score=None, reason=reason)


def _errored(source: str, reason: str, raw: dict[str, Any] | None = None) -> ViralityScore:
    return ViralityScore(
        source=source,
        status="error",
        score=None,
        raw=raw or {},
        reason=reason,
    )


def bitgrit(text: str, followers: int = 0, following: int = 0) -> ViralityScore:
    """Score an X-style post via the bitgrit virality API.

    Returns ``status="skipped"`` if ``BITGRIT_API_KEY`` is unset, and
    ``status="error"`` on HTTP failures. Normalizes the 0-1 API score to
    0-100.
    """
    api_key = os.getenv("BITGRIT_API_KEY")
    if not api_key:
        return _skipped("bitgrit", "BITGRIT_API_KEY not set")

    payload = {
        "followers": int(followers),
        "following": int(following),
        "tweet": text,
    }
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    req = urllib_request.Request(
        BITGRIT_ENDPOINT,
        headers=headers,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return _errored("bitgrit", f"HTTP {exc.code}: {exc.reason} {body}".strip())
    except Exception as exc:
        return _errored("bitgrit", str(exc))

    raw_score = data.get("score")
    if not isinstance(raw_score, (int, float)):
        return _errored("bitgrit", f"missing/invalid 'score' in response: {data}", raw=data)

    score_100 = float(raw_score) * 100.0
    return ViralityScore(
        source="bitgrit",
        status="ok",
        score=score_100,
        sub_scores={"raw_score_01": float(raw_score)},
        raw=data,
    )


def higgsfield(clip_path: str | Path) -> ViralityScore:
    """Score a short-form clip via the higgsfield CLI.

    Returns ``status="skipped"`` when the CLI isn't on PATH, and
    ``status="error"`` on non-zero exit / stale auth / unparseable JSON.
    """
    if shutil.which(HIGGSFIELD_CLI) is None:
        return _skipped(
            "higgsfield",
            f"higgsfield CLI not installed ({HIGGSFIELD_INSTALL_HINT})",
        )

    cmd = [
        HIGGSFIELD_CLI,
        "virality",
        "score",
        "--input",
        str(clip_path),
        "--json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        return _errored("higgsfield", f"higgsfield CLI timeout: {exc}")
    except Exception as exc:
        return _errored("higgsfield", f"higgsfield CLI invocation failed: {exc}")

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        return _errored(
            "higgsfield",
            f"higgsfield CLI exited {proc.returncode}: {stderr or proc.stdout.strip()}",
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _errored(
            "higgsfield",
            f"could not parse higgsfield JSON: {exc}; stdout={proc.stdout[:400]}",
        )

    viral_potential = data.get("viral_potential")
    if not isinstance(viral_potential, (int, float)):
        return _errored(
            "higgsfield",
            f"missing/invalid 'viral_potential' in response: {data}",
            raw=data,
        )

    sub_scores: dict[str, float] = {}
    for key in ("hook_score", "hold_rate"):
        val = data.get(key)
        if isinstance(val, (int, float)):
            sub_scores[key] = float(val)

    return ViralityScore(
        source="higgsfield",
        status="ok",
        score=float(viral_potential),
        sub_scores=sub_scores,
        raw=data,
    )


def score(draft: Draft, *, clip_path: str | Path | None = None) -> ViralityScore:
    """Dispatch a draft to the appropriate scorer.

    - ``platform == "x"`` with non-empty ``body`` → :func:`bitgrit`.
    - ``platform == "douyin"`` with a ``clip_path`` → :func:`higgsfield`.
    - ``platform == "xhs"`` → :func:`bitgrit` on ``body`` as a generic
      engagement-text proxy. The bitgrit model is trained on X, so treat
      the result as a rough proxy rather than an XHS-native signal.
    - Otherwise returns ``status="skipped"``.

    ``draft.context`` may include ``followers`` and ``following`` for the
    bitgrit path.
    """
    followers = int(draft.context.get("followers", 0) or 0)
    following = int(draft.context.get("following", 0) or 0)

    if draft.platform == "x" and draft.body:
        return bitgrit(draft.body, followers=followers, following=following)
    if draft.platform == "douyin" and clip_path is not None:
        return higgsfield(clip_path)
    if draft.platform == "xhs" and draft.body:
        return bitgrit(draft.body, followers=followers, following=following)
    return _skipped(
        "skipped",
        "no scorer configured for this platform/draft combination",
    )


def rank_drafts(drafts: list[Draft]) -> list[tuple[Draft, ViralityScore]]:
    """Score and rank a batch of drafts in descending score order.

    Drafts whose score is ``None`` (skipped / errored) sort last but keep
    their original relative order among themselves.
    """
    scored: list[tuple[Draft, ViralityScore]] = [(d, score(d)) for d in drafts]
    scored.sort(
        key=lambda pair: (
            0 if pair[1].score is not None else 1,
            -(pair[1].score or 0.0),
        )
    )
    return scored
