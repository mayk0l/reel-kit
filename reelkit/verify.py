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


FILLERS = {"eh", "ehh", "eeh", "em", "emm", "mm", "mmm", "este", "ah", "eh eh", "eh, eh", "o sea", "bueno"}
NOISE = {"gracias", "gracias.", "ya", "sí", "(nada)"}


def _norm(t):
    return " ".join("".join(c for c in w if c.isalnum()) for w in t.lower().split()).strip()


def fillers(p: Project, src, a, b, gap=0.3):
    """Muletillas y trabadas. Whisper omite los "eh" y, con contexto, 'arregla' las repeticiones, así que:
      1. el tramo se parte en frases según las pausas reales y cada frase se transcribe sola;
      2. prueba de eliminación: cada bloque de voz de la frase se silencia y se vuelve a transcribir; si el texto
         no cambia, ese bloque no aportaba palabras = MULETILLA ("eh, eh…" entre "Izurieta" y "gerente general");
      3. una frase corta cuyas palabras reaparecen al comienzo de la siguiente = ARRANQUE EN FALSO
         ("¿estamos?" + "hoy estamos con…").
    Es una ayuda: confirma siempre con `verify` y avisa al usuario que escuche esos puntos."""
    x = audio.load(p.wav(src))
    regs = [r for r in audio.speech_regions(x, a, b, below=25) if r[1] - r[0] >= 0.06]
    phrases = []
    for s_, e_ in regs:
        if phrases and s_ - phrases[-1][1] < gap:
            phrases[-1][1] = e_
            phrases[-1][2].append((s_, e_))
        else:
            phrases.append([s_, e_, [(s_, e_)]])
    clip = lambda t0, t1: x[int(max(0, t0) * audio.SR):int(t1 * audio.SR)].copy()
    texts = [_say(clip(s_ - 0.05, e_ + 0.08)) for s_, e_, _ in phrases]
    print(f"== {src} {a}-{b}: {len(phrases)} frases")
    found = 0
    for i, ((s_, e_, blocks), t) in enumerate(zip(phrases, texts)):
        n = _norm(t)
        nxt = _norm(texts[i + 1]).split()[:4] if i + 1 < len(texts) else []
        flag = ""
        if n in FILLERS or (n and all(w in FILLERS for w in n.split())):
            flag = "⚠ MULETILLA: sácala entera"
        elif n and nxt and len(n.split()) <= 3 and all(w in nxt for w in n.split()):
            flag = "⚠ ARRANQUE EN FALSO: empieza en la frase siguiente"
        elif n in NOISE or len(n) <= 2:
            flag = "? corta: puede ser ruido o muletilla, escúchala"
        print(f"  {s_:7.2f}-{e_:7.2f}  {t[:72]:<72} {flag}")
        found += bool(flag.startswith("⚠"))
        if len(blocks) > 1 and not flag:
            base = clip(s_ - 0.05, e_ + 0.08)
            for bs, be in blocks:
                if be - bs < 0.15:
                    continue
                y = base.copy()
                y[int((bs - s_ + 0.05) * audio.SR):int((be - s_ + 0.05) * audio.SR)] = 0
                if _norm(_say(y)) == n:
                    found += 1
                    print(f"      ⚠ posible muletilla/trabada en {bs:.2f}-{be:.2f}: al quitarla el texto no cambia (confírmalo con verify)")
    print(f"  {found} punto(s) a corregir" if found else "  sin muletillas detectadas (igual confírmalo escuchando)")
