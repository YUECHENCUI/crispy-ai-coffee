# 脆脆的AI早咖啡 · CRISPY AI COFFEE

每天早上 8 点（Asia/Shanghai）一条 **~85 秒的中文 AI 新闻竖版短视频**（微信视频号 1080×1920）：
主持人「脆脆」用大白话讲清 5 条昨天的 AI 大事，每条加一句「锐评」。
本仓库是把它**全自动生产出来**的流水线：X 上采集 → 核实 → 写 `brief.json` → **一条命令**出视频、封面、文案、QA。

> 只生成文件，**不会发布**到任何平台。
> 每日由 agent 执行的精简流程见 **[`SKILL.md`](SKILL.md)**；人设与口播规范见 **[`assets/persona.md`](assets/persona.md)**。

## 产出（每期 `output/YYYY-MM-DD/`，日期 = 发布当天早上）
| 文件 | 说明 |
|---|---|
| `crispy-ai-coffee-YYYY-MM-DD.mp4` / `.srt` | 1080×1920 H.264/AAC，75–90 s，−14 LUFS，烧录字幕 |
| `sph/cover_3x4_1080x1440.png` | 视频号封面（固定模板，见下） |
| `sph/cover_9x16_1080x1920.png` | 同一画面 = 视频第一帧 |
| `sph/caption.txt` | 短标题 / 1–3 行描述 / 3–6 个话题 |
| `sph/sources.txt` | 每条新闻的来源链接（自查 / 置顶评论） |
| `qa/contact_sheet.png` | 一张图看全片关键帧（封面、片头、每条锐评时刻、片尾、3:4 封面） |
| `media/` | 本期用到的官方图片/视频（来源记录在 `video/media_manifest.json`） |

## 安装（全新 Debian/Ubuntu）
```bash
git clone https://github.com/YUECHENCUI/crispy-ai-coffee.git
cd crispy-ai-coffee && ./setup.sh
```
`setup.sh` 会装：`ffmpeg`、`fonts-noto-cjk`（思源黑体/宋体）、从 google/fonts 下载 Inter Tight / JetBrains Mono / Instrument Serif（SIL OFL）、Python venv + `requirements.txt`（playwright、edge-tts、numpy/scipy、jinja2、pillow、jsonschema）、Playwright Chromium，并自检字体。需要外网（edge-tts 在线合成语音）。

## 用法
```bash
D=$(TZ=Asia/Shanghai date +%F)
.venv/bin/python run.py --init --date $D      # 生成 output/$D/brief.json 模板
# …按 SKILL.md 采集、核实、填写 brief.json …
.venv/bin/python run.py --date $D             # validate → tts → media → video → sphkit → qa，打印 PASS/FAIL + 文件路径
```
- 结果缓存在 `output/$D/.cache/`：改了哪一步的输入就只重跑哪一步；`--force [step]` 强制重跑；`--verbose` 显示完整日志（默认写到 `output/$D/run.log`）。
- 其他：`--steps stills`（每场景一张 PNG 快速看版式）、`--steps samples`（声线试听）、`--with-article`（可选的公众号图文，默认关闭）、`--variant NAME`（写到 `output/$D/NAME/` 做对比版）。
- `brief.json` 结构：`schema/brief.schema.json`（validate 步骤会按 schema + 人设规则检查），模板 `templates/brief.example.json`，完整示例 `examples/2026-10-09.brief.json`。

## 定时任务
每天 **07:30 Asia/Shanghai 启动，08:00 前交付**：agent 照 [`SKILL.md`](SKILL.md) 执行（X 采集 ≤25 次调用 → WebSearch 核实 → 写 brief → `run.py` → 看 contact sheet → 报告 4 个交付文件路径）。文件夹按**发布当天早上的日期**命名，内容覆盖前一天 00:00 到当天 07:30。

