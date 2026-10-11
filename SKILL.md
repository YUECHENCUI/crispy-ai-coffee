---
name: crispy-ai-coffee-daily
description: Produce one daily episode of 「脆脆的AI早咖啡」 (Chinese ~85 s vertical AI-news video for 微信视频号) — collect yesterday's AI news from X across LLM labs + robotics/multimodal/science/finance/everyday apps, verify, write brief.json in the 脆脆 persona, run one command, check one contact sheet, deliver files. Use for the 07:30 Asia/Shanghai scheduled run or any "make today's AI coffee episode" request. Never publishes anything.
---

# 脆脆的AI早咖啡 · daily run (start 07:30, deliver by 08:00 Asia/Shanghai)

Repo root = this folder. Detail lives in `assets/persona.md` (voice bible) and `README.md`; don't re-read them unless stuck.
**Never post/publish anything.** Output only files.

**Writing (from 2026-10-11 / 第003杯):** Priority #1 = explain each story clearly in plain spoken Chinese. Coffee wordplay only in the fixed opening + sign-off (channel name). 锐评 = one short plain sentence (friend explaining), no forced puns. See `assets/persona.md`.

**Selection (from 2026-10-12 / 第004杯):** LLMs stay the main thread, but **do not** fill the episode with only Claude/OpenAI/Gemini. Broad AI tech + everyday-life/fun apps. See §1–2.

## 0. Setup check (10 s)
`[ -x .venv/bin/python ] || ./setup.sh` · `D=$(TZ=Asia/Shanghai date +%F)` (= publish morning = folder name `output/$D/`)
`.venv/bin/python run.py --init --date $D` → creates `output/$D/brief.json` (fill-in template).
Peek yesterday's lead company in `output/` (or last delivered caption) so you don't repeat the same company as lead two days in a row.

## 1. Collect (x MCP, ≤25 calls total; window = yesterday 00:00 → today 07:30 Asia/Shanghai)
`GetDynamicTools(namespace="x")` once, then `CallDynamicTool`. Prefer **~2–3 queries per bucket** below (`search_news` with `max_age_hours=30`, `max_results=25` + a few `search_posts_all` for engagement). Leave ~12–14 calls for verify.

