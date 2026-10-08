"""Step: 视频号 posting kit — cover images + caption text (nothing is posted anywhere).

Outputs (output/DATE[/variant]/sph/):
  cover_9x16_1080x1920.png  = frame 0 of the video (title scene's cover state, renderAt(0, 0))
  cover_3x4_1080x1440.png   = the central 1080x1440 band (y 240–1680) of that frame; the cover layout
                              keeps every element inside this band, so the 3:4 crop loses nothing
  caption.txt               短标题 / 描述 (1–3 lines) / 话题 hashtags, ready to paste
  sources.txt               per-story source links (for your own reference / a pinned comment)
  kit_check.json            sizes + how closely the cover matches the MP4's real first frame
"""
import json, subprocess
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from .common import out_dir, load_brief, channel, video_name, CATEGORIES
from .render_video import build_data, build_html, W, H

CROP_TOP = 240   # 1920 - 1440 = 480 -> centred band


def _cn_len(s):
    return len(s)


def run(date):
    b = load_brief(date); od = out_dir(date); vd = od / "video"; sd = od / "sph"; sd.mkdir(parents=True, exist_ok=True)
    ch = channel()
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
        # every visible cover element must sit inside the 3:4 band
        outside = pg.evaluate(f"""[...document.querySelectorAll('.cv *')].filter(e => {{
            const r = e.getBoundingClientRect(); return r.width && getComputedStyle(e).opacity !== '0' &&
            !e.closest('.glow') && !e.classList.contains('glow') && (r.top < {CROP_TOP} || r.bottom > {CROP_TOP + 1440} || r.right > 1080 || r.left < 0);
        }}).map(e => (e.className.baseVal ?? e.className) + '@' + Math.round(e.getBoundingClientRect().top) + '-' + Math.round(e.getBoundingClientRect().bottom))""")
        br.close()
    im = Image.open(c916).convert("RGB")
    c34 = sd / "cover_3x4_1080x1440.png"
    im.crop((0, CROP_TOP, 1080, CROP_TOP + 1440)).save(c34, optimize=True)
    # compare with the real first frame of the MP4 (if rendered)
    first = None; mp4 = od / video_name(date)
    if mp4.exists():
        ff = vd / "first_frame.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-frames:v", "1", str(ff)], check=True)
        diff = ImageChops.difference(Image.open(ff).convert("RGB"), im)
        first = round(sum(ImageStat.Stat(diff).mean) / 3, 2)
    # caption
    sph = b.get("sph") or {}
    title = sph.get("title") or b["headline"]
    desc = sph.get("description") or [b["lede"]]
    tags = sph.get("hashtags") or ch["default_hashtags"]
    cap = "\n".join([f"【短标题】{title}", "", "【描述】", *desc, "", " ".join(tags), ""])
    (sd / "caption.txt").write_text(cap, "utf-8")
    lines = [f"{ch['name']} · 第{b['_issue_no']:03d}{ch['unit']} · {b['issue_date']} 信息来源", ""]
    for s in b["video"]["scenes"]:
        if s["type"] != "story": continue
        it = b["_items_by_id"][s["item"]]
        lines.append(f"▪ {it['title']}  [{CATEGORIES[it['category']]['zh']}]")
        lines += [f"  - {x['label']}: {x['url']}" for x in it["sources"]]
        lines.append("")
    (sd / "sources.txt").write_text("\n".join(lines), "utf-8")
    warns = []
    if not 6 <= _cn_len(title) <= 16: warns.append(f"短标题 {_cn_len(title)} chars — 视频号 short titles are usually 6–16 chars")
    if not 3 <= len(tags) <= 6: warns.append(f"{len(tags)} hashtags (want 3–6)")
    if outside: warns.append(f"cover elements outside the 3:4 band: {outside}")
    if first is not None and first > 4: warns.append(f"cover differs from MP4 first frame (mean abs diff {first})")
    chk = {"cover_9x16": c916.name, "cover_3x4": c34.name, "sizes": {c916.name: Image.open(c916).size, c34.name: Image.open(c34).size},
           "first_frame_mean_abs_diff": first, "title_len": _cn_len(title), "n_hashtags": len(tags), "warnings": warns}
    (sd / "kit_check.json").write_text(json.dumps(chk, ensure_ascii=False, indent=1), "utf-8")
    print(f"  视频号 kit -> {sd}  (first-frame diff {first})" + ("".join(f"\n  ⚠ {w}" for w in warns) if warns else ""))
    return chk
