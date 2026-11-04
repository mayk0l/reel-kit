"""Neural restoration for badly clipped / distorted speech (VoiceFixer). Optional and heavy (PyTorch), so it
runs in its own Python: REELKIT_RESTORE_PY or `restore_python` in [tools]; falls back to the current one.

Use it only when `reelkit spectrum` / the clipping metric says the take is destroyed (e.g. >5 % of samples above
0.9 FS: the signal was flattened against the ceiling before AAC). EQ repair cannot bring back clipped peaks."""
import os
import subprocess
import sys
from pathlib import Path

from .tools import run

WORKER = r'''
import sys, warnings
warnings.filterwarnings("ignore")
import torch
from voicefixer import VoiceFixer
vf = VoiceFixer()
vf.restore(input=sys.argv[1], output=sys.argv[2], cuda=torch.cuda.is_available(), mode=int(sys.argv[3]))
'''


def python_for_restore(cfg):
    return cfg.get("tools", {}).get("restore_python") or os.environ.get("REELKIT_RESTORE_PY") or sys.executable


def restored_audio(p, src, a, b, mode=0, margin=0.5):
    """Restore [a-margin, b+margin] of `src`; returns (wav_path, start_offset_in_source). Cached in work/restored."""
    a0 = max(0.0, a - margin)
    out_dir = p.work / "restored"
    out_dir.mkdir(exist_ok=True)
    dst = out_dir / f"{src}_{a0:.2f}_{b + margin:.2f}_m{mode}.wav"
    if dst.exists():
        return dst, a0
    tmp = out_dir / f"_in_{src}_{a0:.2f}.wav"
    # VoiceFixer needs headroom: decode to float and pull the level down so restored peaks have room
    run([p.tools.ffmpeg, "-v", "error", "-y", "-ss", f"{a0:.3f}", "-to", f"{b + margin:.3f}", "-i", p.media(src), "-vn",
         "-ac", "1", "-ar", "44100", "-af", "volume=-6dB", "-c:a", "pcm_s16le", tmp])
    py = python_for_restore(p.cfg)
    r = subprocess.run([py, "-c", WORKER, str(tmp), str(dst), str(mode)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tmp.unlink(missing_ok=True)
    if r.returncode or not Path(dst).exists():
        raise SystemExit("VoiceFixer falló. Instala requirements-restore.txt en un venv y apunta REELKIT_RESTORE_PY "
                         f"a ese python.\n{r.stderr[-1500:]}")
    print(f"  restaurado {src} {a:.2f}-{b:.2f} con VoiceFixer")
    return dst, a0