## 设计（已定稿）
- **人设「脆脆」**（`assets/persona.md`，2026-10-11 起）：优先把事讲清楚。固定开场「早上好，我是脆脆，欢迎收看脆脆的AI早咖啡。」、转场「下一条。」、八卦「最后说个八卦。」、每条「锐评：…」（大白话，不硬梗）、收尾「关注脆脆的AI早咖啡，明天早上八点见。」。咖啡梗只留在频道名和画面视觉里，口播正文不用。
- **声音（锁定）**：`zh-CN-YunxiNeural`，rate +14%，pitch +6Hz，写在 `assets/channel.json`；失败时重试 6 次再回退 `zh-CN-YunjianNeural` → `zh-CN-XiaoxiaoNeural`，QA 把回退判为失败。
- **视觉**：深色编辑风（墨黑 #0B0D12 / 纸白 #F4F1EA / 日出橙 #FF5A1F），Noto Serif/Sans CJK + Inter Tight + JetBrains Mono；Logo = 咖啡杯里升起的日出（`assets/logo_coffee.svg`）。场景全部在 `templates/video.html`，Playwright 逐帧截图 → ffmpeg。
- **★ 固定封面模板**（2026-10-09 定稿）：视频前 1.8 s 的封面态 = 9:16 首帧，中间 y 240–1680 裁出 1080×1440 = 3:4 封面。版式：品牌行 + 「第NNN杯」→ 大日期 + 咖啡杯日出插画 → 星期 → 地平线 → 2 行宋体主标题（第 2 行橙）→ 编号话题胶囊 → 「一杯咖啡的时间，看懂昨天的 AI / EVERY MORNING 08:00」。每期只改 `video.cover_title`、`video.cover_tags`；`sphkit` 检查越界与首帧一致。
- **新闻卡**：分类标签、标题、计数动画数字、要点、来源、「脆脆锐评」贴纸（说到“锐评”时弹出）；八卦条为粉色「咖啡渣时间 · 今日一瓜」印章卡。
- **官方画面（可选）**：条目有官方演示视频/发布图/原帖截图时，卡片换成带框的素材版式（静音、按场景时长截取、`cover`/`contain` 裁切、右下角署名）。只用该新闻官方 X 原帖附件、官方网页/新闻稿或当事人原帖截图；找不到就不用；**绝不用 AI 生成的真人/真实产品图**。规则详见 `assets/persona.md` §8。
- **音乐**（`assets/music/`，原创）：`compose.py` 用 numpy/scipy 从零合成（120 BPM，C–Am–F–G，2 小节问答钩子 + “咖啡杯叮”），片头 sting / 4 小节无缝循环垫乐（人声下自动闪避到 −19.5 dB）/ 片尾 hit / 转场叮。总混音 −14 LUFS，真峰值 ≤ −1 dBTP。

## 目录
```
run.py              一条命令（缓存 + 精简汇总）
SKILL.md            agent 每日流程（精简版）
setup.sh            全新机器安装
pipeline/           common(配置/校验) tts media render_video music sph_kit qa voice_samples (+ 可选 render_article/render_cover)
templates/          video.html brand.css brief.example.json (+ 公众号可选模板 *.j2)
schema/             brief.schema.json
assets/             channel.json(频道/声线/固定口播) persona.md logo_coffee.svg music/
examples/           2026-10-09.brief.json（参考期）
output/             每期产出（不入库）
```

## 许可
- 代码：MIT（见 `LICENSE`）。
- `assets/music/*`（含 `compose.py` 生成的 WAV）与 Logo：本项目原创，按 **CC BY 4.0** 发布。
- 字体不随仓库分发，由 `setup.sh` 从官方来源安装（Noto CJK、Inter Tight、JetBrains Mono、Instrument Serif 均为 SIL OFL）。
- `examples/` 与每期 `brief.json` 中的新闻事实、引语和链接归原始来源所有；下载的官方图片/视频版权归原权利人，仅在 `output/` 本地使用，不入库。
- 语音由 Microsoft Edge 在线 TTS（edge-tts）合成，使用前请自行确认适用条款。
