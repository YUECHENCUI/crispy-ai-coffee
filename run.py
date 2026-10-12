#!/usr/bin/env python3
"""脆脆的AI早咖啡 — one-command daily pipeline (视频号 video).

  .venv/bin/python run.py --date 2026-10-10          # validate → tts → media → video → sphkit → qa, compact summary
  .venv/bin/python run.py --init --date 2026-10-10   # create output/DATE/brief.json from templates/brief.example.json
  options: --force [step,...]  ignore cache (all steps, or the listed ones)   --verbose  stream full logs
           --steps a,b         run only these steps (also: stills, samples, samples_young_male, samples_tw, publish, article, cover, preview)
           --with-article      also build the optional 公众号 article/cover/preview      --variant v2  use output/DATE/v2/

--date = PUBLISH morning (Asia/Shanghai); the episode covers the previous day. Writing brief.json is the agent's job (SKILL.md).
Steps are cached in output/DATE/.cache/state.json: a rerun skips any step whose inputs did not change.
"""
import argparse, contextlib, datetime, hashlib, io, json, sys, time, traceback
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from pipeline import common  # noqa: E402

DEFAULT = ["validate", "tts", "media", "video", "sphkit", "qa"]
ARTICLE = ["article", "cover", "preview"]
EXTRA = ["stills", "samples", "samples_young_male", "samples_tw", "publish"]
CACHED = {"tts", "media", "video", "sphkit"}


def _h(*parts):
    m = hashlib.sha256()
    for p in parts:
        if isinstance(p, Path):
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file() and "__pycache__" not in f.parts: m.update(f.name.encode()); m.update(f.read_bytes())
            elif p.exists(): m.update(p.read_bytes())
            else: m.update(b"<missing>")
        else:
            m.update(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode())
    return m.hexdigest()[:16]


def _key(step, date, od):
    b = json.loads((od / "brief.json").read_text("utf-8")); vd = od / "video"; sc = b["video"]["scenes"]
    code = ROOT / "pipeline"
    if step == "tts":
        from pipeline import tts
        return _h([s["narration"] for s in sc], tts.locked_voice(b), code / "tts.py")
    if step == "media":
        return _h([s.get("media") for s in sc], vd / "timeline.json", code / "media.py")
    if step == "video":
        return _h({k: v for k, v in b.items() if k != "sph"}, vd / "timeline.json", vd / "media_manifest.json",
                  ROOT / "templates", ROOT / "assets", code / "render_video.py", code / "music.py")
    if step == "sphkit":
        return _h(b, vd / "timeline.json", ROOT / "templates" / "video.html", code / "sph_kit.py",
                  str((od / common.video_name(date)).stat().st_mtime) if (od / common.video_name(date)).exists() else "")


def _done(step, date, od):
    vd = od / "video"
    return {"tts": vd / "timeline.json", "media": vd / "media_manifest.json", "video": od / common.video_name(date),
            "sphkit": od / "sph" / "caption.txt"}[step].exists()


