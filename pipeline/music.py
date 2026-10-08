"""Step (inside video): mix the TTS voice with the fixed channel theme (assets/music/).

  t=0            sting.wav (cup clink + hook + downbeat hit at 2.0 s) over the still cover
  t=2.0 →        bed_loop.wav looped on the 120-BPM grid, ducked under the voice
                 (envelope follower: ~40 ms attack, ~350 ms release, 250 ms hold, 30 ms look-ahead)
  story starts   sfx_clink.wav (the theme's cup clink) on every transition into a story = audio signature
  outro          bed stops on the first 8th-note after the last word, outro_hit.wav plays
  master         gain to -14 LUFS integrated, limiter at ≈ -1.5 dBFS, AAC 192 kbps

Levels are set relative to the voice loudness (measured with ffmpeg ebur128):
  sting ≈ voice -1 dB · bed in gaps ≈ voice -10 dB · bed under speech ≈ voice -19.5 dB · hit ≈ voice -0.5 dB
"""
import json, math, re, subprocess
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from .common import ASSETS

SR = 48000
E8 = 0.25                # 8th note @ 120 BPM
BED_START = 2.0          # sting downbeat
MUSIC = ASSETS / "music"
VOICE_LUFS = -16.0
STING_REL, BED_OPEN_REL, DUCK_DB, HIT_REL = -1.0, -10.0, -9.5, -0.5
CLINK_GAIN = 0.42                     # clink peaks ≈ -10.5 dBFS before mastering (voice peaks ≈ -4)
TARGET_LUFS, LIMIT = -14.0, 0.84      # 0.84 ≈ -1.5 dBFS sample peak -> true peak stays ≤ -1 dBTP


def _decode(path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)


def _stereo_wav(path) -> np.ndarray:
    sr, x = wavfile.read(path); assert sr == SR, path
    x = x.astype(np.float64) / (32768.0 if x.dtype == np.int16 else 1.0)
    return x if x.ndim == 2 else np.stack([x, x], 1)


