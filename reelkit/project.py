"""A reel project = a folder with reel.toml + raw videos. See examples/reel.toml."""
import shutil
import tomllib
from pathlib import Path

from .tools import Tools

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".avi", ".mts"}
DEFAULTS = {
    "project": {"raw_dir": "raw", "work_dir": "work", "out_dir": "out", "fps": 30, "width": 1080, "height": 1920},
    "audio": {"voice_lufs": -16.0, "target_lufs": -14.0, "pause_max": 0.45, "pause_keep": 0.15},
    "music": {"file": "", "drop_at": 0.0, "level_lufs": -21.0, "credit": ""},
    "style": {"accent": "#FFD400", "dark": "#0B0B0F", "chip_numbers": True, "punch_zoom": True, "jumpcut_zoom": True},
    "text": {"title": "", "title_sub": "", "cta": "", "cta_sub": ""},
    "captions": {"highlight": [], "replace": {}},
    "tools": {},
}


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        cfg_path = self.root / "reel.toml"
        if not cfg_path.exists():
            raise SystemExit(f"No encuentro {cfg_path}. Copia examples/reel.toml a la carpeta del proyecto.")
        with open(cfg_path, "rb") as f:
            user = tomllib.load(f)
        self.cfg = {k: {**v, **user.get(k, {})} for k, v in DEFAULTS.items()}
        self.segments = user.get("segment", [])
        p = self.cfg["project"]
        self.raw = self.root / p["raw_dir"]
        self.work = self.root / p["work_dir"]
        self.out = self.root / p["out_dir"]
        for d in (self.work, self.out):
            d.mkdir(parents=True, exist_ok=True)
        self.tools = Tools(self.cfg["tools"])
        self._index = None

    # ---- media lookup by file stem (IMG_4543 -> raw/.../IMG_4543.MOV)
    def videos(self):
        return sorted(p for p in self.raw.rglob("*") if p.suffix.lower() in VIDEO_EXT)

    def media(self, stem):
        if self._index is None:
            self._index = {p.stem: p for p in self.videos()}
        if stem not in self._index:
            raise SystemExit(f"No encuentro el video '{stem}' en {self.raw}")
        return self._index[stem]

    def wav(self, stem):
        return self.work / "wav" / f"{stem}.wav"

    def transcript(self, stem):
        return self.work / "transcripts" / f"{stem}.json"

    def music_file(self):
        f = self.cfg["music"]["file"]
        return (self.root / f) if f else None

    def fonts_dir(self):
        """Fonts copied next to the renders so libass gets a short relative path on every OS."""
        src = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        dst = self.out / "fonts"
        dst.mkdir(exist_ok=True)
        for f in src.glob("*.ttf"):
            if not (dst / f.name).exists():
                shutil.copy2(f, dst / f.name)
        return dst
