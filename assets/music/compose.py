#!/usr/bin/env python3
"""「脆脆的AI早咖啡」theme — original composition, synthesised from scratch with numpy.

No samples, no soundfonts, no third-party audio: every sound (mallet lead, plucked
chords, bass, kick, clap, hats, shaker, cup "clink", reverb) is generated below, so
the result is an original work that can be used commercially.

  120 BPM, C major, progression C–Am–F–G.  Hook (2 bars):
    call   : E5 G5 A5 G5 | E5 D5 C5——        (intro sting)
    answer : E5 G5 A5 C6 | B5 G5 C6——        (outro hit)

Outputs (48 kHz stereo 16-bit WAV, peak-normalised to -1 dBFS):
  sting.wav     3.0 s   cup clink + call phrase + downbeat hit      (episode intro)
  bed_loop.wav  8.0 s   4-bar seamless loop, lighter groove          (under the voice)
  outro_hit.wav 3.8 s   answer phrase + big C chord + clink + ring   (episode outro)
  theme_demo.wav        sting + 2×bed + outro, for listening
  sfx_clink.wav 0.9 s   the cup clink alone (played on every story transition)
Re-run:  .venv/bin/python assets/music/compose.py   (fixed random seed -> identical files)
"""
import numpy as np
from pathlib import Path
from scipy.signal import butter, sosfilt, lfilter, fftconvolve
from scipy.io import wavfile

SR = 48000
BPM = 120
BEAT = 60 / BPM          # 0.5 s
E8 = BEAT / 2            # 8th note 0.25 s
BAR = BEAT * 4           # 2.0 s
OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(20261009)


def midi(n):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    p, o = n[:-1], int(n[-1]); return 440 * 2 ** ((names[p] + 12 * (o + 1) - 69) / 12)


def tt(d): return np.arange(int(d * SR)) / SR
def bp(x, lo, hi, order=2): return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)
def hp(x, f, order=2): return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)
def lp(x, f, order=2): return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


# ---------------- instruments ----------------
def mallet(f, dur=0.9, vel=1.0):
    """Bright glock/marimba-like mallet: partials with fast decays."""
    t = tt(dur); s = np.zeros_like(t)
    for ratio, amp, dec in [(1, 1.0, 0.55), (2.0, 0.25, 0.3), (3.99, 0.18, 0.12), (8.9, 0.05, 0.05)]:
        s += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t / dec)
    return vel * s * np.minimum(1, t / 0.002)


def pluck(f, dur=0.5, vel=1.0, bright=0.6, decay=0.994):
    """Karplus–Strong plucked string (vectorised with lfilter)."""
    n = int(SR / f); L = int(dur * SR)
    x = np.zeros(L); x[:n] = lp(rng.uniform(-1, 1, n), 1500 + 6000 * bright)
    a = np.zeros(n + 2); a[0] = 1; a[n] = -0.5 * decay; a[n + 1] = -0.5 * decay
    return vel * lfilter([1], a, x) * np.minimum(1, np.linspace(1, 0, L) * 6)


def bass(f, dur=0.45, vel=1.0):
    t = tt(dur)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    return vel * np.tanh(1.6 * s * np.minimum(1, t / 0.006) * np.exp(-t / 0.28)) * 0.8


def kick(vel=1.0):
    t = tt(0.35); f = 46 + 120 * np.exp(-t * 32)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8.5)
    click = hp(rng.uniform(-1, 1, len(t)), 3000) * np.exp(-t * 400) * 0.3
    return vel * np.tanh(2.2 * s + click)


def clap(vel=1.0):
    t = tt(0.25); n = rng.uniform(-1, 1, len(t))
    env = sum(np.exp(-np.maximum(0, t - d) * 140) * (t >= d) for d in (0, 0.011, 0.022)) * 0.6 + np.exp(-t * 18) * 0.5
    return vel * bp(n, 900, 3200) * env


def hat(vel=1.0):
    t = tt(0.06); return vel * hp(rng.uniform(-1, 1, len(t)), 7500) * np.exp(-t * 70)


def shaker(vel=1.0):
    t = tt(0.08); return vel * bp(rng.uniform(-1, 1, len(t)), 4500, 11000) * np.minimum(1, t / 0.012) * np.exp(-t * 45)