def loudness(path) -> dict:
    """Integrated loudness / LRA / true peak via ffmpeg ebur128."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    summ = r.stderr[r.stderr.rfind("Summary:"):]
    g = lambda k: float(re.search(k + r":\s+(-?[\d.]+|-inf)", summ).group(1).replace("-inf", "-120"))
    return {"I": g("I"), "LRA": g("LRA"), "TP": g("Peak")}


def _write(path, x):
    wavfile.write(path, SR, x.astype(np.float32))


def _lufs_arr(x, tmp: Path):
    _write(tmp, x); return loudness(tmp)["I"]


def _db(x): return 10 ** (x / 20)


def duck_envelope(voice_mono, depth_db=DUCK_DB, hop=0.01, hold=0.25, attack=0.04, release=0.35, lookahead=0.03):
    n = int(hop * SR); m = len(voice_mono) // n + 1
    pad = np.zeros(m * n); pad[:len(voice_mono)] = voice_mono
    rms = np.sqrt((pad.reshape(m, n) ** 2).mean(1) + 1e-12); db = 20 * np.log10(rms)
    active = db > db.max() - 32
    h = int(hold / hop); act = active.copy()
    for k in np.flatnonzero(active): act[k:k + h] = True          # hold
    la = int(lookahead / hop); act = np.concatenate([act[la:], np.zeros(la, bool)]) | act  # look-ahead
    target = np.where(act, depth_db, 0.0); g = np.zeros(m); cur = 0.0
    a_c, r_c = math.exp(-hop / attack), math.exp(-hop / release)
    for k in range(m):
        c = a_c if target[k] < cur else r_c
        cur = c * cur + (1 - c) * target[k]; g[k] = cur
    t_hop = (np.arange(m) + 0.5) * n
    return _db(np.interp(np.arange(len(voice_mono)), t_hop, g))


def mix(vd: Path, timeline: dict, out: Path, lead_default=0.25, clink=True, outro_hit=True) -> dict:
    total = timeline["total"]; N = int(round(total * SR)); tmp = vd / "_tmp_loud.wav"
    # 1) voice track
    voice = np.zeros(N)
    for s in timeline["scenes"]:
        v = _decode(vd / "audio" / s["audio"])
        i0 = int(round((s["start"] + s.get("lead", lead_default)) * SR)); n = min(len(v), N - i0)
        voice[i0:i0 + n] += v[:n]
    vI = _lufs_arr(np.stack([voice, voice], 1), tmp)
    voice *= _db(VOICE_LUFS - vI)
    # 2) stems + their loudness
    sting, bed, hit = (_stereo_wav(MUSIC / f) for f in ("sting.wav", "bed_loop.wav", "outro_hit.wav"))
    L = {k: loudness(MUSIC / f)["I"] for k, f in (("sting", "sting.wav"), ("bed", "bed_loop.wav"), ("hit", "outro_hit.wav"))}
    g_sting = _db(VOICE_LUFS + STING_REL - L["sting"]); g_bed = _db(VOICE_LUFS + BED_OPEN_REL - L["bed"])
    g_hit = _db(VOICE_LUFS + HIT_REL - L["hit"])
    # 3) arrangement
    o = timeline["scenes"][-1]
    voice_end = o["start"] + o.get("lead", lead_default) + o["voice_duration"]
    hit_at = math.ceil((voice_end + 0.08) / E8) * E8
    music = np.zeros((N, 2))
    n = min(len(sting), N); music[:n] += sting[:n] * g_sting
    b0, b1 = int(BED_START * SR), min(N, int(hit_at * SR))
    reps = (b1 - b0) // len(bed) + 2
    bed_track = np.tile(bed, (reps, 1))[:b1 - b0] * g_bed
    fi, fo = int(0.02 * SR), int(0.06 * SR)
    bed_track[:fi] *= np.linspace(0, 1, fi)[:, None]; bed_track[-fo:] *= np.linspace(1, 0, fo)[:, None]
    music[b0:b1] += bed_track
    env = duck_envelope(voice)
    music *= env[:, None]
    if outro_hit:
        h0 = int(hit_at * SR); n = min(len(hit), N - h0); music[h0:h0 + n] += hit[:n] * g_hit
    clinks = []
    if clink and (MUSIC / "sfx_clink.wav").exists():
        ck = _stereo_wav(MUSIC / "sfx_clink.wav")
        for s in timeline["scenes"]:
            if s["type"] == "story":
                c0 = max(0, int((s["start"] - 0.04) * SR)); n = min(len(ck), N - c0)
                music[c0:c0 + n] += ck[:n] * CLINK_GAIN; clinks.append(round(s["start"] - 0.04, 2))
    mixed = np.stack([voice, voice], 1) + music
    fo = int(0.35 * SR); mixed[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    # 4) master: gain to target, limiter, AAC; one correction pass if the limiter shaved loudness
    mI = _lufs_arr(mixed, tmp); raw = vd / "mix_raw.wav"; _write(raw, mixed)
    gain = TARGET_LUFS - mI
    for _ in range(3):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
                        f"volume={gain:.2f}dB,alimiter=limit={LIMIT}:attack=4:release=60:level=0",
                        "-ar", str(SR), "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
        fin = loudness(out)
        if abs(fin["I"] - TARGET_LUFS) <= 0.3: break
        gain += TARGET_LUFS - fin["I"]
    tmp.unlink(missing_ok=True)
    rep = {"voice_lufs_raw": vI, "stem_lufs": L, "gains_db": {
               "sting": round(20 * math.log10(g_sting), 2), "bed_open": round(20 * math.log10(g_bed), 2),
               "bed_ducked": round(20 * math.log10(g_bed) + DUCK_DB, 2), "hit": round(20 * math.log10(g_hit), 2)},
           "rel_to_voice_db": {"sting": STING_REL, "bed_open": BED_OPEN_REL, "bed_under_voice": BED_OPEN_REL + DUCK_DB, "hit": HIT_REL},
           "hit_at": hit_at, "clinks_at": clinks, "voice_end": round(voice_end, 3), "master_gain_db": round(gain, 2), "final": fin}
    (vd / "mix_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
    print(f"  music mix: final {fin['I']:.1f} LUFS, TP {fin['TP']:.1f} dBTP, LRA {fin['LRA']:.1f}; bed under voice {BED_OPEN_REL + DUCK_DB:.1f} dB")
    return rep
