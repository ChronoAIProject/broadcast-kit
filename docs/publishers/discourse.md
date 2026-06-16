# Discourse publisher

Generic Discourse reply publisher. Works for any Discourse instance: the
n8n community forum, discuss.huggingface.co, meta.discourse.org, or any
self-hosted Discourse. Each instance just needs its own `--instance` flag.

## Scope

In scope:
- Reply to an existing topic (not new-topic creation)
- Per-(account · instance) persistent storage_state
  (`state/discourse/<account>__<instance_host>/auth.json`)
- Cloudflare bypass via `playwright-stealth` (rare for Discourse but some
  instances front with Cloudflare)
- **Accurate** shadowban detection via Topic JSON API (not text-match)

Out of scope:
- Daily cap / rate limiting (caller's responsibility)
- Multi-account orchestration
- New topic creation
- Metrics fetcher (use Topic JSON API directly: `<instance>/t/<id>.json`)

## Why generic Discourse

Discourse is a popular forum platform with consistent UI selectors across
instances and versions:
- `#topic-footer-buttons button.create` for the reply button
- `textarea.d-editor-input` for the compose editor
- `.save-or-cancel button.btn-primary` for submit

So one publisher handles all of them. You just provide:
- `instance_url`: e.g. `https://community.n8n.io`
- `topic_url`: e.g. `https://community.n8n.io/t/some-slug/12345`

## Why JSON API for shadowban check

The naive approach (anon HTML fetch + text-match for "removed") **does not work**
for Discourse. Discourse hides staged-for-review posts completely from the anon
view · no placeholder · no "waiting for review" text in the HTML. A text-match
would return false-positive "comment is visible" even when the post is staged.

The kit uses the Topic JSON API instead:

```
GET <instance>/t/<topic_id>.json  (anon)
→ {"post_stream": {"posts": [...]}}
```

The `posts` array is the authoritative list of what's actually visible to anon
users. If your username doesn't appear in it · your post is staged or hidden.
This catches the common new-account anti-spam case that text-match misses.

## Setup

```bash
pip install broadcast-kit
python -m playwright install chromium

# Login once per (account · instance) pair:
broadcast-kit-discourse login --fresh \
  --account my_handle \
  --instance https://community.n8n.io

# headed Chromium opens to <instance>/login · log in (email/password / OAuth) · close
```

The cookie domain is per-instance · so the same account name at two different
Discourse instances gets two separate `auth.json` files.

## Publish

```bash
broadcast-kit-discourse publish \
  --manifest discourse-manifest.yaml \
  --account my_handle
```

Manifest:

```yaml
id: my-reply-001
platform: discourse
instance_url: https://community.n8n.io
topic_url: https://community.n8n.io/t/some-topic-slug/12345
body: |
  Your reply body here (markdown OK).
expected_topic_id: 12345  # optional sanity check
```

The publisher auto-derives which `auth.json` to use from the instance_url in
the manifest plus the `--account` flag.

## Shadowban check

```bash
broadcast-kit-discourse shadowban-check \
  https://community.n8n.io/t/some-slug/12345 \
  --account my_handle
```

Returns JSON:

```json
{"ok": true, "suspected_shadowban": false, "post_number": 7}
```

or, for a staged post:

```json
{
  "ok": false,
  "suspected_shadowban": true,
  "reason": "@my_handle not in topic 12345 post list (3 posts: alice, bob, charlie) · most likely staged for staff review"
}
```

## New-account anti-spam reality

**Almost every Discourse instance** auto-stages the first few posts from
new accounts for staff review. This is normal anti-spam. Don't assume
publisher failure when shadowban_check returns staged · it usually
clears in 1-3 days after staff approve.

Strategies:
- Have a real human introduce themselves first (Discourse's "introduce yourself" topic exists on most instances)
- Read 10+ topics to bump Trust Level 0 → 1 (Discourse uses time-on-site
  signals)
- Pre-establish account via legitimate content before automation

If your account gets fully suspended ("account placed on hold"), reach out
to staff via inbox · explain the legitimate use case (e.g. "this is a
secondary account for sharing my dev experience"). Most staff approve.

## CLI reference

```
broadcast-kit-discourse login --account <handle> --instance <url> [--fresh]
broadcast-kit-discourse publish --manifest <path> --account <handle>
broadcast-kit-discourse shadowban-check <posted_url> --account <handle>
broadcast-kit-discourse accounts
broadcast-kit-discourse doctor --account <handle> --instance <url>
```

## Programmatic use

```python
from broadcast_kit.publishers.discourse.config import load_settings
from broadcast_kit.publishers.discourse.publish import submit_reply, shadowban_check

settings = load_settings(
    account="my_handle",
    instance_url="https://community.n8n.io",
)
result = submit_reply(
    settings=settings,
    topic_url="https://community.n8n.io/t/some-slug/12345",
    body="Your reply",
    dry_run=False,
)
print(result.posted_url)

sb = shadowban_check(result.posted_url, account="my_handle")
print(sb)
```
