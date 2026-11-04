"""Step 3: reel.toml -> finished vertical reel.
pieces (tone-mapped, reframed, zoom moves, per-piece audio chain) -> concat -> music ducked under the voice
-> captions + motion graphics (ASS) -> H.264/AAC at -14 LUFS."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from . import audio, gpu
from .graphics import Overlay
from .project import Project
from .restore import restored_audio
from .tools import duration, loudness, probe, run

HDR = ("arib-std-b67", "smpte2084")


def _transfer(p, stem, cache={}):
    if stem not in cache:
        info = p.work / "media.json"
        meta = json.loads(info.read_text(encoding="utf-8")) if info.exists() else {}
        if stem in meta:
            cache[stem] = meta[stem]["transfer"]
        else:
            vs = next(s for s in probe(p.tools, p.media(stem))["streams"] if s["codec_type"] == "video")
            cache[stem] = vs.get("color_transfer", "")
    return cache[stem]


def video_filter(p, seg, src, dur, zoom):
    c = p.cfg["project"]
    Wd, Hd, fps = c["width"], c["height"], c["fps"]
    vf = []
    tr = _transfer(p, src)
    if tr in HDR:
        tin = "arib-std-b67" if tr == "arib-std-b67" else "smpte2084"
        vf.append(f"zscale=tin={tin}:min=bt2020nc:pin=bt2020:t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,"
                  "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,eq=brightness=0.02:saturation=1.08")
    fx = float(seg.get("focus_x", 0.5))      # horizontal sources: which part of the frame to keep (0 left .. 1 right)
    vf.append(f"scale={Wd}:{Hd}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={Wd}:{Hd}:(iw-{Wd})*{fx}:(ih-{Hd})/2,fps={fps}")
    if zoom:
        n = max(1, round(dur * fps))
        vf.append(f"scale={Wd * 2}:{Hd * 2}:flags=lanczos,zoompan=z='{zoom.format(n=n)}':"
                  f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*0.42':d=1:s={Wd}x{Hd}:fps={fps}")
    vf.append("setsar=1,format=yuv420p")
    return ",".join(vf)


def render_piece(p, dst, seg, vsrc, va, dur, zoom=None, voice=None, post=audio.VOICE_POST):
    """voice=(src, start, gain_db): speech track from a clip (may be another clip) or, when src is a Path,
    from a restored WAV. B-roll own sound is muted."""
    T = p.tools
    cmd = [T.ffmpeg, "-y", "-v", "error", "-ss", f"{va:.3f}", "-t", f"{dur:.3f}", "-i", p.media(vsrc)]
    fade = f"aresample=48000,afade=t=in:d=0.02,afade=t=out:st={max(0, dur - 0.03):.3f}:d=0.03"
    if voice:
        vs, vstart, g = voice
        idx = 0
        if not (vs == vsrc and abs(vstart - va) < 1e-6):
            cmd += ["-ss", f"{vstart:.3f}", "-t", f"{dur:.3f}", "-i", vs if isinstance(vs, Path) else p.media(vs)]
            idx = 1
        afilt = f"[{idx}:a]aformat=channel_layouts=stereo,volume={g:.2f}dB,{post},{fade}[a]"
    else:
        afilt = f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a]"
    fc = f"[0:v]{video_filter(p, seg, vsrc, dur, zoom)}[v];{afilt}"
    run(cmd + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "ffv1", "-level", "3",
               "-c:a", "pcm_s16le", "-ar", "48000", "-t", f"{dur:.3f}", dst])
    return duration(T, dst)


def build(p: Project, version="v1"):
    T, cfg = p.tools, p.cfg
    if T.missing():
        raise SystemExit("Faltan herramientas: " + "; ".join(T.missing()) + "  (corre: python -m reelkit doctor)")
    st, au = cfg["style"], cfg["audio"]
    pieces_dir = p.out / "pieces" / version
    shutil.rmtree(pieces_dir, ignore_errors=True)
    pieces_dir.mkdir(parents=True)

    # ------------------------------------------------------------ pieces
    timeline, t, prev_chip = [], 0.0, None
    for seg in p.segments:
        sid = seg["id"]
        section_start = bool(seg.get("hook")) or (seg.get("chip") and seg.get("chip") != prev_chip)
        prev_chip = seg.get("chip", prev_chip)
        if seg.get("vo") or seg.get("broll"):
            if seg.get("vo"):
                vs, va, vb = seg["vo"]["src"], seg["vo"]["in"], seg["vo"]["out"]
                dur = vb - va
                g = au["voice_lufs"] - loudness(T, p.media(vs), va, dur)["lufs"]
                voice, src_words = (vs, va, g), (vs, va, vb)
            else:
                dur, voice, src_words = seg["out"] - seg["in"], None, None
            zoom = "1+0.06*on/{n}" if st["punch_zoom"] else None
            name = f"{len(timeline):03d}_{sid}.mkv"
            real = render_piece(p, pieces_dir / name, seg, seg["src"], seg["in"], dur, zoom, voice)
            timeline.append(dict(seg=seg, name=name, words=src_words, a=src_words[1] if src_words else seg["in"],
                                 b=src_words[2] if src_words else seg["out"], src=src_words[0] if src_words else None,
                                 t0=t, t1=t + real))
            t += real
        else:
            x = audio.load(p.wav(seg["src"]))
            if seg.get("restore"):      # destroyed take: neural restoration, then a gentle chain
                rwav, roff = restored_audio(p, seg["src"], seg["in"], seg["out"])
                g = au["voice_lufs"] - loudness(T, rwav, seg["in"] - roff, seg["out"] - seg["in"])["lufs"]
                post = audio.RESTORED_POST
            else:
                g = seg.get("voice_lufs", au["voice_lufs"] - (1.5 if seg.get("repair") else 0)) - \
                    loudness(T, p.media(seg["src"]), seg["in"], seg["out"] - seg["in"])["lufs"]
                post = seg.get("post") or (audio.REPAIR_POST if seg.get("repair") else audio.VOICE_POST)
            parts = audio.trim_pauses(x, seg["in"], seg["out"], au["pause_max"], au["pause_keep"])
            for k, (a, b) in enumerate(parts):
                base = 1.07 if (st["jumpcut_zoom"] and k % 2 == 1) else 1.0
                zoom = None
                if st["punch_zoom"] and k == 0 and (section_start or seg.get("punch")):
                    zoom = f"{base}+0.07*pow(max(0,1-on/10),3)"
                elif base != 1.0:
                    zoom = f"{base}"
                name = f"{len(timeline):03d}_{sid}.mkv"
                voice = (rwav, a - roff, g) if seg.get("restore") else (seg["src"], a, g)
                real = render_piece(p, pieces_dir / name, seg, seg["src"], a, b - a, zoom, voice, post)
                timeline.append(dict(seg=seg, name=name, src=seg["src"], a=a, b=b, t0=t, t1=t + real))
                t += real
        print(f"  {timeline[-1]['t1']:6.2f}s  {sid}", flush=True)
    total = t

    for q in timeline:
        if q["src"]:
            for issue in audio.edge_issues(audio.load(p.wav(q["src"])), q["a"], q["b"]):
                print(f"  ⚠ {q['seg']['id']} {q['src']} {q['a']:.2f}-{q['b']:.2f}: {issue}")

    (pieces_dir / "concat.txt").write_text("".join(f"file '{q['name']}'\n" for q in timeline), encoding="utf-8")
    full = p.out / f"full_{version}.mkv"
    run([T.ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", full], cwd=pieces_dir)

    # ------------------------------------------------------------ music, ducked under the voice
    mix = p.out / f"mix_{version}.wav"
    mf, mc = p.music_file(), cfg["music"]
    if mf and mf.exists():
        drop_piece = next((q for q in timeline if q["seg"].get("drop")), timeline[0])
        m_start = max(0.0, mc["drop_at"] - drop_piece["t0"])
        m_gain = mc["level_lufs"] - loudness(T, mf, m_start, total)["lufs"]
        warn_music_gaps(T, mf, m_start, total)
        run([T.ffmpeg, "-y", "-v", "error", "-i", full, "-ss", f"{m_start:.3f}", "-t", f"{total:.3f}", "-i", mf,
             "-filter_complex",
             f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={m_gain:.2f}dB,"
             f"afade=t=in:d=0.4,afade=t=out:st={max(0, total - 2.5):.3f}:d=2.5[m];"
             "[0:a]asplit=2[v][key];[m][key]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=450[md];"
             "[v][md]amix=inputs=2:normalize=0[out]", "-map", "[out]", "-c:a", "pcm_s24le", mix])
        print(f"  música desde {m_start:.2f}s del tema ({m_gain:+.1f} dB)")
    else:
        run([T.ffmpeg, "-y", "-v", "error", "-i", full, "-vn", "-c:a", "pcm_s24le", mix])

    # ------------------------------------------------------------ graphics
    ov = Overlay(st["accent"], st["dark"])
    ov.captions(caption_chunks(p, timeline))
    tags_done, chip_order, chip_span, first = set(), [], {}, {}
    for q in timeline:
        first.setdefault(q["seg"]["id"], q)
    for q in timeline:
        seg = q["seg"]
        last = max(r["t1"] for r in timeline if r["seg"] is seg)
        if q is first[seg["id"]]:
            if seg.get("hook"):
                ov.headline(q["t0"], last, seg["hook"])
            tag = tuple(seg.get("tag", ()))
            if tag and (tag not in tags_done or seg.get("retag")):
                tags_done.add(tag)
                ov.lower_third(q["t0"] + 0.15, min(q["t0"] + 3.2, total), tag[0], tag[1] if len(tag) > 1 else "")
            if seg.get("drop") and mf:
                ov.flash(q["t0"])
        if seg.get("chip"):
            if seg["chip"] not in chip_span:
                chip_order.append(seg["chip"])
                chip_span[seg["chip"]] = [q["t0"], q["t1"]]
            chip_span[seg["chip"]][1] = q["t1"]
    for i, c in enumerate(chip_order, 1):
        ov.chip(*chip_span[c], c, i if st["chip_numbers"] else None)
    tx = cfg["text"]
    title = [q for q in timeline if q["seg"].get("title")]
    if title and tx["title"]:
        ov.card(title[0]["t0"], title[-1]["t1"], tx["title"], tx["title_sub"])
    cta = [q for q in timeline if q["seg"].get("cta")]
    if cta and tx["cta"]:
        ov.card(cta[0]["t0"], total, tx["cta"], tx["cta_sub"], arrow=True, credit=mc["credit"])
    ass = p.out / f"reel_{version}.ass"
    ov.write(ass)
    p.fonts_dir()

    # ------------------------------------------------------------ encode (two-pass loudnorm)
    tl = au["target_lufs"]
    err = run([T.ffmpeg, "-hide_banner", "-i", mix, "-af", f"loudnorm=I={tl}:TP=-1.5:LRA=9:print_format=json",
               "-f", "null", "-"]).stderr
    ln = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    af = (f"loudnorm=I={tl}:TP=-1.5:LRA=9:measured_I={ln['input_i']}:measured_TP={ln['input_tp']}:"
          f"measured_LRA={ln['input_lra']}:measured_thresh={ln['input_thresh']}:offset={ln['target_offset']}:"
          "linear=true,aresample=192000,alimiter=limit=0.70:attack=1:release=60:level=0,aresample=48000")
    final = p.out / f"reel_{version}.mp4"
    burn = subprocess.Popen([T.ffmpeg_ass, "-v", "error", "-i", full.name, "-vf", f"ass={ass.name}:fontsdir=fonts",
                             "-map", "0:v", "-c:v", "rawvideo", "-f", "nut", "-"], stdout=subprocess.PIPE, cwd=p.out)
    enc = subprocess.run([T.ffmpeg, "-y", "-v", "error", "-f", "nut", "-i", "-", "-i", str(mix), "-map", "0:v", "-map", "1:a",
                          "-af", af, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                          "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)], stdin=burn.stdout)
    burn.stdout.close()
    burn.wait()
    if enc.returncode or burn.returncode:
        raise SystemExit("Falló el encode final")
    print(f"LISTO {total:.1f}s -> {final}")
    return final


def warn_music_gaps(T, mf, start, total):
    """Lesson: a track's breakdown (silences) once landed under the reel's ending. Warn before encoding."""
    raw = subprocess.run([T.ffmpeg, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{total:.3f}", "-i", str(mf), "-ac", "1",
                          "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    h = 4000
    db = 20 * np.log10(np.sqrt(np.mean(x[:len(x) // h * h].reshape(-1, h) ** 2, axis=1)) + 1e-9)
    gaps = [round(i * 0.5, 1) for i, v in enumerate(db) if v < -40 and i * 0.5 < total - 3]
    if gaps:
        print(f"  ⚠ la música tiene silencios en el reel en {gaps[:12]} s: mueve drop_at / el segmento con drop "
              "o usa `reelkit music-profile` para elegir otro tramo")


# ---------------------------------------------------------------- captions
def _cleaner(p, seg):
    rep = p.cfg["captions"]["replace"]
    fixes = {k.lower(): v for k, v in seg.get("fix", {}).items()}

    def clean(w):
        core = w.strip().strip(",.¿?¡!…;:\"'")
        for k, v in rep.items():
            if k.startswith("re:") and re.match(k[3:], core, re.I):
                return v.upper()
            if k.lower() == core.lower():
                return v.upper()
        return fixes.get(core.lower(), core).upper()
    return clean


def caption_chunks(p, timeline, max_words=3, max_chars=18):
    """Re-transcribe each voice segment on its own (no VAD/context: tighter word times), map words through
    the jump cuts and group them into short karaoke chunks."""
    hl = {h.upper() for h in p.cfg["captions"]["highlight"]}
    groups = {}
    for q in timeline:
        if q["src"]:
            groups.setdefault((q["seg"]["id"], q["src"]), []).append(q)
    chunks = []
    for (_, src), parts in groups.items():
        seg = parts[0]["seg"]
        clean = _cleaner(p, seg)
        x = audio.load(p.wav(src))
        a, b = parts[0]["a"], parts[-1]["b"]
        pad = np.zeros(8000, np.float32)
        segs = gpu.transcribe(np.concatenate([pad, x[int(a * audio.SR):int(b * audio.SR)], pad]))
        words = []
        for s in segs:
            for w in s.words:
                ws, we = a + w.start - 0.5, a + w.end - 0.5
                q = next((q for q in parts if q["a"] - 0.15 <= ws < q["b"]), None)
                txt = clean(w.word)
                if not q or not txt or (words and words[-1]["txt"].endswith(txt) and words[-1]["txt"] != txt):
                    continue
                if words and not any(ch.isalnum() for ch in txt):      # "60" + "%" -> "60%"
                    words[-1]["txt"] += txt
                    words[-1]["e"] = min(q["t1"], q["t0"] + we - q["a"])
                    continue
                words.append(dict(txt=txt, raw=w.word.strip(), kw=any(k in hl for k in txt.split()),
                                  s=q["t0"] + max(0.0, ws - q["a"]), e=min(q["t1"], q["t0"] + we - q["a"]), end=q["t1"]))
        cur = []
        for w in words:
            if cur and (len(cur) >= max_words or sum(len(c["txt"]) for c in cur) + len(w["txt"]) > max_chars):
                chunks.append(cur)
                cur = []
            cur.append(w)
            if w["raw"][-1:] in ",.?!" and len(cur) >= 2:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
    return chunks
