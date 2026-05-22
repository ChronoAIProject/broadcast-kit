# Xiaohongshu (XHS) Publisher

Self-contained Playwright-based XHS publisher. Lives at `broadcast_kit/publishers/xhs/`. No external repo dependency.

## What it does

- Logs into `creator.xiaohongshu.com` with a persisted Playwright `storage_state` (no QR re-scan after first login).
- Uploads images (up to 18) or a single video.
- Fills title (<=20 chars) and body (<=1000 chars).
- Selects topics through the topic-picker UI (not raw `#hashtag` text in body — XHS treats those as plain text).
- Clicks the publish button.
- Returns a verdict and (when detectable) the note URL.

XHS has no official publish API. Everything routes through the creator center via Playwright.

## What it does NOT do

This kit ships the bare publisher only. It does not include:

- A learning loop or experiment table (build that on top if you want one)
- A content brain / dbskill review chain
- A hourly publish daemon (use launchd/cron/your own scheduler)
- Metrics scraping (XHS metrics in this kit returns `status: stub`)

## Required tools

- Python 3.11+
- `pip install playwright pydantic pyyaml typer python-dotenv pillow`
- `python -m playwright install chromium`

## Environment variables

All paths default under `$BROADCAST_KIT_STATE_DIR/xhs/`.

| Variable | Purpose | Default |
|---|---|---|
| `BROADCAST_KIT_STATE_DIR` | Root for all runtime state | `./state` |
| `XHS_AUTH_STATE` | Playwright storage_state json path | `state/xhs/auth.json` |
| `XHS_WORK_ROOT` | Working dir for screenshots | `state/xhs/work` |
| `XHS_SCREENSHOT_DIR` | Screenshot output | `state/xhs/work/screenshots` |
| `XHS_CREATOR_PUBLISH_URL` | Creator publish entrypoint | `https://creator.xiaohongshu.com/publish/publish?source=official` |
| `XHS_SKIP_SUBMIT` | If true/1, never click final publish | unset |
| `XHS_KEEP_OPEN` | If true/1, leave Chromium open after run | unset |

## First-time login

```bash
python -m broadcast_kit.publishers.xhs.cli login --fresh
```

A non-headless Chromium opens. Scan the QR code in the XHS app. Return to the terminal and press Enter — storage_state is saved to `XHS_AUTH_STATE`. Next runs reuse this file; no QR re-scan unless the cookie expires.

Check login validity:

```bash
python -m broadcast_kit.publishers.xhs.cli login
# prints "valid" or "expired"
```

> **Note:** `check_login_valid()` is NOT a local file check. It launches a
> headless Chromium, navigates to `creator.xiaohongshu.com`, and waits for the
> DOM — expect **5–15 seconds** of wall-clock cost plus dependency on the user's
> network reaching Xiaohongshu's edge. It can also time out / return false for
> reasons unrelated to the cookie (network blips, XHS UI revs). For frequent
> checks (per-publish preflights, hot loops), **cache the result with a short
> TTL** instead of re-running it every call.

If you only need to know whether the user has finished the **first interactive
login** (i.e. does an `auth.json` exist yet?), use the fast file-stat helper
`is_auth_state_present(settings)` instead — no Chromium, no network:

```python
from broadcast_kit.publishers.xhs import (
    Settings,
    is_auth_state_present,
)
from broadcast_kit.publishers.xhs.publish import check_login_valid

settings = Settings.for_xhs(account="default")

# Fast: just stats the file on disk. No Chromium, no network. <1 ms.
if not is_auth_state_present(settings):
    raise SystemExit("Run `xhs login --fresh` first.")

# Slow: launches headless Chromium + hits creator.xiaohongshu.com. 5–15 s.
# Only call this when you actually need to confirm the cookie still works.
if not check_login_valid(settings):
    raise SystemExit("Cookie expired — run `xhs login --fresh` again.")
```

Rule of thumb: gate first-time setup on `is_auth_state_present`, gate
publish-time correctness on `check_login_valid` (cached).

## Manifest

JSON or YAML. Example `manifest.yaml`:

```yaml
id: XHS-001
title: "正式标题"
body: |
  第一段:一句话钩子。

  第二段:解释截图里发生了什么。

  第三段:落到普通人能理解的场景。

  第四段:轻引导。
asset_kind: image
asset_paths:
  - covers/01.png
  - covers/02.png
topics:
  - 自我认知
  - 命理
```

Constraints (validated by the manifest schema):

- `title` 1–20 chars
- `body` 1–1000 chars
- `asset_kind`: `image` (1–18 assets) or `video` (exactly 1 asset)
- `topics` must be selectable through the XHS topic picker — raw hashtag text in `body` is ignored by XHS as plain text

### Public Content Guard

The XHS manifest parser blocks obvious internal operating language from public
fields before upload. The guard checks `title`, `body`, and `topics` for terms
such as `测试`, `短图文版本`, `Test`, `A/B`, `experiment`, and
`Broadcast Test`.

