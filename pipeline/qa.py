"""Step: QA — durations, codecs, sample frames, font availability, layout warnings."""
import json, subprocess
from .common import out_dir, load_brief, ffprobe_duration, video_name
from .music import loudness


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _font_ok(family):
    r = subprocess.run(["fc-match", "-f", "%{family}", family], capture_output=True, text=True)
    return family.split(":")[0].lower() in r.stdout.lower(), r.stdout


def _contact_sheet(frames, out, cols=5, tw=324):
    """Tile labelled key frames into one PNG so a reviewer (or agent) checks a single image."""
    from PIL import Image, ImageDraw, ImageFont
    th = int(tw * 16 / 9); lab_h = 40; rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * (th + lab_h) + (rows + 1) * 8), (24, 26, 32))
    fp = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK SC:bold"], capture_output=True, text=True).stdout
    try: font = ImageFont.truetype(fp, 22)
    except Exception: font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for k, (lab, f) in enumerate(frames):
        r, c = divmod(k, cols); x = 8 + c * (tw + 8); y = 8 + r * (th + lab_h + 8)
        im = Image.open(f).convert("RGB"); im.thumbnail((tw, th), Image.LANCZOS)
        sheet.paste(im, (x + (tw - im.width) // 2, y + lab_h + (th - im.height) // 2))
        d.text((x + 4, y + 6), lab[:16], fill=(255, 179, 138), font=font)
    sheet.save(out, optimize=True)


def run(date):
    b = load_brief(date); od = out_dir(date); vd = od / "video"; qd = od / "qa"; qd.mkdir(exist_ok=True)
    mp4 = od / video_name(date)
    tl = json.loads((vd / "timeline.json").read_text("utf-8"))
    info = _probe(mp4)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    vdur, adur, fdur = float(v["duration"]), float(a["duration"]), float(info["format"]["duration"])
    problems = []
    if (v["width"], v["height"]) != (1080, 1920): problems.append(f"resolution {v['width']}x{v['height']}")
    if v["codec_name"] != "h264" or a["codec_name"] != "aac": problems.append("codec not h264/aac")
    if abs(vdur - adur) > 0.25: problems.append(f"audio/video length mismatch v={vdur:.2f} a={adur:.2f}")
    if abs(fdur - tl["total"]) > 0.3: problems.append(f"duration {fdur:.2f} != timeline {tl['total']:.2f}")
    if not 75 <= fdur <= 90: problems.append(f"duration {fdur:.1f}s outside 75–90s target")
    loud = loudness(mp4)
    if abs(loud["I"] + 14) > 1.0: problems.append(f"loudness {loud['I']} LUFS (target -14 ±1)")
    if loud["TP"] > -0.9: problems.append(f"true peak {loud['TP']} dBTP (want ≤ -1)")
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(mp4), "-af", "astats=measure_perchannel=none", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    peak_db = [float(l.split(":")[-1]) for l in r.splitlines() if "Peak level dB" in l]
    if peak_db and max(peak_db) >= -0.1: problems.append(f"audio sample peak {max(peak_db)} dBFS (clipping)")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-filter_complex",
                    "[0:a]showwavespic=s=1600x260:colors=#FF5A1F[w]", "-map", "[w]", "-frames:v", "1", str(qd / "audio_waveform.png")])
    # no 公众号 anywhere in the spoken script or the burned-in subtitles
    if any("公众号" in c["text"] for s_ in tl["scenes"] for c in s_["cues"]): problems.append("subtitles mention 公众号")
    for fam in ["Noto Sans CJK SC", "Noto Serif CJK SC", "Inter Tight", "JetBrains Mono"]:
        ok, got = _font_ok(fam)
        if not ok: problems.append(f"font missing: {fam} (fc-match → {got})")
    notes = []
    layout = json.loads((vd / "layout_qa.json").read_text("utf-8")) if (vd / "layout_qa.json").exists() else {}
    for k, w in layout.items():
        for x in w:
            (notes if x.startswith("note:") else problems).append(f"layout scene {k}: {x}")
    # locked voice, no fallback
    lv = tl["voice"]
    fb = sorted({s.get("voice_used") for s in tl["scenes"] if s.get("voice_used") and s.get("voice_used") != lv})
    if fb: problems.append(f"fallback voice used ({', '.join(fb)}) — re-run: run.py --date {date} --force tts")
    # media present where the brief asks for it
    mf = vd / "media_manifest.json"; man = json.loads(mf.read_text("utf-8")) if mf.exists() else {}
    for i, sc in enumerate(b["video"]["scenes"]):
        if sc.get("media") and str(i) not in man: problems.append(f"scene {i}: media requested but not rendered")
    kc = od / "sph" / "kit_check.json"
    if kc.exists(): problems += [f"sph: {w}" for w in json.loads(kc.read_text("utf-8")).get("warnings", [])]
    else: problems.append("sph kit missing (run sphkit)")
    # key frames -> ONE contact sheet (cover/first frame, title, every story at its 锐评 moment, outro, 3:4 cover)
    fd = qd / "frames"; fd.mkdir(exist_ok=True)
    shots = [("封面/首帧 t=0", 0.0)]
    for s in tl["scenes"]:
        if s["type"] == "title": shots.append(("片头", s["start"] + min(s["duration"] - 0.4, tl.get("cover", 1.8) + 4.5)))
        elif s["type"] == "story":
            ta = next((c["start"] for c in s["cues"] if c["text"].startswith("锐评")), s["duration"] * 0.7)
            sc = b["video"]["scenes"][s["index"]]
            lab = f"{s['index']:02d} {sc.get('headline', '')}" + (" ·媒体" if sc.get("media") else "")
            shots.append((lab, s["start"] + min(s["duration"] - 0.3, ta + 1.2)))
        else: shots.append(("片尾", s["start"] + min(s["duration"] - 0.4, s["duration"] * 0.55)))
    frames = []
    for k, (lab, t) in enumerate(shots):
        f = fd / f"{k:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", str(f)], check=True)
        frames.append((lab, f))
    c34 = od / "sph" / "cover_3x4_1080x1440.png"
    if c34.exists(): frames.append(("视频号封面 3:4", c34))
    sheet = qd / "contact_sheet.png"; _contact_sheet(frames, sheet)
    frames = [str(f.relative_to(od)) for _, f in frames]
    rep = {"video": str(mp4.name), "duration": round(fdur, 2), "video_stream": round(vdur, 2), "audio_stream": round(adur, 2),
           "timeline_total": tl["total"], "resolution": f"{v['width']}x{v['height']}", "fps": v["r_frame_rate"],
           "codecs": f"{v['codec_name']}/{a['codec_name']}", "size_mb": round(int(info['format']['size']) / 1e6, 1),
           "voice": tl["voice"], "rate": tl.get("rate"), "loudness": loud, "sample_peak_db": max(peak_db) if peak_db else None,
           "voices_used": sorted({s_.get("voice_used") for s_ in tl["scenes"]}), "media_scenes": sorted(int(k) for k in man),
           "contact_sheet": str(sheet.relative_to(od)), "frames": frames, "problems": problems, "notes": notes}
    (qd / "qa_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
    print(f"  duration {fdur:.2f}s (video {vdur:.2f} / audio {adur:.2f}), {rep['resolution']} {rep['codecs']}, {rep['size_mb']} MB")
    print(f"  loudness {loud['I']} LUFS, true peak {loud['TP']} dBTP, LRA {loud['LRA']}")
    print(f"  contact sheet -> {sheet}")
    print("  ✅ no problems found" if not problems else "  ⚠ PROBLEMS:\n   - " + "\n   - ".join(problems))
    return rep
