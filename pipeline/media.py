"""Step: optional per-story media (official image / short clip) -> output/DATE/media/ + frames for rendering.

brief.json  video.scenes[i].media = {
    "url":    direct file URL (image or mp4) taken from the story's OFFICIAL X post / official page / press kit,
    "page":   the post/page it came from (recorded as the source),
    "credit": short on-screen credit, e.g. "OpenAI @X 官方视频",
    "type":   "video" | "image"            (optional, guessed from the URL),
    "start":  seconds into the clip to start (optional, default 0),
    "end":    seconds into the clip to stop and HOLD that frame (optional; use it to freeze on a
              meaningful frame, e.g. the product name, instead of a blank end card),
    "fit":    "cover" (fill & crop, default for video) | "contain" (whole image + blurred backdrop, default for image)
}
Clips are rendered MUTED, trimmed to the scene length (last frame held if the clip is shorter).
Downloads are cached: an existing file in media/ is reused.
"""
import json, subprocess
from pathlib import Path
from urllib.parse import urlparse
from .common import out_dir, load_brief

FPS = 30
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")


def _kind(m):
    if m.get("type") in ("video", "image"): return m["type"]
    return "video" if urlparse(m["url"]).path.lower().endswith(VIDEO_EXT) else "image"


def _download(url, dest: Path):
    if dest.exists() and dest.stat().st_size > 1000: return
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(["curl", "-fsSL", "--retry", "3", "-A", UA, "-o", str(tmp), url], check=True)
    tmp.rename(dest)


def run(date):
    b = load_brief(date); od = out_dir(date); md = od / "media"; vd = od / "video"
    tl = json.loads((vd / "timeline.json").read_text("utf-8"))
    manifest = {}
    for i, (sc, ts) in enumerate(zip(b["video"]["scenes"], tl["scenes"])):
        m = sc.get("media")
        if not m: continue
        md.mkdir(parents=True, exist_ok=True)
        kind = _kind(m)
        ext = Path(urlparse(m["url"]).path).suffix.lower() or (".mp4" if kind == "video" else ".jpg")
        if kind == "image" and ext not in (".jpg", ".jpeg", ".png", ".webp"): ext = ".jpg"
        f = md / f"scene_{i:02d}{ext}"
        _download(m["url"], f)
        ent = {"kind": kind, "file": str(f), "credit": m.get("credit", ""), "page": m.get("page", ""), "url": m["url"],
               "fit": m.get("fit", "cover" if kind == "video" else "contain")}
        if kind == "video":
            fd = vd / "media_frames" / f"scene_{i:02d}"; fd.mkdir(parents=True, exist_ok=True)
            for old in fd.glob("*.jpg"): old.unlink()
            start = float(m.get("start", 0))
            dur = ts['duration'] if m.get("end") is None else max(0.1, min(ts['duration'], float(m["end"]) - start))
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(f), "-t", f"{dur:.2f}",
                            "-an", "-vf", f"fps={FPS},scale=960:-2:flags=lanczos", "-q:v", "3", str(fd / "%04d.jpg")], check=True)
            n = len(list(fd.glob("*.jpg")))
            if n == 0: raise SystemExit(f"[x] media for scene {i}: no frames extracted (start {start}s beyond clip?)")
            ent.update({"frames_dir": str(fd), "n_frames": n, "start": start, "end": m.get("end")})
        manifest[i] = ent
    (vd / "media_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    print(f"  media: {len(manifest)} scene(s) " + ", ".join(f"{k}:{v['kind']}" for k, v in manifest.items()))
    return manifest