def clink(vel=1.0):
    """Coffee-cup 'clink': short inharmonic ceramic partials — the 'crispy' signature."""
    t = tt(0.9); s = np.zeros_like(t)
    for f, amp, dec in [(2310, 1.0, 0.35), (3790, 0.6, 0.22), (5480, 0.45, 0.12), (8030, 0.25, 0.06)]:
        s += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / dec)
    return vel * s * np.minimum(1, t / 0.0008) * 0.5


def crash(vel=1.0):
    t = tt(1.6); return vel * hp(rng.uniform(-1, 1, len(t)), 5000) * np.exp(-t * 2.6) * 0.5


# ---------------- arrangement helpers ----------------
class Bus:
    def __init__(self, dur, wrap=False):
        self.L = int(round(dur * SR)); self.buf = np.zeros((self.L, 2)); self.wrap = wrap

    def add(self, t0, sig, gain=1.0, pan=0.0):
        i0 = int(round(t0 * SR))
        g = np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)]) * np.sqrt(2)
        st = sig[:, None] * g[None, :] * gain
        if self.wrap:   # tails wrap around -> perfectly seamless loop
            idx = (i0 + np.arange(len(sig))) % self.L; np.add.at(self.buf, idx, st)
        else:
            n = min(len(sig), self.L - i0)
            if n > 0: self.buf[i0:i0 + n] += st[:n]


def reverb(x, wet=0.16, size=1.1, wrap=False):
    t = tt(size); ir = rng.normal(0, 1, (len(t), 2)) * np.exp(-t / (size / 5))[:, None]
    ir = np.stack([lp(ir[:, 0], 6000), lp(ir[:, 1], 6000)], axis=1)
    ir /= np.sqrt((ir ** 2).sum(axis=0))
    out = np.zeros_like(x)
    for c in range(2):
        y = fftconvolve(x[:, c], ir[:, c])
        if wrap:
            yy = y[:len(x)].copy(); tail = y[len(x):]
            for k in range(0, len(tail), len(x)):
                seg = tail[k:k + len(x)]; yy[:len(seg)] += seg
            y = yy
        out[:, c] = y[:len(x)]
    return x + wet * out


CHORDS = {"C": ["C4", "E4", "G4"], "Am": ["A3", "C4", "E4"], "F": ["F3", "A3", "C4"], "G": ["G3", "B3", "D4"]}
ROOT = {"C": "C2", "Am": "A1", "F": "F2", "G": "G2"}
CALL = [("E5", 0), ("G5", 1), ("A5", 2), ("G5", 3), ("E5", 4), ("D5", 5), ("C5", 6)]
ANSWER = [("E5", 0), ("G5", 1), ("A5", 2), ("C6", 3), ("B5", 4), ("G5", 5)]


def groove(bus, t0, chord, light=False):
    """One bar of the bouncy groove starting at t0 (four-on-the-floor + off-beat chord stabs)."""
    for b in range(4):
        tb = t0 + b * BEAT
        bus.add(tb, kick(), 0.55 if light else 0.8)
        if b in (1, 3): bus.add(tb, clap(), 0.22 if light else 0.32, pan=0.05)
        bus.add(tb + E8, hat(), 0.16 if light else 0.22, pan=0.35)
        for s in range(4): bus.add(tb + s * E8 / 2, shaker(), 0.05 if light else 0.07, pan=-0.3)
        for k, n in enumerate(CHORDS[chord]):
            bus.add(tb + E8 + k * 0.004, pluck(midi(n), 0.32, bright=0.7), 0.13 if light else 0.17, pan=-0.25 + 0.25 * k)
    r = midi(ROOT[chord])
    for pos, mult in [(0, 1), (1.5, 2), (2, 1), (3.5, 1.5)]:
        bus.add(t0 + pos * BEAT, bass(r * mult, 0.42), 0.5 if light else 0.6)


def norm(x, peak_db=-1.0): return x / (np.abs(x).max() + 1e-9) * 10 ** (peak_db / 20)


def save(name, x):
    wavfile.write(OUT / name, SR, (np.clip(x, -1, 1) * 32767).astype(np.int16)); print("wrote", OUT / name, f"{len(x)/SR:.2f}s")


