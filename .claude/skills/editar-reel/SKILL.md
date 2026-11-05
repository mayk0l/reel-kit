---
name: editar-reel
description: Edita Reels verticales (Instagram/TikTok) a partir de entrevistas grabadas con celular usando reel-kit - analiza todos los videos, propone un guion con hook/intro/desarrollo/cierre, fija cortes verificados de oído, nivela y repara el audio, agrega música libre de derechos con ducking y motion graphics profesionales, y entrega un MP4 a -14 LUFS. Úsala cuando el usuario quiera armar, iterar o corregir un reel/video corto desde material propio, en Windows, macOS o Linux.
---

# Editar un Reel con reel-kit

Flujo probado en el Tech AI Summit: un reel resumen de varias entrevistas (`examples/reel.toml`) y reels de una
entrevista completa (`examples/entrevista.toml`). Los reels tuvieron buena respuesta: mantén este formato. Herramienta: el paquete `reelkit` de este repo
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
- **Pregunta quién es quién** si hay varios entrevistadores (describe ropa/aspecto y a quién entrevistó cada uno): el
  usuario puede pedir "un reel mío" o "uno de Matías". No adivines por el nombre.
- Mide el audio de cada entrevista candidata (recorte >0.9 FS, 250 Hz, 4.5–9 kHz con `spectrum`) **antes** de proponerla:
  una toma muy recortada genera quejas de "saturado" que no se arreglan del todo.
- Varios reels del mismo material: un proyecto por reel con `raw_dir`/`work_dir` apuntando al proyecto original
  (`"../evento/raw"`, `"../evento/analysis"`): no se re-transcribe nada. Se pueden armar en paralelo (la GPU aguanta dos
  Whisper large-v3 int8 en 6 GB).

## 2. Guion (pídele aprobación al usuario antes de cortar)

Estructura que funcionó:
- **HOOK (0–10 s)**: la frase más concreta y sorprendente, mejor con números ("de 1 semana a 2 horas"). Titular grande `hook = "DE {1 SEMANA}|A {2 HORAS}"`.
- **INTRO (~5 s)**: voz en off "hoy estamos en…" sobre b-roll del lugar + tarjeta de título (`[text] title`). El drop de la música cae aquí (`drop = true`).
- **DESARROLLO**: 3–4 bloques temáticos, cada uno con `chip` (se numeran solos). Deja que cada entrevistado **termine la idea**: el usuario prefirió contexto completo antes que frases sueltas.
- **CONCLUSIÓN**: el consejo más fuerte, con espacio suficiente.
- **CIERRE**: b-roll llamativo + CTA (`[text] cta`) con flecha animada.
**Formato "entrevista completa"** (también funcionó, 2:30–3:00, máximo de Instagram 3 min):
HOOK con la frase más fuerte sacada de una respuesta (se repite después en su contexto) → tarjeta de título sobre b-roll
(`ENTREVISTA AL CEO DE|{EMPRESA}`) → cada pregunta del entrevistador abre un bloque con `chip` y su respuesta completa →
CTA. Cartel con el nombre del entrevistador (`tag = ["MAYKOL", "Tech AI Summit"]`) y del entrevistado (`retag` al volver).
Saca: errores del entrevistador (dijo "Google" en vez de "Huawei"), autopresentaciones con nombres que no puedes
confirmar, frases repetidas, agradecimientos finales.
Presenta el guion como tabla: bloque, clip, tramo, frase. Con varias opciones, usa AskUserQuestion con el guion de cada
una en la vista previa. Evita datos dudosos que el entrevistado mismo no sabe confirmar.
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

**Muletillas y trabadas** (el usuario las nota siempre: "eh, eh…", "estamos… hoy estamos", "con… con personas"):
`python -m reelkit fillers <proyecto> SRC A B` sobre cada tramo de voz **antes** de compilar, sobre todo en las
presentaciones del entrevistador. Whisper no escribe los "eh" y con contexto "limpia" las repeticiones; `fillers` parte
en frases por las pausas reales, transcribe cada una sola y hace una prueba de eliminación (si al silenciar un bloque el
texto no cambia, era muletilla; solo en frases de ≤4 s, con más contexto Whisper rellena). Sirve también como mapa de
  frases con sus límites de energía para elegir cortes. Tiene falsos positivos: confirma con `verify` y corta saltándote el bloque (dos
segmentos del mismo `src`). Si la muletilla está pegada a una palabra sin silencio, corta en el valle más bajo y escucha
"inicio"/"final". Cuando el usuario reporte una muletilla, búscala tú (energía + palabras), no le pidas más detalles.

## 4. Audio

- Todo se nivela solo: voz a -16 LUFS por tramo, mezcla final a -14 LUFS (estándar Reels/TikTok).
- Si el usuario dice "suena saturado": `python -m reelkit spectrum <proyecto> SRC A B` y mide cuánto está recortado
  (muestras sobre 0.9 de escala: >5 % = recorte duro antes del AAC; voz limpia < 1 %). Para eso usa `repair = true`:
  declipper + quita retumbe + **baja** los agudos sobre 4 kHz (ahí está la distorsión) y deja 2 kHz para inteligibilidad;
  además ese tramo va 1.5 dB más bajo. Lección: subir presencia/agudos en una toma recortada la hace sonar MÁS saturada.
  Verifica que los dos canales no sean una pista de seguridad distinta antes de concluir.
- `restore = true` (VoiceFixer, opcional, `requirements-restore.txt` en otro venv + `REELKIT_RESTORE_PY`) reconstruye la
  voz con IA y reduce más la distorsión, pero puede deformar consonantes (convirtió "Shadow AI" en "Chabón AI").
  Úsalo solo si `verify` confirma que las palabras clave siguen entendiéndose, y deja que el usuario elija oyendo un A/B.
