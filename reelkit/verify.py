"""Cut verification. Lesson learned: Whisper word times run early and, given a whole sentence, Whisper
'completes' words that the cut actually chopped. So every cut is checked three ways:
energy at the edges + transcription of ONLY the first and last ~1.3 s (no context to fill in from)."""
import numpy as np

from . import audio, gpu
from .project import Project


def energy_map(p: Project, src, a, b, step=0.02):
    x = audio.load(p.wav(src))
    db = audio.energy_db(x, a, b, hop=0.01)
    k = max(1, int(step / 0.01))
    cells = [f"{a + i / 100:.2f}:{db[i]:.0f}" for i in range(0, len(db), k)]
    print(f"== {src} {a}-{b}  (dB por {int(step * 1000)} ms; silencio < -35, voz > -25)")
    for i in range(0, len(cells), 12):
        print("  " + " ".join(cells[i:i + 12]))


def _say(x):
    pad = np.zeros(8000, np.float32)
    return " ".join(s.text.strip() for s in gpu.transcribe(np.concatenate([pad, x, pad]), words=False)) or "(nada)"


def verify(p: Project, specs, edge=1.3):
    """specs: list of (src, a, b). Prints full / head-only / tail-only transcription + edge warnings."""
    for src, a, b in specs:
        x = audio.load(p.wav(src))
        sl = lambda t0, t1: x[int(t0 * audio.SR):int(t1 * audio.SR)]
        print(f"\n{src} {a:.2f}-{b:.2f} ({b - a:.1f}s)")
        print(f"  completo : {_say(sl(a, b))}")
        if b - a > edge * 1.5:
            print(f"  inicio   : {_say(sl(a, a + edge))}")
            print(f"  final    : {_say(sl(b - edge, b))}")
        for issue in audio.edge_issues(x, a, b):
            print(f"  ⚠ {issue}")
