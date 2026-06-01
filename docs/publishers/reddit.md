# Reddit publisher

Playwright-stealth based comment reply on **old.reddit.com**. Each call
submits one OP-level reply to a given thread URL via a logged-in account.

## Scope

In scope:
- OP-level (top-of-thread) comment reply
- Per-account persistent storage_state (`state/reddit/<account>/auth.json`)
- Cloudflare bypass via `playwright-stealth`
- Anonymous shadowban detection (5-min anon fetch · check for `[removed]` / mod-removed text)

Out of scope (caller's responsibility):
- Daily cap / rate limiting (broadcast-kit treats each publish call as atomic)
- Multi-account orchestration
- Nested comment-of-comment reply
- Original post (OP submit) — this kit only does comment-reply
- Metrics fetcher (use Reddit JSON API directly: `https://www.reddit.com/comments/<id>.json`)

## Why old.reddit + stealth

**old.reddit.com** because:
- Stable HTML selectors (the new React Reddit changes layout often)
- Reddit officially still supports it and has no plans to deprecate
- Simpler DOM = more reliable Playwright automation

**playwright-stealth** because:
- Default Playwright Chromium triggers Cloudflare browser-integrity check at `/login`
- You get a `You've been blocked by network security` page · login is impossible
- Stealth patches `navigator.webdriver` + CDP `Runtime.enable` signals + WebGL fingerprint + others
- Verified bypass against Reddit Cloudflare 2026-05-29

If you skip `pip install playwright-stealth` the kit still installs · but Reddit will likely block your login.

## Setup

```bash
pip install broadcast-kit  # includes playwright-stealth
python -m playwright install chromium
broadcast-kit-reddit login --fresh --account my_handle
# headed Chromium opens · log into Reddit (password / Google OAuth / etc.) · close window
# storage_state written to state/reddit/my_handle/auth.json
```

Google OAuth note: Google's OAuth flow has its own automation detection that
playwright-stealth may not fully bypass. If you hit "This browser may not be
secure", try email/password login instead.

## Publish

```bash
broadcast-kit-reddit publish \
  --manifest reddit-manifest.yaml \
  --account my_handle
```

Minimal manifest (`reddit-manifest.yaml`):

```yaml
id: my-reply-001
platform: reddit
thread_url: https://www.reddit.com/r/n8n/comments/1abcdef/some_thread/
body: |
  Your comment text here (markdown OK).
expected_subreddit: n8n  # optional · catches copy-paste mistakes
```

## Shadowban / AutoMod detection

Reddit's AutoMod can silently remove new-account comments. The kit's
`shadowban_check` does a fresh anonymous fetch of the posted URL:

```bash
broadcast-kit-reddit shadowban-check https://old.reddit.com/r/.../op2sqte/
```

Returns JSON with `suspected_shadowban: true|false`. Recommended to call
~5 minutes after publish (gives AutoMod time to act).

Detection signals:
- HTTP 404
- Body contains `[removed]` / `removed by moderators` / `page not found`

This is text-based · misses some edge cases (e.g. when the entire comment is
silently hidden without textual indicator). For higher confidence, also use
PRAW or Reddit JSON API to read your account's comment list directly.

## Account warming caveat

New Reddit accounts (zero karma · account age <1 month) get aggressive
AutoMod treatment in many subs (r/n8n / r/SelfHosted / r/homeassistant / etc.).
Expect 50-90% silent-remove rate during the first 1-2 weeks. Strategies:

- Pre-warm the account manually with peer-help comments in r/CasualConversation
  or r/NewToReddit (no automation · just be human)
- Accept the cost · use `shadowban_check` to surface what got through
- Start with karma-permissive subs (r/AskReddit · r/AI_Agents) before
  targeting karma-gated subs

## CLI reference

```
broadcast-kit-reddit login --account <handle> [--fresh]
broadcast-kit-reddit publish --manifest <path> --account <handle>
broadcast-kit-reddit shadowban-check <posted_url>
broadcast-kit-reddit accounts [--live-check]
broadcast-kit-reddit doctor --account <handle>
```

## Programmatic use

```python
from broadcast_kit.publishers.reddit.config import load_settings
from broadcast_kit.publishers.reddit.publish import submit_comment, shadowban_check

settings = load_settings(account="my_handle")
result = submit_comment(
    settings=settings,
    thread_url="https://www.reddit.com/r/n8n/comments/abc/...",
    body="Your reply text",
    dry_run=False,
)
print(result.posted_url)

# Later · check if it survived AutoMod
sb = shadowban_check(result.posted_url)
print(sb)  # {"ok": True/False, "suspected_shadowban": ..., ...}
```
