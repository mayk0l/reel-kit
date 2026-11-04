"""Step 1: analyse every raw video -> media.json, audio_levels.tsv, contact sheets, transcripts."""
import json
import subprocess

from PIL import Image, ImageDraw, ImageFont

from . import audio, gpu
from .project import Project
from .tools import duration, loudness, probe, run


def media_info(p: Project):
    info = {}
    for v in p.videos():
        d = probe(p.tools, v)
        vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
        rot = next((sd.get("rotation") for sd in vs.get("side_data_list", []) if "rotation" in sd), 0)
        w, h = vs.get("width", 0), vs.get("height", 0)
        if abs(int(rot or 0)) in (90, 270):
            w, h = h, w
        info[v.stem] = {"file": str(v.relative_to(p.root)), "duration": float(d["format"].get("duration", 0)),
                        "width": w, "height": h, "fps": vs.get("r_frame_rate"), "codec": vs.get("codec_name"),
                        "transfer": vs.get("color_transfer", ""), "has_audio": any(s["codec_type"] == "audio" for s in d["streams"])}
    (p.work / "media.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    return info


def contact_sheets(p: Project, info, frames=8):
    sheets = p.work / "sheets"
    sheets.mkdir(exist_ok=True)
    rows = []
    for stem, m in info.items():
        dst = sheets / f"{stem}.jpg"
        if not dst.exists():
            fps = max(frames / max(m["duration"], 0.5), 0.01)
            run([p.tools.ffmpeg, "-v", "error", "-y", "-i", p.media(stem), "-vf",
                 f"fps={fps:.4f},scale=160:-2,tile={frames}x1", "-frames:v", "1", "-update", "1", dst], check=False)
        if dst.exists():
            rows.append((stem, dst))
    # overview pages with labels, 9 clips per page
    font = ImageFont.load_default()
    for k in range(0, len(rows), 9):
        imgs = [(s, Image.open(f)) for s, f in rows[k:k + 9]]
        wmax = max(i.width for _, i in imgs) + 110
        page = Image.new("RGB", (wmax, sum(i.height for _, i in imgs)), "black")
        y = 0
        for s, i in imgs:
            page.paste(i, (110, y))
            ImageDraw.Draw(page).text((6, y + i.height // 2), s, fill="white", font=font)
            y += i.height
        page.save(sheets / f"overview_{k // 9:02d}.jpg", quality=85)


def levels(p: Project, info):
    lines = ["clip\tdur_s\tLUFS\tLRA\ttrue_peak"]
    for stem, m in info.items():
        if m["has_audio"]:
            L = loudness(p.tools, p.media(stem))
            lines.append(f"{stem}\t{m['duration']:.1f}\t{L['lufs']}\t{L['lra']}\t{L['true_peak']}")
    (p.work / "audio_levels.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def transcribe_all(p: Project, info):
    (p.work / "transcripts").mkdir(exist_ok=True)
    for stem, m in info.items():
        if not m["has_audio"]:
            continue
        wav = p.wav(stem)
        if not wav.exists():
            audio.extract_wav(p.tools, p.media(stem), wav)
        dst = p.transcript(stem)
        if dst.exists():
            continue
        segs = gpu.transcribe(audio.load(wav), words=True, vad=True, context=True)
        data = [{"start": s.start, "end": s.end, "text": s.text.strip(),
                 "words": [{"s": w.start, "e": w.end, "w": w.word, "p": round(w.probability, 3)} for w in s.words]}
                for s in segs]
        dst.write_text(json.dumps({"file": stem, "duration": m["duration"], "segments": data}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"  transcrito {stem}: {len(data)} segmentos", flush=True)
    out = ["# OJO: los tiempos de Whisper suelen ir 0.3-1.0 s ADELANTADOS. Nunca cortes con ellos directo:",
           "# usa `reelkit energy` y `reelkit verify` para fijar cada entrada/salida.\n"]
    for stem in info:
        t = p.transcript(stem)
        if t.exists():
            d = json.loads(t.read_text(encoding="utf-8"))
            out.append(f"\n### {stem} ({d['duration']:.0f}s)")
            out += [f"[{s['start']:6.1f}-{s['end']:6.1f}] {s['text']}" for s in d["segments"]]
    (p.work / "all_transcripts.txt").write_text("\n".join(out) + "\n", encoding="utf-8")


def ingest(p: Project):
    print(f"Videos en {p.raw}: {len(p.videos())}")
    info = media_info(p)
    print("· niveles de audio");  levels(p, info)
    print("· hojas de miniaturas"); contact_sheets(p, info)
    print("· transcripción (Whisper)"); transcribe_all(p, info)
    hdr = [s for s, m in info.items() if m["transfer"] in ("arib-std-b67", "smpte2084")]
    print(f"Listo -> {p.work}  ({len(hdr)} clips HDR se convertirán a SDR automáticamente)")
