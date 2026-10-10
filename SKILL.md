---
name: crispy-ai-coffee-daily
description: Produce one daily episode of 「脆脆的AI早咖啡」 (Chinese ~85 s vertical AI-news video for 微信视频号) — collect yesterday's AI news from X, verify, write brief.json in the 脆脆 persona, run one command, check one contact sheet, deliver files. Use for the 07:30 Asia/Shanghai scheduled run or any "make today's AI coffee episode" request. Never publishes anything.
---

# 脆脆的AI早咖啡 · daily run (start 07:30, deliver by 08:00 Asia/Shanghai)

Repo root = this folder. Detail lives in `assets/persona.md` (voice bible) and `README.md`; don't re-read them unless stuck.
**Never post/publish anything.** Output only files.

**Writing (from 2026-10-11 / 第003杯):** Priority #1 = explain each story clearly in plain spoken Chinese. Coffee wordplay only in the fixed opening + sign-off (channel name). 锐评 = one short plain sentence (friend explaining), no forced puns. See `assets/persona.md`.

## 0. Setup check (10 s)
`[ -x .venv/bin/python ] || ./setup.sh` · `D=$(TZ=Asia/Shanghai date +%F)` (= publish morning = folder name `output/$D/`)
`.venv/bin/python run.py --init --date $D` → creates `output/$D/brief.json` (fill-in template).

## 1. Collect (x MCP, ≤25 calls total; window = yesterday 00:00 → today 07:30 Asia/Shanghai)
`GetDynamicTools(namespace="x")` once, then `CallDynamicTool`:
- **search_news** ×4 (`max_age_hours=30`, `max_results=25`): `AI` · `OpenAI Anthropic Google Gemini` · `AI chips funding valuation` · `China AI model DeepSeek Qwen`
- **search_posts_all** ×5 (`start_time`=window start UTC ISO, `sort_order=recency`, `max_results=25`, `post.fields=public_metrics,created_at`, `expansions=author_id`, `user.fields=username`):
  1 `(from:OpenAI OR from:sama OR from:OpenAIDevs) -is:reply -is:retweet`
  2 `(from:AnthropicAI OR from:claudeai OR from:GoogleDeepMind OR from:GeminiApp OR from:sundarpichai) -is:reply -is:retweet`
  3 `(from:xai OR from:elonmusk OR from:AIatMeta OR from:nvidia OR from:MistralAI) AI -is:reply -is:retweet`
  4 `(from:deepseek_ai OR from:Alibaba_Qwen OR from:Kimi_Moonshot) -is:reply -is:retweet`
  5 `(OpenAI OR Anthropic OR AI) (lawsuit OR quits OR bounty OR leaked OR drama) -is:retweet` with `sort_order=relevancy`
- **Verify** ≤14: keyword `search_posts_all` to find each candidate's original post; then ONE `get_posts_by_ids` for all chosen ids with `expansions=attachments.media_keys,author_id`, `media.fields=type,url,variants,preview_image_url,duration_ms`, `post.fields=public_metrics,created_at,text` (gives heat + official media URLs in one call).
- `search_news` summaries are leads only, never a source.

## 2. Choose (5 stories for the video, 6–9 items in brief)
- Heat = likes + 3×reposts + 2×quotes of the original post; prefer in-window, new developments only.
- Mix: ≥2 tech, ≥1 biz, exactly 1 gossip/people (last, `"segment":"zha"`); ≤3 from one company.
- Drop anything without a first-party post or a credible outlet; no crypto/marketing.
- **Cross-check every chosen story with WebSearch** (official page or credible media); put ≥2 URLs in `sources`.

## 3. Write `output/$D/brief.json` (schema: `schema/brief.schema.json`; validator enforces it)
- Facts/numbers/quotes exactly as sources say; reports keep 「据《X》报道/称」; uncertain → leave out.
- **Priority #1 — explain clearly:** each story = what happened · who · key number · why it matters to an ordinary person, in plain spoken Chinese.
- Fixed lines (validator checks via `assets/channel.json` catchphrases):
  - opening **「早上好，我是脆脆，欢迎收看脆脆的AI早咖啡。」** (+ optional 「今天主要看：A，B。」 — no coffee flavor)
  - story 2+ starts **「下一条。」**
  - gossip (last, `"segment":"zha"`) starts **「最后说个八卦。」** (on-screen pink「咖啡渣时间」card stays)
  - every story ends **「锐评：…」**(≤16字, plain opinion — what it means / what to watch for; no forced puns/slang/analogies; no new facts) + `take` (≤20字 on screen)
  - outro exactly **「关注脆脆的AI早咖啡，明天早上八点见。」**
- Drop from narration: 现磨 / 趁热喝 / 下一口 / 今天这杯 / 咖啡见底 / 续杯 / 咖啡渣时间 / 今日一瓜 (banned list enforces).
- Story = fact → number → 锐评, 55–75 字; total narration 360–420 字 (≈80–90 s). Short sentences, 你 not 大家, no 新闻腔/过气网络词 (validator bans list in `assets/channel.json`). Write numbers as digits, `$300`→`300美元`, no brackets/emoji.
- `headline` ≤10字, `point` ≤20字, `video.cover_title` 2×≤9字, `cover_tags` 4–5, `sph` title 6–16字 + 3 lines + 3–6 hashtags. Last description line plain: **「每天早上8点，用大白话讲清楚昨天的AI大事」** (or same idea). Voice is locked in `assets/channel.json` — don't set it.
- **Media (optional, 0–3 stories):** only official visuals of that story (its official X post attachment, official page/press kit, or the source person's own screenshot). `media: {url, page, credit, type, start, end, fit}`; clips muted & auto-trimmed; `start` skips intro logos, `end` freezes on a meaningful frame (product name/UI) instead of a blank end card. No stock/random/other-outlet images, never AI-generated images of real people/products. Nothing suitable → omit.

## 4. Run (one command, ~2–3 min, cached reruns)
`.venv/bin/python run.py --date $D`
Prints PASS/FAIL + paths. On FAIL it shows the reason and log tail: fix brief.json → rerun same command (finished steps are skipped).

## 5. Check ONE image
Read `output/$D/qa/contact_sheet.png` (cover/first frame, intro, every story at its 锐评 moment, outro, 3:4 cover). Look for: tofu boxes, clipped/overlapping text, subtitles >2 lines, media frame cropping something important, wrong credit. Fix → rerun.

## 6. Deliver (report paths + 1-line summary; do NOT upload)
`output/$D/crispy-ai-coffee-$D.mp4` · `output/$D/sph/cover_3x4_1080x1440.png` · `output/$D/sph/caption.txt` · `output/$D/sph/sources.txt` (+ the 5 stories with sources, duration, media used, anything unverified).

## Failure handling
- TTS/network: pipeline retries 6× then falls back (QA fails on fallback) → wait 1–2 min, `run.py --date $D --force tts`.
- Validator errors: fix the named field. Layout "note:" lines are hints, not failures.
- Duration out of 75–90 s: add/cut ~10 字 per 2 s.
- Media download 403/404: drop that `media` block (don't substitute random images).
- X rate limit (429): wait 60 s. Out of budget: go with what's verified (min 4 stories).
- Machine lost: `git clone https://github.com/YUECHENCUI/crispy-ai-coffee.git && cd crispy-ai-coffee && ./setup.sh`.
