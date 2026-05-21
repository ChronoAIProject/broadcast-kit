# Internal staff onboarding

You don't need to be a developer. Follow this page top to bottom.

## What this kit does for you

The first reliable path is: you give it a finished video, it polishes the caption with AI, and posts it to Douyin and Xiaohongshu at a scheduled time.

If your machine also has NotebookLM and SlideSync configured, it can generate the video from a PDF or markdown document first. Treat that as the advanced path.

## What you need before you start

- A Mac (the publishers need a visible browser window)
- About 30 minutes for first-time setup
- A Chrono Google account for NotebookLM
- A Douyin creator account (扫码 once)
- A Xiaohongshu creator account (扫码 once)

If you don't have one of these, ask your team lead before continuing.

## Step 1 — get the kit

Open Terminal and paste:

```bash
cd ~/Desktop
git clone <will-be-published-internal-url>/broadcast-kit
cd broadcast-kit
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

Each line waits for the previous one. If something looks red or says "error", stop and ask in the team channel.

If your task is to generate videos from source files through NotebookLM + SlideSync, install the optional source-to-video dependency too:

```bash
pip install '.[source-to-video]'
```

## Step 2 — run the setup wizard

One command. It walks you through the rest.

```bash
broadcast-kit setup
```

The wizard checks your machine, then asks a few questions:

- **LLM credentials** — pick NyxID (recommended for internal staff) or paste a key.
- **Douyin login** — answer "yes" when asked. A browser opens; scan the QR code in the Douyin app. Come back to Terminal and press Enter.
- **Xiaohongshu login** — same flow.
- **NotebookLM login** — same flow with your Chrono Google account.

The wizard is safe to re-run. It won't ask you the same question twice unless you pass `--reset`.

## Step 3 — check readiness

Run this after setup:

```bash
broadcast-kit doctor
```

Look at the `summary` block:

- `ok_for_douyin_existing_media: true` means you can publish a finished video to Douyin.
- `ok_for_xhs_existing_media: true` means you can publish a finished video or image note to Xiaohongshu.
- `ok_for_source_to_video: true` means NotebookLM + SlideSync generation should also be available.
- Anything listed under `blockers` must be fixed before publishing existing media.

After platform login, you can also run:

```bash
broadcast-kit doctor --live-login-check
```

That opens platform pages to verify saved cookies.

## Step 4 — publish your first known-good piece

Drop your source notes and your finished video somewhere on disk. Then:

```bash
broadcast-kit produce-publish \
  --input ~/Desktop/我的稿件.md \
  --video-file ~/Desktop/final-with-subtitles.mp4 \
  --platforms douyin,xhs \
  --schedule "2026-05-25T20:00:00+08:00"
```

What happens (you'll see a stage-by-stage report in Terminal):

1. The kit uses your `--video-file` as the publishable asset.
2. AI polishes the caption (`content_brain`, then a marketing-persona pass, then a reviewer).
3. Douyin and Xiaohongshu publishers open a browser, fill the form, click publish.

If any stage decides "hold" or "rejected", the kit **stops before publishing** and tells you why. Read the message and decide whether to fix and re-run, or skip the AI gate.

## Advanced path — generate video from source

Only use this after `broadcast-kit doctor` shows `ok_for_source_to_video: true`:

```bash
broadcast-kit produce-publish \
  --input ~/Desktop/我的稿件.pdf \
  --platforms douyin,xhs \
  --schedule "2026-05-25T20:00:00+08:00"
```

In this mode:

1. NotebookLM generates a slide deck + audio podcast.
2. SlideSync merges them into a video.
3. The same polish and publish steps run.

If NotebookLM or SlideSync is unavailable, the command will block publishing with a clear "no publishable video" message. Use the known-good `--video-file` path until the generation dependencies are fixed.

### Useful variations

```bash
# Just preview, don't actually publish:
broadcast-kit produce-publish --input X --video-file final.mp4 --platforms douyin,xhs --dry-run

# Use a finished video file:
broadcast-kit produce-publish --input X --video-file final.mp4 --platforms douyin

# Only Xiaohongshu:
broadcast-kit produce-publish --input X --video-file final.mp4 --platforms xhs