def main():
    # ---- sting: clink, call phrase over C, downbeat hit on bar 2 ----
    st = Bus(3.0)
    st.add(0.0, clink(), 0.9, pan=0.2)
    groove(st, 0.0, "C")
    for n, k in CALL:
        d = 0.9 if k < 6 else 1.6
        st.add(k * E8, mallet(midi(n), d), 0.75, pan=0.1)
        st.add(k * E8, mallet(midi(n) * 2, d * 0.6), 0.12, pan=-0.1)   # octave sparkle
    st.add(BAR, kick(), 0.9); st.add(BAR, crash(), 0.6); st.add(BAR, bass(midi("C2"), 0.9), 0.7)
    for k, n in enumerate(CHORDS["C"] + ["C5"]):
        st.add(BAR + k * 0.006, pluck(midi(n), 0.9, bright=0.8, decay=0.997), 0.22)
    sting = reverb(st.buf, wet=0.18)
    fade = np.ones(len(sting)); fade[-int(0.4 * SR):] = np.linspace(1, 0, int(0.4 * SR))
    sting = norm(sting * fade[:, None])

    # ---- bed loop: 4 bars C–Am–F–G, lighter, with a soft echo of the hook (the earworm) ----
    bd = Bus(4 * BAR, wrap=True)
    for i, ch in enumerate(["C", "Am", "F", "G"]): groove(bd, i * BAR, ch, light=True)
    for n, k in CALL[:4]: bd.add(k * E8, mallet(midi(n), 0.7), 0.22, pan=0.15)
    for n, k in [("G5", 0), ("A5", 1), ("C6", 2), ("B5", 4)]: bd.add(3 * BAR + k * E8, mallet(midi(n), 0.6), 0.14, pan=-0.15)
    bed = reverb(bd.buf, wet=0.14, wrap=True)
    n = len(bed); tiled = np.tile(bed, (3, 1))   # filter circularly so the loop seam stays seamless
    bed = norm(np.stack([lp(tiled[:, 0], 9000), lp(tiled[:, 1], 9000)], axis=1)[n:2 * n])

    # ---- outro: 1.5 s pickup + answer phrase, big C hit + clink + ring ----
    ou = Bus(3.8)
    for b in range(3):
        tb = b * BEAT; ou.add(tb, kick(), 0.75); ou.add(tb + E8, hat(), 0.2, pan=0.35); ou.add(tb, bass(midi("G2"), 0.4), 0.55)
        for k, n in enumerate(CHORDS["G"]): ou.add(tb + E8 + k * 0.004, pluck(midi(n), 0.3, bright=0.7), 0.16)
    for n, k in ANSWER:
        ou.add(k * E8, mallet(midi(n), 0.9), 0.78, pan=0.1); ou.add(k * E8, mallet(midi(n) * 2, 0.5), 0.12, pan=-0.1)
    th = 6 * E8
    ou.add(th, mallet(midi("C6"), 2.0), 0.9); ou.add(th, mallet(midi("C5"), 2.0), 0.4)
    ou.add(th, kick(), 1.0); ou.add(th, crash(), 0.8); ou.add(th + 0.02, clink(), 0.7, pan=-0.2); ou.add(th, bass(midi("C2"), 1.2), 0.75)
    for k, n in enumerate(["C3", "G3", "C4", "E4", "G4", "C5"]):
        ou.add(th + k * 0.008, pluck(midi(n), 2.0, bright=0.8, decay=0.998), 0.2, pan=-0.3 + 0.12 * k)
    outro = reverb(ou.buf, wet=0.22, size=1.6)
    f2 = np.ones(len(outro)); f2[-int(0.8 * SR):] = np.linspace(1, 0, int(0.8 * SR)) ** 2
    outro = norm(outro * f2[:, None])

    save("sting.wav", sting); save("bed_loop.wav", bed); save("outro_hit.wav", outro)
    save("theme_demo.wav", norm(np.concatenate([sting[:int(BAR * SR)], np.tile(bed, (2, 1)) * 0.6, outro])))
    # story-transition SFX: the same cup clink, solo (generated last so the stems above stay byte-identical)
    ck = Bus(0.9); ck.add(0.0, clink(), 1.0, pan=0.15)
    save("sfx_clink.wav", norm(reverb(ck.buf, wet=0.12, size=0.6), -3.0))


if __name__ == "__main__":
    main()