def _run_step(s, a):
    from pipeline import tts, media, render_video, sph_kit, qa, render_article, render_cover, voice_samples
    if s == "validate":
        errs = common.validate_brief(common.load_brief(a.date))
        if errs: raise SystemExit("brief.json problems:\n - " + "\n - ".join(errs))
    elif s == "tts": tts.run(a.date)
    elif s == "media": media.run(a.date)
    elif s == "video": render_video.run(a.date, workers=a.workers, bgm=a.bgm, use_music=not a.no_music)
    elif s == "sphkit": sph_kit.run(a.date)
    elif s == "publish": sph_kit.write_texts(a.date)  # caption+publish.json only, no re-render
    elif s == "qa": return qa.run(a.date)
    elif s == "article": render_article.run(a.date)
    elif s == "cover": render_cover.run(a.date)
    elif s == "preview": render_article.preview(a.date)
    elif s == "stills": render_video.stills(a.date)
    elif s == "samples": voice_samples.run(a.date)
    elif s == "samples_young_male": voice_samples.run(a.date, voice_samples.YOUNG_MALE_VOICES)
    elif s == "samples_tw": voice_samples.run(a.date, voice_samples.TW_VOICES)
    else: raise SystemExit(f"unknown step {s}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat())
    ap.add_argument("--steps", default=None)
    ap.add_argument("--with-article", action="store_true")
    ap.add_argument("--variant", default=None)
    ap.add_argument("--force", nargs="?", const="all", default=None, help="ignore cache: 'all' or comma list of steps")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--bgm", default=None, help="external music (verified CC0/licensed only)")
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args()
    common.set_variant(a.variant)
    od = common.out_dir(a.date)
    if a.init:
        od.mkdir(parents=True, exist_ok=True); (od / "raw").mkdir(exist_ok=True)
        dst = od / "brief.json"
        if dst.exists(): sys.exit(f"[x] {dst} already exists")
        ex = json.loads((ROOT / "templates" / "brief.example.json").read_text("utf-8"))
        ex["issue_date"] = a.date
        d = datetime.date.fromisoformat(a.date)
        ex["coverage"] = {"from": f"{d - datetime.timedelta(days=1)} 00:00", "to": f"{d} 07:30", "tz": "Asia/Shanghai"}
        dst.write_text(json.dumps(ex, ensure_ascii=False, indent=2), "utf-8")
        print(f"created {dst}"); return
    if not (od / "brief.json").exists(): sys.exit(f"[x] {od / 'brief.json'} missing — run --init and fill it in")
    steps = [s.strip() for s in a.steps.split(",") if s.strip()] if a.steps else list(DEFAULT)
    if a.with_article and not a.steps: steps = steps[:-1] + ARTICLE + steps[-1:]
    force = set(DEFAULT + ARTICLE + EXTRA) if a.force == "all" else set((a.force or "").split(","))
    cache_f = od / ".cache" / "state.json"; cache_f.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_f.read_text("utf-8")) if cache_f.exists() else {}
    log_f = od / "run.log"; log = open(log_f, "a", encoding="utf-8")
    log.write(f"\n===== {datetime.datetime.now().isoformat(timespec='seconds')} {' '.join(sys.argv[1:])}\n"); log.flush()
    t0 = time.time(); status = []; rep = None
    for s in steps:
        ts = time.time()
        if s in CACHED and s not in force and _done(s, a.date, od):
            try:
                k = _key(s, a.date, od)
                if cache.get(s) == k: status.append(f"{s}·cached"); continue
            except Exception: pass
        buf = log if not a.verbose else sys.stdout
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                print(f"▶ {s}"); out = _run_step(s, a)
            if s == "qa": rep = out
        except BaseException as e:  # noqa: BLE001
            log.write(traceback.format_exc()); log.flush()
            msg = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"
            json.dump(cache, open(cache_f, "w"), indent=1)
            tail = log_f.read_text("utf-8").splitlines()[-25:]
            print(f"❌ FAIL at step '{s}' ({time.time() - ts:.0f}s)\n{msg}\n--- last log lines ({log_f}) ---\n" + "\n".join(tail))
            sys.exit(1)
        if s in CACHED:
            try: cache[s] = _key(s, a.date, od)
            except Exception: pass
            if s == "tts":   # never cache a TTS run that needed the fallback voice
                tl = json.loads((od / "video" / "timeline.json").read_text("utf-8"))
                if any(x.get("voice_used") != tl["voice"] for x in tl["scenes"]): cache.pop("tts", None)
            for d in DEFAULT[DEFAULT.index(s) + 1:]:
                if d in CACHED and d not in steps: cache.pop(d, None)
        status.append(f"{s}✓{time.time() - ts:.0f}s")
    json.dump(cache, open(cache_f, "w"), indent=1)
    rel = lambda p: str(Path(p).relative_to(ROOT)) if str(p).startswith(str(ROOT)) else str(p)
    if rep is None:
        print(f"✅ done ({time.time() - t0:.0f}s): " + "  ".join(status) + f"\n   folder: {rel(od)}"); return
    ok = not rep["problems"]
    b = common.load_brief(a.date)
    print(f"{'✅ PASS' if ok else '❌ FAIL'}  {a.date} 第{b['_issue_no']:03d}杯 · {rep['duration']}s · {rep['loudness']['I']} LUFS / TP {rep['loudness']['TP']} · "
          f"voice {', '.join(rep['voices_used'])} · media scenes {rep['media_scenes'] or '-'}")
    for lab, p in [("MP4", od / common.video_name(a.date)), ("Cover 3:4", od / "sph/cover_3x4_1080x1440.png"),
                   ("Caption", od / "sph/caption.txt"), ("Sources", od / "sph/sources.txt"),
                   ("Contact sheet (view this ONE image)", od / rep["contact_sheet"])]:
        print(f"   {lab:<36} {rel(p)}")
    for p in rep["problems"]: print(f"   ✗ {p}")
    for n in rep.get("notes", []): print(f"   · {n}")
    print(f"   steps: {'  '.join(status)}  ({time.time() - t0:.0f}s, log {rel(log_f)})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
