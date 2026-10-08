"""Voice audition: opening + first story, mixed with the channel theme, one file per voice.

  .venv/bin/python run.py --date 2026-10-09 --variant v3 --steps samples
Outputs output/DATE[/variant]/voice_samples/<voice>.m4a (+ samples.json with rate/pitch/description)
Edit SAMPLE_VOICES to audition others (edge-tts only supports rate / pitch / volume, no speaking styles).
"""
import json, shutil
from pathlib import Path
from .common import out_dir, load_brief, ffprobe_duration
from . import tts, music

SAMPLE_VOICES = [
    # (voice, rate, pitch, one-line description)
    ("zh-CN-XiaoyiNeural", "+12%", "-2Hz", "女声 · 活泼年轻（MS 标签 Lively），最像嘴快又暖的咖啡师朋友；音高略压低一点，少点卡通感"),
    ("zh-CN-liaoning-XiaobeiNeural", "+16%", "+0Hz", "女声 · 东北话（MS 标签 Humorous），辨识度最高、最逗，但英文词/数字可能带口音、正式感最弱"),
    ("zh-CN-YunjianNeural", "+12%", "+0Hz", "男声 · 激情解说型（MS 标签 Passion，体育/小说），能量足、像兴奋的哥们，偏“喊”"),
]
YOUNG_MALE_VOICES = [
    ("zh-CN-YunxiaNeural", "+8%", "-12Hz", "男声 · 少年感最强（MS 标签 Cute），音高压低后更像二十出头的男生而不是小孩；轻快、有点皮"),
    ("zh-CN-YunxiNeural", "+14%", "+6Hz", "男声 · 阳光大男孩（MS 标签 Lively/Sunshine），提速提调后更年轻、更有劲，比 v1/v2 的讲解腔更活"),
]
TW_VOICES = [
    ("zh-TW-YunJheNeural", "+12%", "+2Hz", "男声 · 台湾腔年轻男生（MS 标签 Friendly/Positive），亲切、软萌一点、带俏皮感，台腔辨识度高"),
]
TAIL = 3.4   # room for the outro jingle at the end of the sample


def run(date, voices=SAMPLE_VOICES):
    b = load_brief(date); od = out_dir(date); sd = od / "voice_samples"; sd.mkdir(parents=True, exist_ok=True)
    scenes = [s for s in b["video"]["scenes"] if s["type"] == "title"][:1] + \
             [s for s in b["video"]["scenes"] if s["type"] == "story"][:1]
    meta = []
    for voice, rate, pitch, desc in voices:
        work = sd / "_work" / voice
        tts.run(date, scenes=scenes, vd=work, voice=voice, rate=rate, pitch=pitch)
        tl_path = work / "timeline.json"; tl = json.loads(tl_path.read_text("utf-8"))
        tl["scenes"][-1]["duration"] = round(tl["scenes"][-1]["duration"] + TAIL, 3); tl["total"] = round(tl["total"] + TAIL, 3)
        tl_path.write_text(json.dumps(tl, ensure_ascii=False, indent=1), "utf-8")
        name = f"{voice}.m4a"
        out = sd / name
        rep = music.mix(work, tl, out)
        used = {s.get("voice_used") for s in tl["scenes"]}
        if used != {voice}: print(f"  ⚠ {name}: some scenes fell back to {used - {voice}} — re-run this sample")
        meta.append({"file": name, "voice": voice, "rate": rate, "pitch": pitch, "description": desc,
                     "duration": round(ffprobe_duration(out), 2), "lufs": rep["final"]["I"], "true_peak": rep["final"]["TP"],
                     "voice_used": sorted(used)})
        print(f"  sample -> {out.name}  {meta[-1]['duration']}s  {rep['final']['I']} LUFS")
    # merge with earlier auditions (same file name -> replaced)
    prev = json.loads((sd / "samples.json").read_text("utf-8")) if (sd / "samples.json").exists() else []
    names = {m["file"] for m in meta}
    meta = [m for m in prev if m["file"] not in names] + meta
    (sd / "samples.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    wrap_mp4(od, sd, [m["file"] for m in meta])
    shutil.rmtree(sd / "_work", ignore_errors=True)
    return meta


def wrap_mp4(od, sd, files, cover=None):
    """Chat can't attach bare audio: wrap each sample as an MP4 over the static 3:4 cover (720x960)."""
    import subprocess
    cover = cover or (od / "sph" / "cover_3x4_1080x1440.png")
    for f in files:
        a = sd / f; out = a.with_suffix(".mp4")
        if not a.exists(): continue
        dur = ffprobe_duration(a)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "2", "-i", str(cover), "-i", str(a),
                        "-map", "0:v", "-map", "1:a", "-vf", "scale=720:960:flags=lanczos,format=yuv420p",
                        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20", "-r", "2",
                        "-c:a", "copy", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)], check=True)