### Category buckets (sample queries — pick 1–2 per bucket that fit the day; skip empty ones)
| Bucket | Aim | Sample `search_news` | Sample `search_posts_all` (`start_time`=window start UTC, `-is:reply -is:retweet`, `post.fields=public_metrics,created_at`, `expansions=author_id`, `user.fields=username`) |
|---|---|---|---|
| **A. LLM labs** (main thread, don't over-index) | Model releases, API, safety | `OpenAI Anthropic Claude Gemini GPT` | `(from:OpenAI OR from:AnthropicAI OR from:claudeai OR from:GoogleDeepMind OR from:xai OR from:AIatMeta) -is:reply -is:retweet` |
| **B. Robotics / embodied / world models / autonomy** | Tesla FSD/Optimus, SpaceX/xAI hardware, humanoids | `Tesla FSD OR Optimus OR robotics OR "world model" OR "embodied AI" OR humanoid` | `(from:Tesla OR from:elonmusk OR from:SpaceX OR from:xai OR from:Figure_robot) (FSD OR Optimus OR robot OR AI) -is:reply -is:retweet` |
| **C. Multimodal gen** | Video/image/audio/3D gen | `AI video generation OR Sora OR Runway OR Midjourney OR Suno OR "3D generation"` | — |
| **D. Everyday-life / fun apps** ★ required pick | Viral demos, consumer features, quirky uses people can try | `viral AI app OR ChatGPT tip OR "AI demo" OR "AI helped me" OR "try this AI" OR consumer AI feature` | `(AI OR ChatGPT OR Claude) (demo OR tip OR tutorial OR "try this" OR lifestyle OR cooking OR travel) -is:retweet` `sort_order=relevancy` |
| **E. AI + science** | Math, neuroscience, bio/drug discovery | `AI science OR AlphaFold OR "drug discovery" OR neuroscience OR "AI math"` | — |
| **F. Finance / chips / investing** | Funding, markets, semis, IPOs | `AI chips funding OR NVIDIA OR semiconductor OR "AI IPO" OR valuation` | `(from:nvidia) (AI OR GPU OR chip) -is:reply -is:retweet` |
| **G. China AI / devices / policy** | DeepSeek/Qwen, gadgets, regulation | `China AI DeepSeek Qwen OR "AI device" OR "AI policy" OR "AI regulation"` | `(from:deepseek_ai OR from:Alibaba_Qwen OR from:Kimi_Moonshot) -is:reply -is:retweet` |
| **H. People / drama** | Quits, lawsuits, bounty, leaked | — | `(AI OR OpenAI OR Anthropic OR Tesla) (lawsuit OR quits OR leaked OR drama OR bounty) -is:retweet` `sort_order=relevancy` |

**Suggested call mix (~10 collect + ≤14 verify ≈ 24):** `search_news` ×6–7 across A–G · `search_posts_all` ×3–4 (A labs + B robotics/Tesla + D everyday + H drama) · verify ≤14 (keyword find originals + ONE `get_posts_by_ids` with `expansions=attachments.media_keys,author_id`, `media.fields=type,url,variants,preview_image_url,duration_ms`, `post.fields=public_metrics,created_at,text`).
- `search_news` summaries are leads only, never a source.

## 2. Choose (5 stories for the video, 4–6 ok; 6–9 items in brief)
- Heat = likes + 3×reposts + 2×quotes of the original post; rank by **engagement + recency + significance**. Final picks = agent judgment.
- **Diversity (hard rules from 第004杯):**
  1. **≤2** stories from pure LLM labs (OpenAI / Anthropic / Google DeepMind / xAI / Meta **model releases**). Labs' non-model news (policy, hiring drama) may count as gossip/biz instead.
  2. **≥2** from outside LLMs: robotics/autonomy/world models · multimodal gen · AI+science · AI+finance/chips/investment · consumer hardware · policy.
  3. **≥1 everyday-life / fun application** story (bucket D): a viral demo, consumer feature, or quirky use — narrate **what an ordinary person can actually do with it**, not just the model name.
  4. Exactly **1** gossip/people slot last (`"segment":"zha"`); gossip can be any area.
  5. **Don't** lead with the same company two mornings in a row.
  6. ≤2 from one company overall; drop crypto/marketing and anything without a first-party post or credible outlet.
- Tag each item with a `category`: `tech` 技术 · `app` 应用 (everyday/fun/multimodal products) · `hardtech` 硬科技 · `science` 科学 · `capital` 资本 · `biz` 商业 · `gossip` 八卦·人物.
- **Cross-check every chosen story with WebSearch** (official page or credible media); put ≥2 URLs in `sources`.

## 3. Write `output/$D/brief.json` (schema: `schema/brief.schema.json`; validator enforces it)
- Facts/numbers/quotes exactly as sources say; reports keep 「据《X》报道/称」; uncertain → leave out.
- **Priority #1 — explain clearly:** each story = what happened · who · key number · why it matters to an ordinary person, in plain spoken Chinese. Everyday/fun stories: say **what you can try / tap / get**.
- Fixed lines (validator checks via `assets/channel.json` catchphrases):
  - opening **「早上好，我是脆脆，欢迎收看脆脆的AI早咖啡。」** (+ optional 「今天主要看：A，B。」 — no coffee flavor)
  - story 2+ starts **「下一条。」**
  - gossip (last, `"segment":"zha"`) starts **「最后说个八卦。」** (on-screen pink「咖啡渣时间」card stays)
  - every story ends **「锐评：…」**(≤16字, plain opinion — what it means / what to watch for; no forced puns/slang/analogies; no new facts) + `take` (≤20字 on screen)
  - outro exactly **「关注脆脆的AI早咖啡，明天早上八点见。」**
- Drop from narration: 现磨 / 趁热喝 / 下一口 / 今天这杯 / 咖啡见底 / 续杯 / 咖啡渣时间 / 今日一瓜 (banned list enforces).
- Story = fact → number → 锐评, 55–75 字; total narration 360–420 字 (≈80–90 s). Short sentences, 你 not 大家, no 新闻腔/过气网络词 (validator bans list in `assets/channel.json`). Write numbers as digits, `$300`→`300美元`, no brackets/emoji.
- `headline` ≤10字, `point` ≤20字, `video.cover_title` 2×≤9字, `cover_tags` 4–5.
- **Hashtags:** fixed `#AI` `#科技新闻` `#脆脆的AI早咖啡` + **1–3 per-episode topic tags** from today's stories (e.g. `#特斯拉` `#机器人` `#ChatGPT`); total 3–6. Last description line: **「每天早上8点，用大白话讲清楚昨天的AI大事」**. Voice locked in `assets/channel.json` — don't set it.
- **Media (optional, 0–3 stories):** only official visuals of that story (its official X post attachment, official page/press kit, or the source person's own screenshot). `media: {url, page, credit, type, start, end, fit}`; clips muted & auto-trimmed; `start` skips intro logos, `end` freezes on a meaningful frame. No stock/random/other-outlet images, never AI-generated images of real people/products. Nothing suitable → omit.

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
- X rate limit (429): wait 60 s. Out of budget: go with what's verified (min 4 stories) but keep diversity (≥1 everyday + ≥2 non-LLM) if at all possible.
- Machine lost: `git clone https://github.com/YUECHENCUI/crispy-ai-coffee.git && cd crispy-ai-coffee && ./setup.sh`.
