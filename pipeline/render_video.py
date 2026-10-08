"""Step: render the vertical 1080x1920 explainer video.

HTML scenes (templates/video.html) are driven frame-by-frame with window.renderAt(scene, t)
in headless Chromium (Playwright), screenshots are piped into ffmpeg, scenes are rendered
in parallel, concatenated, and muxed with the TTS voice + the fixed channel theme (pipeline/music.py).
Subtitles are drawn inside the HTML (burned in); an .srt is also exported.
"""
import json, math, subprocess, os, shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from .common import ROOT, TEMPLATES, ASSETS, CATEGORIES, out_dir, load_brief, ffprobe_duration, channel, video_name
from .tts import LEAD, COVER
from . import music

ZH_NUM = "零一二三四五六七八九十"

FPS = 30
W, H = 1080, 1920


def _domain(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc.replace("www.", "")


def out_dir_of(b):
    return out_dir(b["issue_date"])


def _take_at(sc, tl):
    """When the 脆脆锐评 sticker pops: the spoken '锐评' cue, else the cue matching take_from, else 65 %."""
    import re
    nz = lambda x: re.sub(r"[\s，。！？；：、,.!?;:“”\"'《》—]", "", x)
    for c in tl["cues"]:
        if nz(c["text"]).startswith("锐评"): return c["start"]
    tf = nz(sc.get("take_from", ""))
    for c in tl["cues"]:
        ct = nz(c["text"])
        if tf and ct and (ct.startswith(tf) or tf.startswith(ct)): return max(0, c["start"] - 0.15)
    return round(tl["duration"] * 0.65, 2)


def build_data(b, timeline):
    items = b["_items_by_id"]
    mf = out_dir_of(b) / "video" / "media_manifest.json"
    media = {}
    if mf.exists():
        for k, m in json.loads(mf.read_text("utf-8")).items():
            if b["video"]["scenes"][int(k)].get("media"):   # brief still asks for it
                media[k] = {"kind": m["kind"], "fit": m["fit"], "credit": m["credit"],
                            "src": Path(m["file"]).as_uri(), "frames": Path(m["frames_dir"]).as_uri() if m.get("frames_dir") else "",
                            "n_frames": m.get("n_frames", 0)}
    scenes, n = [], 0
    stories = [s for s in b["video"]["scenes"] if s["type"] == "story"]
    for sc, tl in zip(b["video"]["scenes"], timeline["scenes"]):
        d = {"type": sc["type"], "duration": tl["duration"], "cues": tl["cues"], "start": tl["start"]}
        if sc["type"] == "outro":   # same grid maths as music.mix -> logo pops exactly on the jingle hit
            vend = tl["start"] + tl.get("lead", LEAD) + tl["voice_duration"]
            d["hit"] = round(math.ceil((vend + 0.08) / music.E8) * music.E8 - tl["start"], 3)
        if sc["type"] == "story":
            n += 1
            it = items[sc["item"]]; cat = CATEGORIES[it["category"]]
            ks = it.get("key_stat") or {}
            srcs = it["sources"]
            web = [x for x in srcs[1:] if "x.com" not in _domain(x["url"])]
            default_src = srcs[0]["label"] + (" · " + _domain(web[0]["url"]) if web else "")
            d.update({"n": n, "color": cat["color"], "cat_zh": cat["zh"], "cat_en": cat["en"],
                      "headline": sc.get("headline", it["title"]), "point": sc.get("point", ""),
                      "stat_value": sc.get("stat_value", ks.get("value", "")),
                      "stat_label": sc.get("stat_label", ks.get("label", "")),
                      "source": sc.get("source", default_src),
                      "take": sc.get("take", ""), "segment": sc.get("segment", ""),
                      "take_at": _take_at(sc, tl), "media": media.get(str(len(scenes)))})
        scenes.append(d)
    rundown = []
    for sc in stories:
        it = items[sc["item"]]; cat = CATEGORIES[it["category"]]
        rundown.append({"h": sc.get("headline", it["title"]), "en": cat["en"], "color": cat["color"]})
    ch = channel(); v = b.get("video", {})
    return {"md": b["_md"], "year": str(b["_date"].year), "weekday": b["_weekday"], "weekday_en": b["_weekday_en"],
            "issue_no": b["_issue_no"], "lede": v.get("lede", b["lede"]),
            "n_stories": len(stories), "n_zh": ZH_NUM[len(stories)] if len(stories) <= 10 else str(len(stories)),
            "rundown": rundown, "scenes": scenes, "channel": ch,
            "cover": timeline.get("cover", COVER),
            "cover_title": v.get("cover_title", [b["headline"]]), "cover_tags": v.get("cover_tags", [r["h"] for r in rundown])}


def build_html(data, dest: Path):
    html = (TEMPLATES / "video.html").read_text("utf-8")
    html = html.replace('href="brand.css"', f'href="{(TEMPLATES / "brand.css").as_uri()}"')
    html = html.replace('src="../assets/', f'src="{ASSETS.as_uri()}/')
    html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    dest.write_text(html, "utf-8")
    return dest


def _render_scene(args):
    html_path, i, duration, seg_path = args
    from playwright.sync_api import sync_playwright
    nframes = int(round(duration * FPS))
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS),
                           "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-r", str(FPS), "-video_track_timescale", "30000", str(seg_path)],
                          stdin=subprocess.PIPE)
    warns = []
    with sync_playwright() as p:
        br = p.chromium.launch(args=["--font-render-hinting=none", "--disable-gpu"])
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto(Path(html_path).as_uri())
        pg.evaluate("document.fonts.ready.then(()=>1)")
        for f in range(nframes):
            t = f / FPS
            pg.evaluate(f"renderAt({i}, {t:.5f})")
            pg.evaluate("window.mediaWait()")   # wait for the media frame <img> to decode
            if f == int(min(nframes - 1, 3.0 * FPS)):
                warns += pg.evaluate("qa()")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=93))
        br.close()
    ff.stdin.close(); ff.wait()
    if ff.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for scene {i}")
    return i, nframes, sorted(set(warns))