Keep experiment IDs, variant names, and A/B notes in local state, metrics, or
manifest metadata fields that are not published. Public fields must read like a
finished note.

## Commands

Publish a note (live):

```bash
python -m broadcast_kit.publishers.xhs.cli publish \
  --manifest /path/to/manifest.yaml
```

Dry-run (uploads media + fills text + selects topics, but does NOT click publish):

```bash
python -m broadcast_kit.publishers.xhs.cli publish \
  --manifest /path/to/manifest.yaml \
  --dry-run
```

Alternative — invoke through the top-level broadcast-kit CLI:

```bash
broadcast-kit publish --platform xhs --manifest /path/to/manifest.yaml
```

## Result shape

```python
{
    "platform": "xhs",
    "status": "success" | "failed" | "not_submitted" | "manifest_invalid" | "asset_missing",
    "judgement": "success" | "failed" | "not_submitted",
    "detail": "...",
    "note_url": "https://www.xiaohongshu.com/...?published=true" | None,
    "screenshots": ["/abs/path/tab-selected-...png", ...],
    "manifest_path": "/abs/path/manifest.yaml",
}
```

Success detection looks for `发布成功` / `笔记发布成功` in the page body, or `published=true` in the URL. If neither marker hits, treat as `failed` and inspect the latest screenshot.

`published=true` is only a submit-page signal. For production workflows, do a
post-submit verification pass in the creator center's note manager:

1. Open `https://creator.xiaohongshu.com/new/note-manager` with the same account storage state.
2. Check `已发布` and `全部笔记`; XHS can briefly show `全部笔记(0)` until the tab refreshes.
3. Match the note by title and publish time.
4. Open `编辑` and verify the actual public body and media count.
5. Treat the note as published only after the manager row or edit page confirms it.

When editing an existing image note, uploading a new image set can append files
unless the "重新上传将会清空已上传的图片" confirmation is accepted. Confirm
the media count after repair, for example `5/18` rather than an accidental
`10/18`.

## Multi-account

The XHS publisher supports publishing from multiple Xiaohongshu accounts on the same host. Each account has its own auth cookie and working directory under `state/xhs/<account>/`.

**State layout**

```
state/xhs/
  default/            # default account, used when --account is omitted
    auth.json
    work/             # screenshots
  academic/
    auth.json
    work/
  classical/
    auth.json
    work/
```

**First-time login for a non-default account**

```bash
python -m broadcast_kit.publishers.xhs.cli login --fresh --account academic
```

A non-headless Chromium opens; scan the QR with the target XHS account, press Enter. `storage_state` is saved to `state/xhs/academic/auth.json`. Repeat per account.

**List accounts**

```bash
python -m broadcast_kit.publishers.xhs.cli accounts
# prints each account: label, auth.json mtime, exists?
python -m broadcast_kit.publishers.xhs.cli accounts --live-check
# additionally opens each account's saved cookie against creator.xiaohongshu.com to confirm validity
```

**Use `--account` at every command**

```bash
# Publish from the academic account
python -m broadcast_kit.publishers.xhs.cli publish \
  --manifest /path/to/manifest.yaml \
  --account academic

# Doctor for one account or all
python -m broadcast_kit.publishers.xhs.cli doctor --account academic
python -m broadcast_kit.publishers.xhs.cli doctor --all-accounts

# Same flag on the top-level CLI
broadcast-kit publish --platform xhs --manifest manifest.yaml --account academic
broadcast-kit doctor --account academic
```

If `--account` is omitted, the publisher uses `default`.

**`XHS_AUTH_STATE` still wins.** If you export `XHS_AUTH_STATE=/path/to/auth.json`, that explicit path is used regardless of `--account`. This preserves the single-account muscle memory for users who manage cookies via the env var.

**Auto-migration**

On first invocation after upgrade, if `state/xhs/auth.json` exists at the legacy path but `state/xhs/default/auth.json` does not, the file is moved into the new layout and a one-line warning is printed:

```
[migrate] state/xhs/auth.json -> state/xhs/default/auth.json
```

After migration, existing flows that didn't pass `--account` keep working — they resolve to the `default` account automatically.

**Playbook per account**

Playbook files now live at `state/playbook/xhs/<account>.yaml` (legacy `state/playbook/xhs.yaml` is auto-migrated on next write). The playbook YAML carries a top-level `account: <label>` field.

## Operational notes

- Chromium runs **non-headless**. Same display requirement as Douyin.
- Selectors target the current creator-center DOM; XHS revs the UI frequently. If a selector breaks, inspect the page and patch `SELECTORS` in `broadcast_kit/publishers/xhs/publish.py`.
- The publisher avoids forbidden patterns at the manifest layer (title length, asset count). It does not enforce XHS content policy — assume you've vetted content elsewhere.
- The screenshots at `tab-selected`, `upload-after`, `meta-after`, `topics-after`, `publish-after` cover the full publish flow for post-mortem.
