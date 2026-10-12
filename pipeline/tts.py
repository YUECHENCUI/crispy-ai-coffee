"""Step: TTS. One edge-tts call per video scene -> mp3 + word boundaries.

Outputs (in output/DATE/video/):
  audio/scene_XX.mp3, audio/scene_XX.words.json, timeline.json
"""
import asyncio, json, re
from pathlib import Path
import edge_tts
# 2026-10: Microsoft returns 403 on the legacy speech.platform.bing.com websocket
# (rany2/edge-tts#490). Use the new api.msedgeservices.com host with the legacy token.
import edge_tts.communicate as _etc
from edge_tts.constants import TRUSTED_CLIENT_TOKEN as _ETT
_etc.WSS_URL = f"wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key={_ETT}"
from .common import out_dir, load_brief, ffprobe_duration, channel

GAP = 0.30          # silence (s) appended after each scene's voice
LEAD = 0.22         # silence before voice starts in each scene
COVER = 1.8         # title scene opens on a still "cover" state (= 视频号 9:16 first frame) while the sting plays
TITLE_LEAD = COVER + 0.4   # voice starts just after the sting's downbeat hit (2.0 s)
TRIM_PAD = 0.18     # keep this much after the last word boundary
OUTRO_TAIL = 3.7    # room after the last words for the outro jingle (pickup + hit + ring)


def scene_lead(kind):
    return TITLE_LEAD if kind == "title" else LEAD


def scene_tail(kind):
    return OUTRO_TAIL if kind == "outro" else GAP
FALLBACK_VOICE = "zh-CN-XiaoxiaoNeural"   # last resort if channel.json has no fallbacks
PRIMARY_TRIES = 6
FALLBACK_TRIES = 2


def locked_voice(b=None):
    """The channel voice (assets/channel.json "voice"), unless the brief sets video.voice_override."""
    cv = channel().get("voice") or {"name": "zh-CN-YunxiNeural", "rate": "+14%", "pitch": "+6Hz", "fallbacks": []}
    ov = ((b or {}).get("video") or {}).get("voice_override")
    v = dict(cv, **ov) if ov else dict(cv)
    bv = (b or {}).get("video") or {}
    if not ov and any(k in bv and bv[k] != v[k2] for k, k2 in (("voice", "name"), ("rate", "rate"), ("pitch", "pitch"))):
        print(f"  note: brief video.voice/rate/pitch ignored — voice is locked to {v['name']} {v['rate']} {v['pitch']} (channel.json)")
    v.setdefault("fallbacks", [{"name": FALLBACK_VOICE, "rate": "+10%", "pitch": "+0Hz"}])
    return v
PUNCT = "，。！？；：、,.!?;:“”\"'（）()《》·…—- "


async def _synth(text, voice, rate, mp3_path, pitch="+0Hz"):
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
    return words


def _norm(s):
    return "".join(ch for ch in s if ch not in PUNCT)


HARD = "，。！？；：—"
SOFT = "、"


def _map_words(text, words):
    """Locate each TTS word in the original text -> list of (start_idx, end_idx)."""
    spans, pos = [], 0
    for w in words:
        target = _norm(w["w"]).lower()
        i, k, st = pos, 0, None
        while i < len(text) and k < len(target):
            ch = text[i].lower()
            if ch in PUNCT:
                i += 1; continue
            if ch == target[k]:
                if st is None: st = i
                k += 1; i += 1
            else:
                break
        if k == len(target) and st is not None:
            spans.append((st, i)); pos = i
        else:  # could not match (TTS normalised text differently) -> approximate
            st = pos
            while st < len(text) and text[st] in PUNCT: st += 1
            en = min(len(text), st + max(1, len(target)))
            spans.append((st, en)); pos = en
    return spans


def vwidth(s):
    """Visual width: CJK = 1, latin/digits/space ≈ 0.55."""
    return sum(1 if ord(ch) > 0x2E80 else 0.55 for ch in s)


