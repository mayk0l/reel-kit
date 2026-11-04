"""Step 4: QA of a finished reel - what it says (transcribed with the music on), loudness, and a frame sheet."""
import subprocess

import numpy as np
from PIL import Image

from . import gpu
from .project import Project
from .tools import duration, loudness, run


def check(p: Project, version, times=None):
    T = p.tools
    final = p.out / f"reel_{version}.mp4"
    raw = subprocess.run([T.ffmpeg, "-v", "error", "-i", str(final), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    print("== Lo que se escucha (Whisper sobre la mezcla final con música):")
    for s in gpu.transcribe(x, words=False):
        print(f"  [{s.start:5.1f}-{s.end:5.1f}] {s.text.strip()}")
    L = loudness(T, final)
    print(f"\n== Volumen: {L['lufs']} LUFS (objetivo {p.cfg['audio']['target_lufs']}), LRA {L['lra']} LU, pico {L['true_peak']} dBTP")
    dur = duration(T, final)
    times = times or [round(dur * k / 11, 1) for k in range(1, 11)]
    thumbs = []
    for t in times:
        f = p.out / f"_frame_{t}.png"
        run([T.ffmpeg, "-v", "error", "-y", "-ss", f"{t}", "-i", final, "-frames:v", "1", "-vf", "scale=270:-2", f])
        thumbs.append(Image.open(f))
        f.unlink()
    sheet = Image.new("RGB", (sum(i.width for i in thumbs), thumbs[0].height), "black")
    x0 = 0
    for i in thumbs:
        sheet.paste(i, (x0, 0))
        x0 += i.width
    out = p.out / f"check_{version}.jpg"
    sheet.save(out, quality=88)
    print(f"\n== Fotogramas en {times} -> {out}")
