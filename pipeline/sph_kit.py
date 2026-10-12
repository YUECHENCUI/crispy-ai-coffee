"""Step: 视频号 posting kit — cover images + caption text (nothing is posted anywhere).

Outputs (output/DATE[/variant]/sph/):
  cover_9x16_1080x1920.png  = frame 0 of the video (title scene's cover state, renderAt(0, 0))
  cover_3x4_1080x1440.png   = the central 1080x1440 band (y 240–1680) of that frame; the cover layout
                              keeps every element inside this band, so the 3:4 crop loses nothing
  caption.txt               短标题 / 描述 (1–3 lines) / 话题 hashtags, ready to paste
  publish.json              machine-readable handoff for 视频号助手 scheduled publish
  sources.txt               per-story source links (for your own reference / a pinned comment)
  kit_check.json            sizes + how closely the cover matches the MP4's real first frame
"""
import json, subprocess
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from .common import out_dir, load_brief, channel, video_name, CATEGORIES, sanitize_short_title
from .render_video import build_data, build_html, W, H

CROP_TOP = 240   # 1920 - 1440 = 480 -> centred band


def _cn_len(s):
    return len(s)


def write_texts(date, *, covers_ok=None):
    """Write caption.txt + publish.json (+ sources.txt). No video/cover render.
    Safe to call after a full run to refresh titles without re-encoding."""
    b = load_brief(date); od = out_dir(date).resolve(); sd = (od / "sph"); sd.mkdir(parents=True, exist_ok=True)
    ch = channel()
    sph = b.get("sph") or {}
    raw_title = sph.get("title") or b["headline"]
    title = sanitize_short_title(raw_title)
    desc_lines = list(sph.get("description") or [b["lede"]])
    tags = sph.get("hashtags") or ch["default_hashtags"]
    tag_line = " ".join(tags)
    # caption.txt (human paste)
    cap = "\n".join([f"【短标题】{title}", "", "【描述】", *desc_lines, "", tag_line, ""])
    (sd / "caption.txt").write_text(cap, "utf-8")
    # description blob for 视频描述 = 【描述】 lines + blank line + hashtags
    description = "\n".join([*desc_lines, "", tag_line])
    video = (od / video_name(date)).resolve()
    cover = (sd / "cover_3x4_1080x1440.png").resolve()
    pub = {
        "video": str(video),
        "cover": str(cover),
        "short_title": title,
        "description": description,
        "publish_at": f"{b['issue_date']} 08:00",
    }
    (sd / "publish.json").write_text(json.dumps(pub, ensure_ascii=False, indent=2) + "\n", "utf-8")
    # sources
    lines = [f"{ch['name']} · 第{b['_issue_no']:03d}{ch['unit']} · {b['issue_date']} 信息来源", ""]
    for s in b["video"]["scenes"]:
        if s["type"] != "story": continue
        it = b["_items_by_id"][s["item"]]
        lines.append(f"▪ {it['title']}  [{CATEGORIES[it['category']]['zh']}]")
        lines += [f"  - {x['label']}: {x['url']}" for x in it["sources"]]
        lines.append("")
    (sd / "sources.txt").write_text("\n".join(lines), "utf-8")
    warns = list(covers_ok or [])
    if raw_title.strip() != title:
        warns.append(f"短标题 sanitized {raw_title!r} → {title!r}")
    if not 1 <= _cn_len(title) <= 16:
        warns.append(f"短标题 {_cn_len(title)} chars — 视频号 short titles must be ≤16")
    if not 3 <= len(tags) <= 6:
        warns.append(f"{len(tags)} hashtags (want 3–6)")
    chk_path = sd / "kit_check.json"
    prev = json.loads(chk_path.read_text("utf-8")) if chk_path.exists() else {}
    cover_warns = [w for w in prev.get("warnings", [])
                   if any(k in w.lower() for k in ("cover", "3:4", "frame"))]
    chk = {**{k: v for k, v in prev.items() if k not in ("warnings", "short_title", "title_len", "n_hashtags", "publish_json")},
           "short_title": title, "title_len": _cn_len(title), "n_hashtags": len(tags),
           "publish_json": "publish.json", "warnings": cover_warns + warns}
    chk_path.write_text(json.dumps(chk, ensure_ascii=False, indent=1), "utf-8")
    print(f"  caption+publish -> {sd / 'publish.json'}  short_title={title!r}"
          + ("".join(f"\n  ⚠ {w}" for w in warns) if warns else ""))
    return pub


def run(date):
    b = load_brief(date); od = out_dir(date); vd = od / "video"; sd = od / "sph"; sd.mkdir(parents=True, exist_ok=True)
    timeline = json.loads((vd / "timeline.json").read_text("utf-8"))
    data = build_data(b, timeline); html = build_html(data, vd / "video.html")
    from playwright.sync_api import sync_playwright
    c916 = sd / "cover_9x16_1080x1920.png"
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--font-render-hinting=none", "--disable-gpu"])
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto(html.as_uri()); pg.evaluate("document.fonts.ready.then(()=>1)")
        pg.evaluate("renderAt(0, 0)")
        pg.screenshot(path=str(c916))
        outside = pg.evaluate(f"""[...document.querySelectorAll('.cv *')].filter(e => {{
            const r = e.getBoundingClientRect(); return r.width && getComputedStyle(e).opacity !== '0' &&
            !e.closest('.glow') && !e.classList.contains('glow') && (r.top < {CROP_TOP} || r.bottom > {CROP_TOP + 1440} || r.right > 1080 || r.left < 0);
        }}).map(e => (e.className.baseVal ?? e.className) + '@' + Math.round(e.getBoundingClientRect().top) + '-' + Math.round(e.getBoundingClientRect().bottom))""")
        br.close()
    im = Image.open(c916).convert("RGB")
    c34 = sd / "cover_3x4_1080x1440.png"
    im.crop((0, CROP_TOP, 1080, CROP_TOP + 1440)).save(c34, optimize=True)
    first = None; mp4 = od / video_name(date)
    if mp4.exists():
        ff = vd / "first_frame.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-frames:v", "1", str(ff)], check=True)
        diff = ImageChops.difference(Image.open(ff).convert("RGB"), im)
        first = round(sum(ImageStat.Stat(diff).mean) / 3, 2)
    cover_warns = []
    if outside: cover_warns.append(f"cover elements outside the 3:4 band: {outside}")
    if first is not None and first > 4: cover_warns.append(f"cover differs from MP4 first frame (mean abs diff {first})")
    # seed kit_check with cover metrics before write_texts merges
    (sd / "kit_check.json").write_text(json.dumps({
        "cover_9x16": c916.name, "cover_3x4": c34.name,
        "sizes": {c916.name: list(Image.open(c916).size), c34.name: list(Image.open(c34).size)},
        "first_frame_mean_abs_diff": first, "warnings": cover_warns,
    }, ensure_ascii=False, indent=1), "utf-8")
    pub = write_texts(date)
    print(f"  视频号 kit -> {sd}  (first-frame diff {first})")
    return {"covers": {"9x16": c916.name, "3x4": c34.name, "first_frame_diff": first}, "publish": pub}
