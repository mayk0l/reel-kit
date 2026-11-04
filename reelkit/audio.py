"""Audio analysis on the 16 kHz mono WAVs: energy maps, speech regions, pause trimming, cut-edge checks,
spectral diagnosis of saturated / boomy lav recordings."""
import subprocess
import wave
from functools import lru_cache

import numpy as np

from .tools import run

SR = 16000
# default voice chain: gentle compression + limiter
VOICE_POST = "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=150:makeup=1,alimiter=limit=0.89"
# after neural restoration (VoiceFixer): keep its dynamics, only tidy up
RESTORED_POST = "highpass=f=80,acompressor=threshold=-22dB:ratio=2:attack=10:release=200:makeup=1,alimiter=limit=0.89"
# destroyed lav take (mic at the mouth, clipped before AAC): reconstruct peaks (adeclip), remove boom, keep the
# 2 kHz intelligibility band, and pull DOWN the 4 kHz+ band - there it is mostly distortion, boosting it sounds worse.
# Never add more compression. Measured on the Tech AI Summit reel: -7 dB of harshness, "Shadow AI" still intelligible.
REPAIR_POST = ("adeclip,highpass=f=120,equalizer=f=250:t=q:w=1:g=-6,equalizer=f=2200:t=q:w=1.2:g=3,"
               "highshelf=f=4200:g=-8,lowpass=f=8500,deesser=i=0.55,alimiter=limit=0.89")


@lru_cache(None)
def load(path):
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def extract_wav(tools, src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    run([tools.ffmpeg, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(SR), dst])


def energy_db(x, a, b, hop=0.01):
    s = x[int(a * SR):int(b * SR)]
    h = int(SR * hop)
    n = len(s) // h
    if n == 0:
        return np.array([-120.0])
    return 20 * np.log10(np.sqrt(np.mean(s[:n * h].reshape(n, h) ** 2, axis=1)) + 1e-9)


def speech_regions(x, a, b, below=20):
    """(start, end) blocks louder than (90th percentile - below dB), 10 ms resolution."""
    db = energy_db(x, a, b)
    db = np.convolve(db, np.ones(3) / 3, "same")
    m = db > np.percentile(db, 90) - below
    e = np.flatnonzero(np.diff(np.r_[0, m.astype(np.int8), 0]))
    return [(a + s / 100, a + t / 100) for s, t in zip(e[0::2], e[1::2]) if t - s >= 5]


def trim_pauses(x, a, b, pause_max=0.45, keep=0.15):
    """Split [a, b] so silences longer than pause_max shrink to 2*keep (jump cuts)."""
    regs = speech_regions(x, a, b)
    out, start = [], a
    for (_, e0), (s1, _) in zip(regs, regs[1:]):
        if s1 - e0 > pause_max:
            out.append((start, e0 + keep))
            start = s1 - keep
    out.append((start, b))
    return out


def edge_issues(x, a, b):
    """Warn when a cut lands inside speech. Checks the 40 ms at each edge AND whether speech keeps going
    right after the out point / was already going right before the in point (a word chopped in half)."""
    seg = x[int(max(0, a - 1.5) * SR):int((b + 1.5) * SR)]      # wider context: short soft pieces don't self-trigger
    if not len(seg):
        return []
    ref = np.percentile(np.abs(seg), 99) + 1e-9
    rel = lambda t0, t1: 20 * np.log10(np.sqrt(np.mean(x[int(t0 * SR):int(t1 * SR)] ** 2) + 1e-12) / ref)
    issues = []
    if rel(a, a + 0.04) > -22:
        issues.append(f"entrada en plena voz ({rel(a, a + 0.04):+.0f} dB)")
    if rel(b - 0.04, b) > -22:
        issues.append(f"salida en plena voz ({rel(b - 0.04, b):+.0f} dB)")
    # silence after the out point shorter than ~80 ms = probably a gap between syllables, not between words
    after = energy_db(x, b, b + 0.3) - 20 * np.log10(ref)
    loud = np.flatnonzero(after > -18)
    if len(loud) and loud[0] * 0.01 < 0.08:
        issues.append(f"la voz retoma {loud[0] * 10} ms después del corte: confirma con `reelkit verify` que no partiste una palabra")
    return issues


def spectrum_report(tools, path, a, b):
    """Band levels relative to 300-1000 Hz plus crest factor, on voiced frames only.
    Clean lav voice here: 250 Hz around -2..-8 dB, 2-3 kHz around -10..-15 dB, crest > 12 dB.
    Boomy+crushed (mic at the mouth): 250 Hz >= 0 dB, 2-3 kHz <= -16 dB, crest < 11 dB -> use repair=true."""
    raw = subprocess.run([tools.ffmpeg, "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(path), "-vn",
                          "-ac", "1", "-ar", "48000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return _bands(np.frombuffer(raw, np.float32))


def _bands(x, sr=48000):
    n = 4096
    fr = x[:len(x) // n * n].reshape(-1, n)
    rms = np.sqrt((fr ** 2).mean(1))
    fr = fr[rms > np.percentile(rms, 50)]
    S = (np.abs(np.fft.rfft(fr * np.hanning(n), axis=1)) ** 2).mean(0)
    f = np.fft.rfftfreq(n, 1 / sr)
    ref = 10 * np.log10(S[(f > 300) & (f < 1000)].mean())
    bands = {f"{b}Hz": round(float(10 * np.log10(S[(f > b / 1.26) & (f < b * 1.26)].mean()) - ref), 1)
             for b in (125, 250, 500, 1000, 2000, 3000, 4000, 6000)}
    crest = 20 * np.log10(np.abs(x).max() / (np.sqrt((x ** 2).mean()) + 1e-12))
    bands["cresta_dB"] = round(float(crest), 1)
    bands["sugerencia"] = "repair = true" if bands["250Hz"] > -1 and crest < 11 else "ok"
    return bands
