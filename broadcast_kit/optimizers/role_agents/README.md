# Vendored role-agent prompts

Source: [`msitarzewski/agency-agents`](https://github.com/msitarzewski/agency-agents) (MIT). See `LICENSE.agency-agents`.

The files in this directory are pure-prompt role specs (frontmatter + system prompt body). They are loaded by `broadcast_kit/optimizers/market_role.py` as `system` prompts when polishing a draft.

| File | Role | Use for |
|---|---|---|
| `douyin.md` | Douyin Strategist | 3-second hook + completion-rate critique for Douyin captions |
| `xhs.md` | Xiaohongshu Specialist | Aesthetic/lifestyle reframe + title/cover review for XHS notes |
| `x.md` | Twitter Engager | Thread structure + reply-bait critique for X threads |
| `growth.md` | Growth Hacker | Cross-platform funnel + acquisition-loop critique |

Cross-platform `growth.md` is intended as a second-pass after the platform-specific role. The `market_role` optimizer can chain `<platform>` → `growth`.

Original files are unmodified. Frontmatter is intact for skill-discovery.