# Stop right before publishing (for review):
broadcast-kit produce-publish --input X --video-file final.mp4 --platforms douyin,xhs --skip publish
```

## Where things live on disk

```
broadcast-kit/
  state/                          ← your stuff (gitignored, stays on your Mac)
    .env                          ← LLM keys (chmod 600)
    douyin/auth.json              ← Douyin login cookie
    xhs/auth.json                 ← Xiaohongshu login cookie
    notebooklm/<slug>/            ← downloaded slides + audio per piece
    produce_publish/              ← merged videos + screenshots per run
```

Cookies last ~weeks. Re-run `broadcast-kit setup` if any platform asks you to log in again.

## When something breaks

The stage report names the stage that failed. Common ones:

| Stage says | What it means | What to do |
|---|---|---|
| `doctor.summary.blockers` has items | The machine is missing required publish dependencies | Fix the listed dependency, then re-run `broadcast-kit doctor` |
| `publish:douyin: blocked — no publishable video` | There is no final video to upload | Pass `--video-file final.mp4`, or fix NotebookLM/SlideSync |
| `notebooklm: skipped — adapter unavailable` | `notebooklm-py` isn't installed or login expired | `pip install notebooklm-py && notebooklm login` |
| `slidesync: skipped — missing inputs` | NotebookLM didn't finish | Re-run; if persistent, check NotebookLM session |
| `content_brain: hold` | AI thinks the content has a real risk | Read `risk_notes`; either fix the source or `--skip content_brain` if you're confident |
| `reviewer: rejected` | Composite score too low | Read `findings`; fix the issues OR re-run with `--skip reviewer` |
| `publish:douyin: failed` | Browser publish step crashed | Open `state/douyin/work/screenshots/` and inspect; usually a login expiry |

If the same error recurs across runs, drop the **stage report JSON** in the team channel — that has everything we need to debug.

## Don't do these things

- Don't commit `state/` to git. It has your auth cookies. (It's gitignored already; just don't fight it.)
- Don't pass `--skip reviewer --skip content_brain` together — that's the whole point of the AI gate.
- Don't run `--force-republish` if you don't know what it does. Ask first.
- Don't share your `state/.env` over Slack/Lark/email. If you need to send a key, use NyxID.

## If you have multiple accounts

If you run more than one Douyin or Xiaohongshu account from this machine (for example `学术号` / `古籍号` / `个人号`), use the `--account <label>` flag. Each account has its own login cookie and working directory; no need to log out and back in between posts.

The pattern is:

```bash
# Step A — set up the host once.
broadcast-kit setup --for tier1

# Step B — log in each account separately. Pick a short label per account.
python -m broadcast_kit.publishers.douyin.cli login --fresh --account academic
python -m broadcast_kit.publishers.douyin.cli login --fresh --account classical
python -m broadcast_kit.publishers.xhs.cli   login --fresh --account academic
python -m broadcast_kit.publishers.xhs.cli   login --fresh --account classical

# Step C — every publish action gets --account <label>.
broadcast-kit publish --platform douyin --manifest manifest.yaml --account academic
broadcast-kit publish --platform xhs    --manifest manifest.yaml --account classical
broadcast-kit produce-publish \
  --input ~/Desktop/我的稿件.md \
  --video-file ~/Desktop/final.mp4 \
  --platforms douyin,xhs \
  --account academic \
  --schedule "2026-05-25T20:00:00+08:00"
```

To check which accounts are set up on this machine:

```bash
python -m broadcast_kit.publishers.douyin.cli accounts
python -m broadcast_kit.publishers.xhs.cli accounts
# Add --live-check to actually verify each cookie against the creator center
```

If you forget `--account`, the kit uses the account labelled `default` (which is whatever was logged in before the multi-account upgrade). Existing single-account setups keep working unchanged — a one-line `[migrate]` message prints the first time you run after the upgrade.

X (Twitter) does not yet support `--account` in this version. If you publish to multiple X handles, manage credentials the existing way and ignore the flag for X.

## What's next

Read [`CATALOG.md`](../CATALOG.md) at the kit root when you want to do something more than the one-shot flow — running a sprint, scoring engagement after publish, generating A/B hook variants. The catalog is the menu of every part you can call.