def align_cues(text, words, total, max_len=16):
    """Group word boundaries into subtitle cues.

    1) split into clauses at hard punctuation (，。！？；：)
    2) a clause wider than max_len is split at the word boundary that best balances
       the two halves (preferring a break after 、), recursively -> no tiny orphans.
    """
    spans = _map_words(text, words)
    clauses, cur = [], []
    for wi, (a, b) in enumerate(spans):
        cur.append(wi)
        if text[b:b + 1] in HARD or wi == len(spans) - 1:
            clauses.append(cur); cur = []

    def width(ids):
        return vwidth(text[spans[ids[0]][0]:spans[ids[-1]][1]])

    def split(ids):
        if len(ids) < 2 or width(ids) <= max_len:
            return [ids]
        best, best_k = None, None
        for k in range(1, len(ids)):
            l, r = width(ids[:k]), width(ids[k:])
            score = abs(l - r) - (2.5 if text[spans[ids[k - 1]][1]:spans[ids[k - 1]][1] + 1] in SOFT else 0)
            if best is None or score < best:
                best, best_k = score, k
        return split(ids[:best_k]) + split(ids[best_k:])

    out = []
    for cl in clauses:
        for ids in split(cl):
            a, b = spans[ids[0]][0], spans[ids[-1]][1]
            t = text[a:b].strip().strip("，。；：、—！？").strip()
            out.append({"text": t, "start": round(words[ids[0]]["t"], 3),
                        "end": round(words[ids[-1]]["t"] + words[ids[-1]]["d"], 3)})
    for i in range(len(out) - 1):
        out[i]["end"] = out[i + 1]["start"]
    if out:
        out[-1]["end"] = round(min(total, out[-1]["end"] + 0.4), 3)
    return out


def run(date, scenes=None, vd=None, voice=None, rate=None, pitch=None):
    """scenes/vd/voice/rate/pitch overrides are used by voice_samples.py (audition renders)."""
    b = load_brief(date)
    vd = Path(vd) if vd else out_dir(date) / "video"; ad = vd / "audio"; ad.mkdir(parents=True, exist_ok=True)
    lv = locked_voice(b)
    voice = voice or lv["name"]; rate = rate or lv["rate"]; pitch = pitch or lv["pitch"]
    plan = [(voice, rate, pitch)] * PRIMARY_TRIES + \
           [(f["name"], f.get("rate", "+10%"), f.get("pitch", "+0Hz")) for f in lv["fallbacks"] for _ in range(FALLBACK_TRIES)]
    scenes = scenes if scenes is not None else b["video"]["scenes"]
    timeline, t0 = [], 0.0
    for i, sc in enumerate(scenes):
        mp3 = ad / f"scene_{i:02d}.mp3"
        words = None
        # edge-tts is a network service: retry (some voices, e.g. zh-TW-YunJheNeural, intermittently return
        # NoAudioReceived), reject truncated audio, then fall back to a second voice (logged in voice_used + warning)
        n_chars = len(_norm(sc["narration"]))
        for attempt, (v, vr, vp) in enumerate(plan):
            try:
                words = asyncio.run(_synth(sc["narration"], v, vr, mp3, vp))
                if words and ffprobe_duration(mp3) >= 0.08 * n_chars: break
                print(f"  ! TTS attempt {attempt + 1} ({v}) returned truncated audio"); words = None
            except Exception as e:  # noqa: BLE001
                print(f"  ! TTS attempt {attempt + 1} ({v}) failed: {e}")
            import time; time.sleep(min(10, 2 + 2 * attempt))
        if not words:
            raise SystemExit(f"[x] TTS failed for scene {i} with the locked voice and all fallbacks — retry later")
        if words and v != voice:
            print(f"  ⚠ scene {i}: fell back to {v} — re-run tts later for a consistent voice")
        # edge-tts pads ~0.8 s of silence at the end of every mp3: cut it so scenes flow tightly
        vdur = min(ffprobe_duration(mp3), words[-1]["t"] + words[-1]["d"] + TRIM_PAD)
        lead = scene_lead(sc["type"])
        dur = round(lead + vdur + scene_tail(sc["type"]), 3)
        cues = align_cues(sc["narration"], words, vdur)
        for c in cues:
            c["start"] = round(c["start"] + lead, 3); c["end"] = round(c["end"] + lead, 3)
        (ad / f"scene_{i:02d}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), "utf-8")
        timeline.append({"index": i, "type": sc["type"], "item": sc.get("item"), "audio": str(mp3.name),
                         "start": round(t0, 3), "duration": dur, "lead": lead, "voice_used": v, "voice_duration": round(vdur, 3), "cues": cues})
        print(f"  scene {i:02d} {sc['type']:<6} voice {vdur:5.2f}s  scene {dur:5.2f}s  cues {len(cues)}")
        t0 += dur
    (vd / "timeline.json").write_text(json.dumps({"voice": voice, "rate": rate, "pitch": pitch, "total": round(t0, 3), "cover": COVER,
                                                   "scenes": timeline}, ensure_ascii=False, indent=1), "utf-8")
    print(f"  total video length ≈ {t0:.1f}s (voice {voice}, rate {rate})")
    return t0
