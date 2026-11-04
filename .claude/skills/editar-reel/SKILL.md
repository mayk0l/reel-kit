---
name: editar-reel
description: Edita Reels verticales (Instagram/TikTok) a partir de entrevistas grabadas con celular usando reel-kit - analiza todos los videos, propone un guion con hook/intro/desarrollo/cierre, fija cortes verificados de oído, nivela y repara el audio, agrega música libre de derechos con ducking y motion graphics profesionales, y entrega un MP4 a -14 LUFS. Úsala cuando el usuario quiera armar, iterar o corregir un reel/video corto desde material propio, en Windows, macOS o Linux.
---

# Editar un Reel con reel-kit

Flujo probado en el reel del Tech AI Summit (`examples/reel.toml`). Herramienta: el paquete `reelkit` de este repo
(`python -m reelkit ...` desde la raíz del repo, con el venv activo). Todo se comunica en español con el usuario.

## 0. Preparar el entorno (una vez por PC)

1. `python -m reelkit doctor` — dice qué falta y cómo instalarlo según el SO. Si no existe el venv, créalo según el README
   (Windows: `py -3.12 -m venv .venv` y `.venv\Scripts\python -m pip install -r requirements.txt`;
   macOS/Linux: `python3 -m venv .venv` y `.venv/bin/pip install -r requirements.txt`).
2. ffmpeg: Windows → `winget install Gyan.FFmpeg` (build full: HEVC + x264 + zimg + libass en un solo binario).
   macOS → `brew install ffmpeg`. Linux sin HEVC/x264 → Shotcut portable y `REELKIT_FFMPEG=.../Shotcut.app/ffmpeg`.
3. GPU NVIDIA: `pip install -r requirements-gpu.txt` (cuBLAS/cuDNN por pip). Sin GPU funciona en CPU con el modelo `medium`
   (más lento; avisa al usuario cuánto puede tardar).
4. En Windows usa rutas con comillas si tienen espacios. Nunca escribas rutas absolutas dentro de filtros de ffmpeg: reelkit
   ya trabaja con rutas relativas (cwd) para que funcione igual en los tres sistemas.

## 1. Proyecto e ingesta

- Carpeta del proyecto: `reel.toml` + `raw/` con los videos (zip extraído en su propia carpeta). Copia `examples/reel.toml`
  y vacía la lista de `[[segment]]`.
- `python -m reelkit ingest <proyecto>` → `work/`: `media.json` (resolución, rotación, HDR), `audio_levels.tsv` (LUFS por
  clip), `sheets/overview_*.jpg` (miniaturas: **míralas** con Read para entender cada clip), `all_transcripts.txt`.
- Lee todo `all_transcripts.txt`. Clasifica: entrevistas útiles, b-roll (ambiente, público, stands, personajes), descartes.

## 2. Guion (pídele aprobación al usuario antes de cortar)

Estructura que funcionó:
- **HOOK (0–10 s)**: la frase más concreta y sorprendente, mejor con números ("de 1 semana a 2 horas"). Titular grande `hook = "DE {1 SEMANA}|A {2 HORAS}"`.
- **INTRO (~5 s)**: voz en off "hoy estamos en…" sobre b-roll del lugar + tarjeta de título (`[text] title`). El drop de la música cae aquí (`drop = true`).
- **DESARROLLO**: 3–4 bloques temáticos, cada uno con `chip` (se numeran solos). Deja que cada entrevistado **termine la idea**: el usuario prefirió contexto completo antes que frases sueltas.
- **CONCLUSIÓN**: el consejo más fuerte, con espacio suficiente.
- **CIERRE**: b-roll llamativo + CTA (`[text] cta`) con flecha animada.
Presenta el guion como tabla: bloque, clip, tramo, frase. Evita datos dudosos que el entrevistado mismo no sabe confirmar.
Duración: 60–100 s funcionó; si crece, propone qué bloque sacar.

