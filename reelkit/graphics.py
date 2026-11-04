"""Motion graphics rendered by libass (ASS subtitles), laid out with real font metrics.

Elements: karaoke captions with a sliding highlight box, animated lower thirds, numbered section chips,
slam-in hook headline with keyword boxes, title / CTA cards, drop flash.

Text markup used in reel.toml: "{palabra}" = keyword on an accent box, "|" = line break.

libass metric calibration for Poppins (measured): em = 0.5675 * Fontsize; with \\an5 at y the caps are
centred at y - 0.060*S (CAP_DY, measured in pixels), cap height = 0.40*S; with \\an7 at y the cap top is y + 0.24*S, baseline y + 0.64*S.
"""
import re
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
EM, W_CORR = 0.5675, 0.985
W, H = 1080, 1920
CAP_DY = -0.060      # with \\an5 at y, the caps' visual centre sits at y + CAP_DY*S
CX = W / 2


def bgr(hexcolor):
    h = hexcolor.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


@lru_cache(None)
def _font(weight, size):
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), size=size)


def text_w(text, S, weight="ExtraBold", spacing=0.0):
    """Rendered width in px of `text` at ASS Fontsize S (spacing = \\fsp px per char)."""
    if not text:
        return 0.0
    return _font(weight, round(S * EM * 4) / 4).getlength(text) * W_CORR + spacing * len(text)


def rrect(w, h, r):
    r = max(0.0, min(r, h / 2, w / 2))
    k = r * 0.4477
    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    return " ".join(v if isinstance(v, str) else f(float(v)) for v in [
        "m", r, 0.0, "l", w - r, 0.0, "b", w - k, 0.0, w, k, w, r, "l", w, h - r, "b", w, h - k, w - k, h, w - r, h,
        "l", r, h, "b", k, h, 0.0, h - k, 0.0, h - r, "l", 0.0, r, "b", 0.0, k, k, 0.0, r, 0.0])


def parse_marked(line):
    """'DE {1 SEMANA}' -> [('DE ', False), ('1 SEMANA', True)]"""
    parts, pos = [], 0
    for m in re.finditer(r"\{(.*?)\}", line):
        if m.start() > pos:
            parts.append((line[pos:m.start()], False))
        parts.append((m.group(1), True))
        pos = m.end()
    if pos < len(line):
        parts.append((line[pos:], False))
    return parts


def layout(tokens, S, gap, hl_gap, max_w=None):
    """tokens: [(text, highlighted)]. Returns (font size, [(text, hl, center_x, width)]) centred on the frame."""
    def widths(sz):
        return [text_w(t, sz) for t, _ in tokens]
    def total(sz):
        ws = widths(sz)
        gaps = [(hl_gap if (tokens[i][1] or tokens[i + 1][1]) else gap) * sz for i in range(len(tokens) - 1)]
        return sum(ws) + sum(gaps), ws, gaps
    tot, ws, gaps = total(S)
    if max_w and tot > max_w:
        S *= max_w / tot
        tot, ws, gaps = total(S)
    x, out = CX - tot / 2, []
    for i, ((t, hl), w) in enumerate(zip(tokens, ws)):
        out.append((t, hl, x + w / 2, w))
        x += w + (gaps[i] if i < len(gaps) else 0)
    return S, out


def tokens_of(line):
    """'¿CÓMO USAN LA {IA}' -> word tokens, the braces part kept together as one highlighted token."""
    toks = []
    for t, hl in parse_marked(line):
        if hl:
            toks.append((t.strip(), True))
        else:
            toks += [(w, False) for w in t.split()]
    return toks


def ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


