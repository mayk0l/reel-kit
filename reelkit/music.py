"""Royalty-free music: search Openverse (CC0 / CC BY), download, map the track and find drops."""
import json
import subprocess
import urllib.parse
import urllib.request

import numpy as np

API = "https://api.openverse.org/v1/audio/"


def search(query, licenses="cc0,by", n=15):
    q = urllib.parse.urlencode({"q": query, "license": licenses, "page_size": n})
    with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "reelkit"}), timeout=30) as r:
        res = json.load(r)["results"]
    for x in res:
        dur = (x.get("duration") or 0) / 1000
        print(f"{x['license']:>4} {x.get('license_version') or '':>4} {dur:6.0f}s  {x['title'][:48]:<48} | "
              f"{(x.get('creator') or '')[:22]:<22} | {x['url']}\n      {x.get('foreign_landing_url', '')}")
    print("\nCC0 = sin crédito. CC BY = gratis pero hay que dar crédito (autor, título, licencia) en el post.")
    print("Prefiere temas completos (>90 s) a loops cortos.")


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "reelkit"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        f.write(r.read())
    print(f"guardado {dst}")


def _decode(tools, path, sr, lowpass=None):
    af = ["-af", f"lowpass=f={lowpass}"] if lowpass else []
    raw = subprocess.run([tools.ffmpeg, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), *af, "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def profile(tools, path):
    """Per-second level (full band and <120 Hz) + candidate drops (bass jumps >= 8 dB), refined to 10 ms.
    Avoid stretches with silences (breakdowns) under the end of the reel."""
    full = _decode(tools, path, 8000)
    low = _decode(tools, path, 4000, lowpass=120)
    per_s = lambda x, sr: 20 * np.log10(np.sqrt(np.mean(x[:len(x) // sr * sr].reshape(-1, sr) ** 2, 1)) + 1e-9)
    F, L = per_s(full, 8000), per_s(low, 4000)
    print("seg: nivel_total/graves (dB)")
    cells = [f"{i}:{F[i]:.0f}/{L[i]:.0f}" for i in range(len(F))]
    for i in range(0, len(cells), 10):
        print("  " + " ".join(cells[i:i + 10]))
    drops = []
    for i in range(4, len(L)):
        if L[i] - np.mean(L[i - 4:i]) >= 8 and (not drops or i - drops[-1] > 8):
            drops.append(i)
    h = 40   # 10 ms at 4 kHz
    out = []
    for d in drops:
        seg = low[(d - 1) * 4000:(d + 1) * 4000]
        db = 20 * np.log10(np.sqrt(np.mean(seg[:len(seg) // h * h].reshape(-1, h) ** 2, 1)) + 1e-9)
        j = int(np.argmax(np.diff(db))) + 1
        out.append(round(d - 1 + j / 100, 2))
    silences = [i for i in range(len(F)) if F[i] < -45]
    print(f"\nDrops candidatos (s): {out}")
    if silences:
        print(f"Silencios/huecos (s): {silences[:40]}{' …' if len(silences) > 40 else ''}")
    return out