## 3. Fijar cortes (lo más importante: aquí se cometieron los errores)

**Nunca cortes con los tiempos de Whisper.** Van 0.3–1.0 s adelantados y, con frase completa como contexto, Whisper
"rellena" palabras que el corte partió (así se cortó "importante" y "control" sin que la transcripción lo mostrara).

Para cada entrada/salida:
1. `python -m reelkit energy <proyecto> IMG_4560 151.2 153.4` → busca el silencio real (< -35 dB) entre palabras.
   Sílabas de una misma palabra tienen valles cortos (40–80 ms); entre palabras suele haber > 100 ms.
2. `python -m reelkit verify <proyecto> IMG_4560 149.10 152.47 [más tríos…]` → transcribe **completo, solo inicio y solo
   final** (1.3 s, sin contexto). Si el "final" no termina en la palabra esperada, el corte está mal.
3. Recién entonces escribe `in`/`out` en `reel.toml`. Al compilar, `build` repite el chequeo de bordes y avisa (⚠).
Pausas largas dentro de un tramo se recortan solas (jump cuts con zoom alternado que los disimula).

## 4. Audio

- Todo se nivela solo: voz a -16 LUFS por tramo, mezcla final a -14 LUFS (estándar Reels/TikTok).
- Si el usuario dice "suena saturado": `python -m reelkit spectrum <proyecto> SRC A B`. Micrófono pegado a la boca =
  250 Hz alto, 2–3 kHz bajo, cresta < 11 dB → agrega `repair = true` al segmento (EQ correctiva, sin más compresión).
  Verifica que los dos canales no sean una pista de seguridad distinta antes de concluir.
- B-roll: su sonido va **silenciado** (voces de fondo pueden decir groserías; pasó). La música lo cubre.
- Voz en off sobre otra toma: `vo = { src = "...", in = ..., out = ... }`.

## 5. Música (libre de derechos)

1. `python -m reelkit music-search "tech house"` (Openverse). CC0 = sin crédito; CC BY = crédito obligatorio
   (`[music] credit`, también en la descripción del post). Prefiere temas completos a loops.
2. `python -m reelkit music-get URL music/tema.mp3` y `python -m reelkit music-profile music/tema.mp3`.
3. Elige un drop tal que **desde el drop hasta el final del reel no haya huecos/silencios** del tema (pasó: el tema se
   apagaba bajo el cierre). `drop_at` = segundo exacto del drop; cae en el segmento con `drop = true`.
   La música baja sola bajo la voz (sidechain) y sube en b-roll y cierre.

## 6. Compilar, revisar, iterar

- `python -m reelkit build <proyecto> --version v1` → `out/reel_v1.mp4`.
- `python -m reelkit check <proyecto> --version v1 --times 0.5 6 12 20 …` → lo que se escucha con música, LUFS y una
  hoja de fotogramas `out/check_v1.jpg`. **Mírala** con Read: textos no tapados, cartel de nombre visible, título legible.
- Avisa al usuario que tú no puedes escuchar: que lo revise con audífonos y te diga el segundo exacto de cada problema.
- Cada feedback → mapea el segundo del reel al segmento (la salida de build lista los tiempos acumulados), corrige
  `reel.toml`, `verify`, y compila una versión nueva (v2, v3…). Nunca sobrescribas la versión que el usuario está revisando.

## Referencia rápida de reel.toml

`[[segment]]`: `id`, `src` (nombre del archivo sin extensión), `in`, `out`, `tag = ["NOMBRE", "cargo"]`, `retag`,
`chip`, `hook`, `repair`, `fix = { palabra_mal_transcrita = "corrección" }`, `broll`, `title`, `cta`, `drop`, `vo`,
`focus_x` (0–1, para recortar videos horizontales a vertical), `punch`.
Texto: `{palabra}` = caja de acento, `|` = salto de línea. `[captions] highlight` = palabras en amarillo,
`replace` = correcciones globales (`"re:^regex" = "TEXTO"`).
