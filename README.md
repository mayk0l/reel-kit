# reel-kit

Edición de Reels verticales desde entrevistas grabadas con celular, guiada por Claude Code.
Funciona en **Windows, macOS y Linux**.

Lo que hace:

- **Analiza** todos los videos: transcripción (Whisper), volumen por clip, miniaturas y detección de HDR.
- **Fija cortes verificados de oído**: usa la energía del audio y transcribe solo el inicio y solo el final de cada corte.
- **Nivela el audio** (voz a −16 LUFS, mezcla a −14 LUFS, pico ≤ −1.5 dBTP) y repara voces recortadas o embarradas.
  Opcional: restauración con IA (VoiceFixer) para tomas destruidas.
- **Música libre de derechos** (Openverse, CC0 / CC BY), alineada a un drop y con *ducking* bajo la voz.
- **Motion graphics**:
  - subtítulos karaoke con caja deslizante;
  - carteles de nombre animados;
  - etiquetas de sección numeradas;
  - titular de hook con impacto;
  - tarjetas de título y cierre;
  - zoom de impacto y jump cuts disimulados.
- **Entrega** un MP4 H.264 1080×1920 a 30 fps, listo para Instagram o TikTok.

## Instalación

Necesitas Python 3.11+, ffmpeg y, de forma opcional, una GPU NVIDIA para transcribir más rápido.

### Windows

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg          # build "full": HEVC, x264, zimg y libass
git clone https://github.com/mayk0l/reel-kit.git
cd reel-kit
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -r requirements-gpu.txt   # solo si tienes GPU NVIDIA
.venv\Scripts\python -m reelkit doctor
```

Si cierras y abres la terminal después de instalar ffmpeg, `doctor` lo encuentra en el PATH.

### macOS

```bash
brew install python@3.12 ffmpeg
git clone https://github.com/mayk0l/reel-kit.git && cd reel-kit
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m reelkit doctor
```

En Mac no hay CUDA: Whisper corre en CPU con el modelo `medium`.

### Linux

```bash
git clone https://github.com/mayk0l/reel-kit.git && cd reel-kit
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-gpu.txt
.venv/bin/python -m reelkit doctor
```

Algunas distros (openSUSE, Fedora) traen un ffmpeg sin HEVC ni x264. En ese caso:

1. Descarga Shotcut portable desde <https://shotcut.org> y descomprímelo en `~/.local/opt/`.
2. `reelkit` lo detecta solo. Si no, exporta `REELKIT_FFMPEG=/ruta/Shotcut.app/ffmpeg`.

El ffmpeg del sistema se sigue usando para los gráficos (libass).

### Opcional: restauración de voz con IA

VoiceFixer usa PyTorch y pesa varios GB, así que va en un entorno aparte:

```bash
python -m venv .venv-restore
.venv-restore/bin/pip install -r requirements-restore.txt     # Windows: .venv-restore\Scripts\pip ...
```

Apunta `REELKIT_RESTORE_PY` al python de ese entorno y marca `restore = true` en el segmento.

## Uso con Claude Code

Abre Claude Code **dentro de la carpeta del repo**. La skill `editar-reel` (en `.claude/skills/`) se carga sola y guía todo el flujo:

```
Usa la skill editar-reel. Mis videos están en <carpeta>. Quiero un reel de ~60-90 s con hook, intro, desarrollo y cierre.
```

## Uso manual

En Windows, reemplaza `.venv/bin/python` por `.venv\Scripts\python`.

```bash
.venv/bin/python -m reelkit ingest  ../mi-reel                               # analiza raw/
.venv/bin/python -m reelkit energy  ../mi-reel IMG_4560 151.2 153.4          # dónde están los silencios
.venv/bin/python -m reelkit verify  ../mi-reel IMG_4560 149.10 152.47        # escucha un corte
.venv/bin/python -m reelkit fillers  ../mi-reel IMG_4560 1.7 8.9           # muletillas y trabadas
.venv/bin/python -m reelkit spectrum ../mi-reel IMG_4543 64.7 99             # ¿voz saturada?
.venv/bin/python -m reelkit music-search "tech house"
.venv/bin/python -m reelkit music-get <url> ../mi-reel/music/tema.mp3
.venv/bin/python -m reelkit music-profile ../mi-reel/music/tema.mp3          # drops y huecos
.venv/bin/python -m reelkit build   ../mi-reel --version v1                  # -> out/reel_v1.mp4
.venv/bin/python -m reelkit check   ../mi-reel --version v1                  # QA: transcripción, LUFS, fotogramas
```

Una carpeta de proyecto contiene:

- `reel.toml`: guion, cortes, textos y música. Hay dos ejemplos reales del Tech AI Summit:
  - [`examples/reel.toml`](examples/reel.toml): reel resumen con varias entrevistas.
  - [`examples/entrevista.toml`](examples/entrevista.toml): una entrevista completa, con pregunta → respuesta por bloque.
- `raw/`: los videos originales.
- `music/`: opcional, la pista de música.

`reelkit` crea `work/` (análisis) y `out/` (renders).

## Licencias

- El código es MIT.
- La tipografía Poppins (`assets/fonts`) es SIL Open Font License 1.1 (ver `assets/fonts/OFL.txt`).
- La música que descargues tiene su propia licencia. Con CC BY tienes que dar crédito en el video y en el post.
