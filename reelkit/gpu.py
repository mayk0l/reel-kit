"""Whisper loader with CUDA when available (NVIDIA libs from pip wheels) and CPU fallback."""
import os
import sys
from pathlib import Path

import numpy as np


def _nvidia_dirs():
    try:
        import nvidia
    except ImportError:
        return []
    dirs = []
    for base in nvidia.__path__:
        for sub in Path(base).iterdir():
            for d in (sub / "lib", sub / "bin"):
                if d.is_dir():
                    dirs.append(str(d))
    return dirs


def ensure_cuda_env():
    """Make the pip-installed CUDA libraries loadable. Call before importing faster_whisper.
    Linux reads LD_LIBRARY_PATH only at process start, so the process re-executes itself once."""
    dirs = _nvidia_dirs()
    if not dirs:
        return
    if os.name == "nt":
        for d in dirs:
            os.add_dll_directory(d)
        os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    elif sys.platform.startswith("linux"):
        cur = os.environ.get("LD_LIBRARY_PATH", "")
        if not all(d in cur.split(os.pathsep) for d in dirs) and not os.environ.get("REELKIT_REEXEC"):
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(dirs + ([cur] if cur else []))
            os.environ["REELKIT_REEXEC"] = "1"
            os.execv(sys.executable, sys.orig_argv)


_model = None


def whisper(model=None):
    """large-v3 on CUDA (int8_float16); falls back to CPU int8 (default 'medium', slower)."""
    global _model
    if _model is not None:
        return _model
    from faster_whisper import WhisperModel
    import ctranslate2
    if ctranslate2.get_cuda_device_count() > 0:
        try:
            m = WhisperModel(model or "large-v3", device="cuda", compute_type="int8_float16")
            list(m.transcribe(np.zeros(16000, np.float32), language="es")[0])   # forces cuBLAS/cuDNN to load
            _model = m
            return m
        except Exception as e:  # noqa: BLE001 - any CUDA failure means CPU
            print(f"[reelkit] CUDA no disponible ({str(e)[:120]}); uso CPU.", file=sys.stderr)
    _model = WhisperModel(model or os.environ.get("REELKIT_CPU_MODEL", "medium"), device="cpu", compute_type="int8")
    return _model


def transcribe(audio, words=True, vad=False, context=False):
    """audio: float32 mono 16 kHz. Returns faster-whisper segments as a list."""
    segs, _ = whisper().transcribe(audio, language="es", vad_filter=vad, word_timestamps=words, beam_size=5,
                                   condition_on_previous_text=context)
    return list(segs)
