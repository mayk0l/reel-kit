"""Environment check with OS-specific install hints."""
import platform
import sys

from .tools import Tools, capabilities

HINTS = {
    "Windows": ("winget install Gyan.FFmpeg   (build 'full': trae HEVC, x264, zimg y libass)\n"
                "    o descarga ffmpeg-release-full desde https://www.gyan.dev/ffmpeg/builds/ y agrega bin\\ al PATH"),
    "Darwin": "brew install ffmpeg   (Homebrew trae HEVC, x264, zimg y libass)",
    "Linux": ("Si tu distro no trae HEVC/x264 (p.ej. openSUSE/Fedora): instala Shotcut portable\n"
              "    (https://shotcut.org) y exporta REELKIT_FFMPEG=/ruta/Shotcut.app/ffmpeg; libass suele venir en el ffmpeg del sistema."),
}


def doctor():
    ok = True
    print(f"Python {sys.version.split()[0]} en {platform.system()} {platform.machine()}")
    if sys.version_info < (3, 11):
        print("✗ Necesitas Python 3.11 o superior"); ok = False
    t = Tools()
    for c in t.candidates:
        caps = capabilities(c)
        print(f"  ffmpeg: {c}\n     " + " ".join(f"{k}{'✓' if v else '✗'}" for k, v in caps.items()))
    print(f"→ decodificar/encodear: {t.ffmpeg or '✗ ninguno'}")
    print(f"→ gráficos (libass):    {t.ffmpeg_ass or '✗ ninguno'}")
    print(f"→ ffprobe:              {t.ffprobe or '✗ ninguno'}")
    if t.missing():
        ok = False
        print("✗ Falta: " + "; ".join(t.missing()))
        print("  Cómo instalar: " + HINTS.get(platform.system(), HINTS["Linux"]))
    for mod in ("numpy", "PIL", "faster_whisper"):
        try:
            __import__(mod)
            print(f"✓ {mod}")
        except ImportError:
            ok = False
            print(f"✗ {mod}: pip install -r requirements.txt")
    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        print(f"{'✓' if n else '·'} GPU CUDA: {n} dispositivo(s)" + ("" if n else " (se usará CPU: más lento, modelo 'medium')"))
    except ImportError:
        pass
    print("\nTodo listo ✓" if ok else "\nHay cosas por instalar (ver arriba).")
    return 0 if ok else 1