def build_audio(vd: Path, timeline, bgm: Path | None, out: Path):
    """Legacy voice-only (+ optional external BGM) track; used with --no-music."""
    ad = vd / "audio"
    inputs, filt = [], []
    for k, s in enumerate(timeline["scenes"]):
        inputs += ["-i", str(ad / s["audio"])]
        ld = int(s.get("lead", LEAD) * 1000)
        filt.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ld}|{ld},"
                    f"apad,atrim=0:{s['duration']:.3f},asetpts=N/SR/TB[a{k}]")
    n = len(timeline["scenes"])
    filt.append("".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[voice]")
    last = "[voice]"
    if bgm and bgm.exists():
        inputs += ["-stream_loop", "-1", "-i", str(bgm)]
        filt.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.10,atrim=0:{timeline['total']:.3f}[bg]")
        filt.append(f"[voice][bg]amix=inputs=2:duration=first:normalize=0[mix]"); last = "[mix]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", last,
           "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True)


def write_srt(timeline, path: Path):
    def ts(x):
        ms = int(round(x * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    lines, k = [], 1
    for s in timeline["scenes"]:
        for c in s["cues"]:
            lines += [str(k), f"{ts(s['start'] + c['start'])} --> {ts(s['start'] + c['end'])}", c["text"], ""]; k += 1
    path.write_text("\n".join(lines), "utf-8")


def run(date, workers=4, bgm=None, only=None, use_music=True):
    b = load_brief(date)
    od = out_dir(date); vd = od / "video"; seg = vd / "segments"; seg.mkdir(parents=True, exist_ok=True)
    tl_path = vd / "timeline.json"
    if not tl_path.exists():
        raise SystemExit("[x] timeline.json missing — run the tts step first")
    timeline = json.loads(tl_path.read_text("utf-8"))
    data = build_data(b, timeline)
    html = build_html(data, vd / "video.html")
    jobs = [(str(html), i, s["duration"], seg / f"scene_{i:02d}.mp4") for i, s in enumerate(data["scenes"])
            if only is None or i in only]
    qa_path = vd / "layout_qa.json"
    report = json.loads(qa_path.read_text("utf-8")) if (only is not None and qa_path.exists()) else {}
    report = {int(k): v for k, v in report.items()}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, nf, warns in ex.map(_render_scene, jobs):
            report[i] = warns
            print(f"  scene {i:02d}: {nf} frames" + (f"  ⚠ {warns}" if warns else ""))
    qa_path.write_text(json.dumps(dict(sorted(report.items())), ensure_ascii=False, indent=1), "utf-8")
    # concat video segments
    lst = vd / "segments.txt"
    lst.write_text("".join(f"file '{seg / f'scene_{i:02d}.mp4'}'\n" for i in range(len(data["scenes"]))), "utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(vd / "video_noaudio.mp4")], check=True)
    if use_music and not bgm:
        music.mix(vd, timeline, vd / "mix.m4a")
    else:
        build_audio(vd, timeline, Path(bgm) if bgm else None, vd / "mix.m4a")
    final = od / video_name(date)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vd / "video_noaudio.mp4"), "-i", str(vd / "mix.m4a"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart",
                    str(final)], check=True)
    write_srt(timeline, od / video_name(date).replace(".mp4", ".srt"))
    print(f"  -> {final}  ({ffprobe_duration(final):.2f}s)")
    return final


def stills(date, at=3.0, dest=None):
    """Quick design preview: one PNG per scene at time `at` (no video encode)."""
    from playwright.sync_api import sync_playwright
    b = load_brief(date); vd = out_dir(date) / "video"
    timeline = json.loads((vd / "timeline.json").read_text("utf-8"))
    data = build_data(b, timeline); html = build_html(data, vd / "video.html")
    dest = Path(dest or vd / "stills"); dest.mkdir(parents=True, exist_ok=True)
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={"width": W, "height": H})
        pg.goto(html.as_uri()); pg.evaluate("document.fonts.ready.then(()=>1)")
        for i, s in enumerate(data["scenes"]):
            t = min(at if s["type"] != "title" else data["cover"] + 4.5, s["duration"] - 0.5)
            pg.evaluate(f"renderAt({i}, {t})"); pg.evaluate("window.mediaWait()")
            f = dest / f"still_{i:02d}.png"; pg.screenshot(path=str(f)); out.append(f)
            w = pg.evaluate("qa()")
            print(f"  still {i:02d} t={t}" + (f" ⚠ {w}" if w else ""))
        br.close()
    return out