- Voz fina/áspera (el caso opuesto al micrófono pegado, p.ej. la entrevista de la Cámara de IA: 250 Hz −14, presencia −3,
  aspereza −21 dB): mide variantes hasta acercarte a la referencia limpia (≈ −3 / −12 / −26) y ponla en `[audio] post`
  (todo el proyecto) o `post` del segmento. Ejemplo: `post = "highpass=f=90,equalizer=f=200:t=q:w=1:g=3,highshelf=f=4500:g=-5,alimiter=limit=0.89"`
  reemplaza la cadena de ese segmento (cualquier filtro de audio de ffmpeg).
- B-roll: su sonido va **silenciado** (voces de fondo pueden decir groserías; pasó). La música lo cubre.
- Voz en off sobre otra toma: `vo = { src = "...", in = ..., out = ... }`.

## 5. Música (libre de derechos)

1. `python -m reelkit music-search "tech house"` (Openverse). CC0 = sin crédito; CC BY = crédito obligatorio
   (`[music] credit`, también en la descripción del post). Prefiere temas completos a loops.
2. `python -m reelkit music-get URL music/tema.mp3` y `python -m reelkit music-profile music/tema.mp3`.
3. Elige un drop tal que **desde el drop hasta el final del reel no haya huecos/silencios** del tema (pasó: el tema se
   apagaba bajo el cierre). `drop_at` = segundo exacto del drop; cae en el segmento con `drop = true`.
   La música baja sola bajo la voz (sidechain) y sube en b-roll y cierre.
4. Cuenta: el tema suena desde `drop_at − t_drop` hasta `drop_at − t_drop + duración_del_reel`; todo ese tramo debe ser
   continuo. En reels largos el drop puede ir a mitad del video (al empezar la 2ª o 3ª pregunta) como "segundo aire".
   `build` avisa (⚠) si la música cae en silencios.
5. Reel de ~3 min: necesitas ~3 min de tema continuo después de `drop_at − t_drop`. Si no alcanza, usa otro tema (del
   mismo artista para mantener la estética) y varía la música entre reels publicados seguidos. En Jamendo, Hasenchat
   tiene muchos temas CC BY 3.0 largos y continuos ("Mium (Tech House Mix)": groove de 7 a 345 s).

## 6. Compilar, revisar, iterar

- `python -m reelkit build <proyecto> --version v1` → `out/reel_v1.mp4`.
- `python -m reelkit check <proyecto> --version v1 --times 0.5 6 12 20 …` → lo que se escucha con música, LUFS, pico
  (debe quedar ≤ -1.5 dBTP) y una hoja de fotogramas `out/check_v1.jpg`. **Mírala** con Read: textos no tapados, cartel
  de nombre visible, título legible, nada encimado. Un subtítulo tenue en la hoja suele ser una captura en el fundido
  entre dos bloques (~160 ms), no falta de contraste: confírmalo con otro fotograma antes de cambiar el estilo.
- **Caras**: revisa 3–4 fotogramas del hook. Si el titular tapa la cara del entrevistado (pasó con UserEmotion), usa
  `hook_y` en el segmento (por defecto 470; ~930 = altura del pecho, entre la cara y los subtítulos).
- Instagram corta a los 3:00: deja el reel en ≤ 2:58 (saca saludos, "¿qué tal, cómo está?", comentarios del entrevistador).
- Estilo de gráficos que el usuario aprobó: sin fondos negros ni oscurecer la pantalla, sin contorno negro grueso (solo
  sombra suave), texto centrado dentro de las cajas amarillas. Si tocas `graphics.py`, mide el centrado en píxeles.
- Avisa al usuario que tú no puedes escuchar: que lo revise con audífonos y te diga el segundo exacto de cada problema.
- Cada feedback → mapea el segundo del reel al segmento (la salida de build lista los tiempos acumulados), corrige
  `reel.toml`, `verify`, y compila una versión nueva (v2, v3…). Nunca sobrescribas la versión que el usuario está revisando.

## 7. Entregar

- Ruta del MP4 + tabla de bloques con tiempos del reel + qué se sacó y por qué + qué debe revisar con audífonos.
- Si lo pide, descripción para el post: primera línea = el hook entre comillas; 3 viñetas con lo que aporta cada bloque;
  pregunta CTA; etiquetas `@[Empresa]` para que el usuario ponga las cuentas reales (no inventes handles); crédito de
  la música (obligatorio con CC BY); 6–9 hashtags. Primera persona si es "su" entrevista.

## Referencia rápida de reel.toml

`[[segment]]`: `id`, `src` (nombre del archivo sin extensión), `in`, `out`, `tag = ["NOMBRE", "cargo"]`, `retag`,
`chip`, `hook`, `repair`, `fix = { palabra_mal_transcrita = "corrección" }`, `broll`, `title`, `cta`, `drop`, `vo`,
`focus_x` (0–1, para recortar videos horizontales a vertical), `punch`, `hook_y`, `post` (cadena de audio propia),
`voice_lufs`, `restore`.
Texto: `{palabra}` = caja de acento, `|` = salto de línea. `[captions] highlight` = palabras en amarillo,
`replace` = correcciones globales (`"re:^regex" = "TEXTO"`; valor `""` borra la palabra, p.ej. `"re:^-gpt$" = ""`).
Las tablas inline de TOML van en **una sola línea**. Corrige en subtítulos lo que Whisper entiende mal por contexto
(ticketera, startup, ChatGPT, nombres de empresa) y avisa al usuario cuáles adivinaste.