class Overlay:
    def __init__(self, accent="#FFD400", dark="#0B0B0F"):
        self.ACC, self.DARK, self.WHITE, self.BLACK = bgr(accent), bgr(dark), "&HFFFFFF&", "&H000000&"
        self.events = []

    # ------------------------------------------------------------------ primitives
    def add(self, t0, t1, text, layer=0):
        if t1 - t0 >= 0.02:
            self.events.append((layer, t0, f"Dialogue: {layer},{ts(t0)},{ts(t1)},Base,,0,0,0,,{text}"))

    def shape(self, t0, t1, w, h, r, color, alpha="00", place="", tags="", layer=0, an=7):
        self.add(t0, t1, f"{{\\an{an}{place}\\bord0\\shad0\\1c{color}\\1a&H{alpha}&{tags}\\p1}}{rrect(w, h, r)}{{\\p0}}", layer)

    def txt(self, S, color=None, weight="ExtraBold", bord=0.0, shad=0.0, blur=0.0, spacing=0.0):
        fn = "Poppins ExtraBold" if weight == "ExtraBold" else "Poppins SemiBold"
        t = f"\\fn{fn}\\fs{S:.1f}\\1c{color or self.WHITE}\\3c{self.BLACK}\\4c{self.BLACK}"
        if bord or shad:
            t += f"\\bord1\\3a&HFF&\\shad{max(shad, 0.02 * S):.1f}\\4a&H8C&\\blur{max(blur, 0.045 * S):.1f}"
        else:
            t += "\\bord0\\shad0\\blur0"
        return t + (f"\\fsp{spacing:.1f}" if spacing else "")

    # ------------------------------------------------------------------ karaoke captions
    def captions(self, chunks, cy=1290, S=92, max_w=940):
        """chunks: list of lists of words {txt, s, e, kw, end}. A box slides to the word being spoken."""
        # fast speech: word starts must strictly increase, and chunks must never overlap
        prev = -1.0
        for chunk in chunks:
            for w in chunk:
                w["s"] = max(w["s"], prev + 0.06)
                prev = w["s"]
        for ci, chunk in enumerate(chunks):
            Ss, placed = layout([(w["txt"], False) for w in chunk], S, gap=0.40, hl_gap=0.40, max_w=max_w)
            pad_x, box_h = 0.15 * Ss, 0.40 * Ss + 0.34 * Ss
            by = cy + CAP_DY * Ss
            end = min(max(chunk[-1]["e"], chunk[-1]["s"] + 0.2) + 0.35, chunk[-1]["end"])
            if ci + 1 < len(chunks):
                nxt = chunks[ci + 1][0]["s"]
                end = nxt if nxt - chunk[-1]["s"] < 0.9 else min(end, nxt)
            st = dict(bord=0.055 * Ss, shad=0.03 * Ss, blur=1.2)
            for i, w in enumerate(chunk):
                t0 = w["s"]
                t1 = chunk[i + 1]["s"] if i + 1 < len(chunk) else end
                if t1 - t0 < 0.03:
                    continue
                last = i == len(chunk) - 1
                fade = "\\fad(0,90)" if last else ""
                cxs = [c for _, _, c, _ in placed]
                bw = placed[i][3] + 2 * pad_x
                if i == 0:
                    anim = f"\\pos({cxs[i]:.1f},{by:.1f})\\fscx60\\fscy60\\t(0,110,0.6,\\fscx100\\fscy100)"
                else:
                    pw = placed[i - 1][3] + 2 * pad_x
                    anim = (f"\\move({cxs[i - 1]:.1f},{by:.1f},{cxs[i]:.1f},{by:.1f},0,90)"
                            f"\\fscx{100 * pw / bw:.1f}\\t(0,90,0.6,\\fscx100)")
                self.shape(t0, t1, bw, box_h, box_h * 0.22, self.ACC, tags=anim + fade, layer=1, an=5)
                for j, (word, _, cx, _) in enumerate(placed):
                    if j == i:
                        style = self.txt(Ss, self.DARK)
                    else:
                        style = self.txt(Ss, self.ACC if chunk[j]["kw"] else self.WHITE, **st)
                    pop = "\\fscx86\\fscy86\\t(0,120,0.6,\\fscx100\\fscy100)\\fad(70,0)" if i == 0 else ""
                    self.add(t0, t1, f"{{\\an5\\pos({cx:.1f},{cy:.1f}){style}{pop}{fade}}}{word}", layer=2)

    # ------------------------------------------------------------------ lower third
    def lower_third(self, t0, t1, name, role="", x0=60, y=1420):
        Sn, Sr = 78, 50
        nw, rw = text_w(name, Sn), text_w(role, Sr, "SemiBold") if role else 0
        bar, gap, pad = 10, 22, 30
        name_cap = y + 0.24 * Sn
        name_base = y + 0.64 * Sn
        ry = name_base + 18 - 0.24 * Sr
        bottom = (ry + 0.64 * Sr + 0.14 * Sr) if role else name_base
        top, bot = name_cap - 24, bottom + 24
        pw, ph = bar + gap + max(nw, rw) + pad, bot - top
        tx = x0 + bar + gap
        out = "\\fad(0,260)"
        wipe = lambda d0, d1: f"\\clip({x0},{top:.0f},{x0 + 1},{bot:.0f})\\t({d0},{d1},0.45,\\clip({x0},{top:.0f},{x0 + pw:.0f},{bot:.0f}))"
        self.shape(t0, t1, pw, ph, 14, self.DARK, alpha="38", place=f"\\pos({x0},{top:.1f})", tags=wipe(90, 430) + out, layer=3)
        self.shape(t0, t1, bar, ph, 5, self.ACC, place=f"\\pos({x0},{top:.1f})",
                   tags="\\fscy0\\t(0,240,0.5,\\fscy100)" + out, layer=4)
        self.add(t0, t1, f"{{\\an7\\move({tx - 26},{y:.1f},{tx},{y:.1f},110,470){self.txt(Sn)}{wipe(110, 470)}{out}}}{name}", layer=5)
        if role:
            self.add(t0, t1, f"{{\\an7\\move({tx - 18},{ry:.1f},{tx},{ry:.1f},260,600){self.txt(Sr, '&HDADADA&', 'SemiBold')}"
                             f"\\alpha&HFF&\\t(260,560,\\alpha&H00&){out}}}{role}", layer=5)

    # ------------------------------------------------------------------ section chip
    def chip(self, t0, t1, label, num=None, cy=300):
        S, sp = 58, 2.5
        n = f"{num:02d}" if num else ""
        full = f"{n}   {label}" if n else label
        w = text_w(full, S, spacing=sp) + 2 * 34
        h = 0.40 * S + 2 * 24
        move = f"\\move({CX:.0f},{cy - 26:.1f},{CX:.0f},{cy:.1f},0,300)"
        common = "\\fscx90\\fscy90\\t(0,300,0.5,\\fscx100\\fscy100)\\fad(200,220)"
        self.shape(t0, t1, w, h, h / 2, self.ACC, place=move, tags=common, layer=3, an=5)
        ty = lambda y0: y0 - CAP_DY * S
        label_txt = (f"{{\\1a&H70&}}{n}{{\\1a&H00&}}   {label}" if n else label)
        self.add(t0, t1, f"{{\\an5\\move({CX:.0f},{ty(cy - 26):.1f},{CX:.0f},{ty(cy):.1f},0,300)"
                         f"{self.txt(S, self.DARK, spacing=sp)}{common}}}{label_txt}", layer=4)

    # ------------------------------------------------------------------ hook headline
    def _marked_line(self, t0, t1, line, yc, S, max_w, delay, enter, box_pad=0.16, layer=3):
        """One line of big text; {highlighted} tokens get an accent box that wipes in after the line enters."""
        Ss, placed = layout(tokens_of(line), S, gap=0.30, hl_gap=0.30 + 2 * box_pad + 0.08, max_w=max_w)
        box_h = 0.40 * Ss + 2 * 0.17 * Ss
        st = dict(bord=0.05 * Ss, shad=0.03 * Ss, blur=1)
        for t, hl, cx, w in placed:
            if hl:
                bx, bw = cx - w / 2 - box_pad * Ss, w + 2 * box_pad * Ss
                by = yc + CAP_DY * Ss - box_h / 2
                self.shape(t0, t1, bw, box_h, box_h * 0.2, self.ACC, place=f"\\pos({bx:.1f},{by:.1f})",
                           tags=(f"\\clip({bx:.0f},{by:.0f},{bx + 1:.0f},{by + box_h:.0f})"
                                 f"\\t({delay + 140},{delay + 360},0.5,\\clip({bx:.0f},{by:.0f},{bx + bw:.0f},{by + box_h:.0f}))"
                                 "\\fad(0,200)"), layer=layer - 1)
                color = f"\\t({delay + 180},{delay + 320},\\1c{self.DARK}\\bord0\\shad0\\blur0)"
            else:
                color = ""
            self.add(t0, t1, f"{{\\an5{enter(cx, yc)}{self.txt(Ss, **st)}{color}\\fad(0,200)}}{t}", layer=layer)
        return box_h

    def headline(self, t0, t1, text, top=470, S=132, max_w=960):
        lines = text.split("|")
        box_h = 0.40 * S + 2 * 0.17 * S
        step = box_h + 26
        for k, line in enumerate(lines):
            d = k * 230
            slam = lambda cx, y, d=d: (f"\\pos({cx:.1f},{y:.1f})\\fscx128\\fscy128\\alpha&HFF&\\blur8"
                                       f"\\t({d},{d + 170},0.5,\\fscx100\\fscy100\\alpha&H00&\\blur{0.045 * S:.1f})")
            self._marked_line(t0, t1, line, top + k * step, S, max_w, d, slam)

    def card(self, t0, t1, text, sub="", cy=860, S=112, arrow=False, credit="", max_w=940):
        lines = text.split("|")
        box_h = 0.40 * S + 2 * 0.17 * S
        step = box_h + 14
        y0 = cy - step * (len(lines) - 1) / 2
        for k, line in enumerate(lines):
            d = 120 + k * 110
            rise = lambda cx, y, d=d: (f"\\move({cx:.1f},{y + 44:.1f},{cx:.1f},{y:.1f},{d},{d + 380})"
                                       f"\\alpha&HFF&\\t({d},{d + 300},\\alpha&H00&)")
            self._marked_line(t0, t1, line, y0 + k * step, S, max_w, d + 60, rise)
        yb = y0 + step * (len(lines) - 1) + box_h / 2 + 40
        dd = 120 + len(lines) * 110
        self.shape(t0, t1, 150, 7, 3.5, self.ACC, place=f"\\pos({CX:.0f},{yb:.1f})",
                   tags=f"\\fscx0\\t({dd},{dd + 320},0.5,\\fscx100)\\fad(0,200)", layer=3, an=5)
        if sub:
            Sb = 52
            self.add(t0, t1, f"{{\\an5\\pos({CX:.0f},{yb + 66:.1f}){self.txt(Sb, weight='SemiBold', bord=2.4, shad=1, blur=1, spacing=1.5)}"
                             f"\\alpha&HFF&\\t({dd + 150},{dd + 500},\\alpha&H00&)\\fad(0,200)}}{sub}", layer=3)
        if arrow:
            ya = yb + 180
            chevron = "m 0 0 l 30 30 l 60 0 l 70 10 l 30 50 l -10 10"
            t = t0 + (dd + 500) / 1000
            k = 0
            while t + 0.35 < t1:
                y1, y2 = (ya, ya + 22) if k % 2 == 0 else (ya + 22, ya)
                fade_in = "\\fad(200,0)" if k == 0 else ""
                self.add(t, min(t + 0.42, t1), f"{{\\an5\\move({CX:.0f},{y1:.1f},{CX:.0f},{y2:.1f},0,420)\\bord0\\shad0\\1c{self.ACC}"
                                               f"{fade_in}\\p1}}{chevron}{{\\p0}}", layer=3)
                t += 0.42
                k += 1
        if credit:
            self.add(t0, t1, f"{{\\an2\\pos({CX:.0f},1580){self.txt(24, weight='SemiBold', bord=1.5, blur=0.6)}"
                             f"\\alpha&H50&\\fad(400,200)}}{credit}", layer=3)

    def flash(self, t, dur=0.28):
        self.shape(t, t + dur, W, H, 0, self.WHITE, alpha="55", place="\\pos(0,0)",
                   tags=f"\\t(0,{int(dur * 1000)},\\1a&HFF&)", layer=6)

    # ------------------------------------------------------------------ output
    def write(self, path):
        header = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
            "YCbCr Matrix: TV.709\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            "Style: Base,Poppins ExtraBold,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        body = "\n".join(e for _, _, e in sorted(self.events, key=lambda e: (e[1], e[0])))
        Path(path).write_text(header + body + "\n", encoding="utf-8")
