"""Find usable ffmpeg builds on Windows / macOS / Linux and run them.

Two roles are needed, and one full build usually covers both (e.g. gyan.dev "full" on Windows):
  ffmpeg      decode HEVC (iPhone), zscale/tonemap (HDR), zoompan, encode libx264
  ffmpeg_ass  burn the ASS motion graphics (libass)
Some Linux distro builds miss HEVC/x264 (patents); the ffmpeg bundled with Shotcut has them.
"""
import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

EXE = ".exe" if os.name == "nt" else ""
NEEDS = {"ffmpeg": ("hevc", "libx264", "zscale", "tonemap", "zoompan", "sidechaincompress", "loudnorm"),
         "ffmpeg_ass": ("ass",)}


def _candidates(name):
    env = os.environ.get(f"REELKIT_{name.upper()}")
    if env:
        yield env
    found = shutil.which(name)
    if found:
        yield found
    home = Path.home()
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    for d in (home / ".local/opt/Shotcut.app", Path("/usr/lib/shotcut"), Path("/opt/shotcut"),
              Path("/Applications/Shotcut.app/Contents/MacOS"), program_files / "Shotcut",
              home / "AppData/Local/Microsoft/WinGet/Links", Path(r"C:\ffmpeg\bin"), Path("/opt/homebrew/bin")):
        p = d / f"{name}{EXE}"
        if p.exists():
            yield str(p)


@lru_cache(None)
def capabilities(ffmpeg):
    def listing(flag):
        try:
            return subprocess.run([ffmpeg, "-hide_banner", flag], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace").stdout
        except OSError:
            return ""
    dec, enc, flt = listing("-decoders"), listing("-encoders"), listing("-filters")
    has = lambda txt, n: re.search(rf"^\s*\S+\s+{re.escape(n)}\s", txt, re.M) is not None
    return {"hevc": has(dec, "hevc"), "libx264": has(enc, "libx264"), "zscale": has(flt, "zscale"),
            "tonemap": has(flt, "tonemap"), "zoompan": has(flt, "zoompan"), "ass": has(flt, "ass"),
            "sidechaincompress": has(flt, "sidechaincompress"), "loudnorm": has(flt, "loudnorm")}


class Tools:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        cands = [c for c in dict.fromkeys([cfg.get("ffmpeg"), cfg.get("ffmpeg_ass"), *_candidates("ffmpeg")]) if c]
        ok = lambda c, role: all(capabilities(c).get(k) for k in NEEDS[role])
        self.ffmpeg = cfg.get("ffmpeg") or next((c for c in cands if ok(c, "ffmpeg")), None)
        if self.ffmpeg and ok(self.ffmpeg, "ffmpeg_ass"):
            self.ffmpeg_ass = cfg.get("ffmpeg_ass") or self.ffmpeg
        else:
            self.ffmpeg_ass = cfg.get("ffmpeg_ass") or next((c for c in cands if ok(c, "ffmpeg_ass")), None)
        probe = Path(self.ffmpeg).with_name(f"ffprobe{EXE}") if self.ffmpeg else None
        self.ffprobe = cfg.get("ffprobe") or (str(probe) if probe and probe.exists() else shutil.which("ffprobe"))
        self.candidates = cands

    def missing(self):
        out = []
        if not self.ffmpeg:
            out.append("ffmpeg con HEVC + libx264 + zscale/tonemap + zoompan")
        if not self.ffmpeg_ass:
            out.append("ffmpeg con libass (filtro 'ass')")
        if not self.ffprobe:
            out.append("ffprobe")
        return out


def run(cmd, cwd=None, check=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd,
                       encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise RuntimeError(f"Falló: {' '.join(map(str, cmd))[:400]}\n{r.stderr[-3000:]}")
    return r


def probe(tools, path):
    r = run([tools.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    return json.loads(r.stdout)


def duration(tools, path):
    return float(run([tools.ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout)


def loudness(tools, path, start=0.0, dur=None, audio_only=True):
    """Integrated loudness (LUFS) of a range; -70 when silent."""
    cmd = [tools.ffmpeg, "-hide_banner", "-nostats", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    err = run(cmd, check=False).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    lra = re.findall(r"LRA:\s+(-?[\d.]+) LU", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    return {"lufs": float(m[-1]) if m else -70.0, "lra": float(lra[-1]) if lra else 0.0,
            "true_peak": float(tp[-1]) if tp else -70.0}
