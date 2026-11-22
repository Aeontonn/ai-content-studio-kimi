#!/usr/bin/env python3
"""AI Content Studio - carousel renderer.

Turns a carousel spec (JSON) into finished Instagram slides using the brand
kit: PNG images (Pillow), an editable PowerPoint deck (python-pptx; opens in
PowerPoint, Keynote, Google Slides and imports into Canva), an optional PDF,
and an overview image for quick visual QA.

One layout engine builds a "scene" per slide; the PNG and PPTX backends both
draw that same scene, so the editable deck matches the images.

Usage
  python carousel.py render carousel.json --out exports/carousel-name [--pptx] [--pdf]
  python carousel.py validate carousel.json

Slide types: cover, text, list, quote, stat, image, cta
Emphasis: wrap words in **double asterisks** to color them with the accent.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

SLIDE_TYPES = ("cover", "text", "list", "quote", "stat", "image", "cta")
MAX_SLIDES = 20

FONT_DIRS = [
    Path("C:/Windows/Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts",
    Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"), Path.home() / "Library/Fonts",
]
FALLBACK_FONTS = {
    "bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf", "Arial Bold.ttf",
             "NotoSans-Bold.ttf", "Roboto-Bold.ttf", "Helvetica.ttc"],
    "regular": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "segoeui.ttf", "Arial.ttf",
                "NotoSans-Regular.ttf", "Roboto-Regular.ttf", "Helvetica.ttc"],
}
# Chinese-capable fonts: Windows (Microsoft YaHei, SimHei), macOS (PingFang, Hiragino, STHeiti),
# Linux (Noto Sans CJK / Source Han Sans, WenQuanYi). Any of them also contains Latin letters.
CJK_FONTS = {
    "bold": ["msyhbd.ttc", "msyh.ttc", "simhei.ttf", "PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Medium.ttc",
             "NotoSansCJK-Bold.ttc", "NotoSansSC-Bold.otf", "NotoSansSC-Bold.ttf", "SourceHanSansSC-Bold.otf",
             "wqy-zenhei.ttc", "wqy-microhei.ttc", "DroidSansFallbackFull.ttf"],
    "regular": ["msyh.ttc", "Deng.ttf", "simhei.ttf", "PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Light.ttc",
                "NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf", "NotoSansSC-Regular.ttf", "SourceHanSansSC-Regular.otf",
                "wqy-microhei.ttc", "wqy-zenhei.ttc", "DroidSansFallbackFull.ttf"],
}


# --------------------------------------------------------------------------- colors

def rgb(hex_color: str) -> Tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def luminance(hex_color: str) -> float:
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(bg: str, *candidates: str) -> str:
    """First candidate with WCAG AA contrast (4.5) on bg, else black or white."""
    for color in candidates:
        if color and contrast(bg, color) >= 4.5:
            return color
    return "#111111" if contrast(bg, "#111111") >= contrast(bg, "#FFFFFF") else "#FFFFFF"


# --------------------------------------------------------------------------- fonts

def find_font_file(names: List[str]) -> Optional[Path]:
    for folder in FONT_DIRS:
        if not folder.exists():
            continue
        for name in names:
            direct = folder / name
            if direct.exists():
                return direct
        try:
            for name in names:
                hit = next(folder.rglob(name), None)
                if hit:
                    return hit
        except (PermissionError, OSError):
            continue
    return None


class Fonts:
    def __init__(self, kit: dict, brand_dirs: List[Path], need_cjk: bool = False):
        from PIL import ImageFont  # type: ignore
        self.ImageFont = ImageFont
        self.paths = {}
        self.family = {}
        self.warnings: List[str] = []
        for role, weight in (("heading", "bold"), ("body", "regular")):
            spec = (kit.get("fonts") or {}).get(role) or {}
            path = C.resolve_relative(spec.get("file", ""), *brand_dirs) if spec.get("file") else None
            if spec.get("file") and not path:
                self.warnings.append(f"Brand {role} font '{spec['file']}' not found; using a system font")
            path = path or find_font_file(FALLBACK_FONTS[weight])
            self.paths[role] = path
            self.family[role] = spec.get("family") or (self._family_of(path) if path else "Arial")
        if not self.paths["heading"] and not self.paths["body"]:
            self.warnings.append("No TrueType fonts found; using Pillow's built-in font (plain look)")
        self.cjk_family = ""
        if need_cjk:
            spec = (kit.get("fonts") or {}).get("cjk") or {}
            custom = C.resolve_relative(spec.get("file", ""), *brand_dirs) if spec.get("file") else None
            if spec.get("file") and not custom:
                self.warnings.append(f"Brand Chinese font '{spec['file']}' not found; using a system Chinese font")
            found = None
            for role, weight in (("heading", "bold"), ("body", "regular")):
                path = custom or find_font_file(CJK_FONTS[weight])
                if path:
                    self.paths[role] = path
                    found = path
            if found:
                self.cjk_family = spec.get("family") or self._family_of(found)
            else:
                self.warnings.append("No Chinese font found, so Chinese text would show as empty boxes. Install a "
                                     "Chinese font (for example Noto Sans SC) or set fonts.cjk.file in the brand kit")
        self.cache = {}

    def _family_of(self, path: Path) -> str:
        try:
            return self.ImageFont.truetype(str(path), 20).getname()[0]
        except Exception:
            return "Arial"

    def get(self, role: str, size: int):
        key = (role, size)
        if key not in self.cache:
            path = self.paths.get(role) or self.paths.get("heading") or self.paths.get("body")
            if path:
                self.cache[key] = self.ImageFont.truetype(str(path), size)
            else:
                try:
                    self.cache[key] = self.ImageFont.load_default(size=size)
                except TypeError:  # Pillow < 10.1
                    self.cache[key] = self.ImageFont.load_default()
        return self.cache[key]


# --------------------------------------------------------------------------- rich text layout

Token = Tuple[str, bool, bool, bool]  # (text, emphasized, no space before, no line break before)

CLOSING = "，。！？、；：）」』》】〉”’…—·%,.!?;:)]}"
TOKEN_RE = re.compile(f"[{C.CJK_CHARS}]|[{C.CJK_PUNCT}]|[^\\s{C.CJK_CHARS}{C.CJK_PUNCT}]+")


def _cjkish(text: str) -> bool:
    return bool(text) and ord(text[0]) >= 0x2E80


def rich_paragraphs(text: str) -> List[List[Token]]:
    """Split text into tokens with emphasis ('**word**' = accent color).

    Latin text splits into words; Chinese into single characters, so a line can break between
    any two characters and no spaces are drawn between them. Closing punctuation never starts
    a line, and a word glued to punctuation in the source ("yours:") stays glued.
    """
    paragraphs = []
    for para in str(text or "").split("\n"):
        tokens: List[Token] = []
        prev_char = " "
        for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", para)):
            emph = i % 2 == 1
            for match in TOKEN_RE.finditer(part):
                word, start = match.group(0), match.start()
                before = part[start - 1] if start else prev_char
                nospace = bool(tokens) and not before.isspace()
                nobreak = nospace and (word[0] in CLOSING or not (_cjkish(word) or _cjkish(tokens[-1][0][-1])))
                tokens.append((word, emph, nospace, nobreak))
            if part:
                prev_char = part[-1]
        paragraphs.append(tokens)
    return paragraphs


def line_width(line: List[Token], font) -> float:
    space = font.getlength(" ")
    return sum(font.getlength(w) + (space if k and not nospace else 0) for k, (w, _, nospace, _nb) in enumerate(line))


def wrap(paragraphs, font, max_width: int) -> List[List[Token]]:
    lines = []
    for tokens in paragraphs:
        if not tokens:
            lines.append([])
            continue
        para: List[List[Token]] = []
        line: List[Token] = []
        for token in tokens:
            if line and not token[3] and line_width(line + [token], font) > max_width:
                para.append(line)
                line = []
            line.append(token if line else (token[0], token[1], False, False))
        para.append(line)
        # Chinese typesetting: never leave one character alone on the last line (避头尾/孤字)
        if len(para) >= 2 and len(para[-1]) == 1 and _cjkish(para[-1][0][0]) and len(para[-2]) > 3:
            prev = para[-2]
            moved = [prev.pop()]
            while moved[0][3] and len(prev) > 2:  # punctuation travels with the character before it
                moved.insert(0, prev.pop())
            moved[0] = (moved[0][0], moved[0][1], False, False)
            para[-1] = moved + para[-1]
        lines.extend(para)
    return lines

def fit_text(fonts: Fonts, role: str, text: str, max_w: int, max_h: int, start: int, minimum: int, spacing: float):
    paragraphs = rich_paragraphs(text)
    size = start
    while True:
        font = fonts.get(role, size)
        lines = wrap(paragraphs, font, max_w)
        height = int(len(lines) * size * spacing)
        widest = max((line_width(ln, font) for ln in lines), default=0)
        if (height <= max_h and widest <= max_w) or size <= minimum:
            return {"size": size, "lines": lines, "height": height, "overflow": height > max_h or widest > max_w,
                    "paragraphs": paragraphs}
        size -= 2


# --------------------------------------------------------------------------- scenes

class Builder:
    def __init__(self, spec: dict, kit: dict, fonts: Fonts, base_dirs: List[Path]):
        self.spec, self.kit, self.fonts, self.base_dirs = spec, kit, fonts, base_dirs
        size = str(spec.get("size") or kit.get("carousel", {}).get("size") or "1080x1350")
        self.W, self.H = (int(v) for v in size.lower().split("x"))
        self.M = round(self.W * 0.089)
        c = kit["colors"]
        self.c = {k: c.get(k) or C.DEFAULT_KIT["colors"][k] for k in C.DEFAULT_KIT["colors"]}
        self.handle = spec.get("handle") or kit.get("handle") or ""
        self.cjk = C.has_cjk(" ".join(str(v) for s in spec.get("slides", []) for v in s.values()))
        self.warnings: List[str] = []

    def theme(self, kind: str) -> dict:
        c = self.c
        if kind == "cover":
            bg = c["primary"]
        elif kind == "cta":
            bg = c["accent"]
        else:
            bg = c["background"]
        text = readable_on(bg, c["text"], c["background"], c["secondary"])
        accent = c["accent"] if kind != "cta" and contrast(bg, c["accent"]) >= 3 else text
        muted = c["muted"] if kind not in ("cover", "cta") and contrast(bg, c["muted"]) >= 3 else text
        return {"bg": bg, "text": text, "accent": accent, "muted": muted}

    def text_el(self, role, text, box, start, minimum, color, accent, spacing=1.15, align="left", label=""):
        x, y, w, h = box
        if C.has_cjk(text):  # Chinese needs more line spacing than Latin text
            spacing = max(spacing, 1.25 if role == "heading" else 1.45)
        fit = fit_text(self.fonts, role, text, w, h, start, minimum, spacing)
        if fit["overflow"]:
            self.warnings.append(f"slide {self.index}: {label or role} text is too long for its space; shorten it")
        return {"kind": "text", "role": role, "box": [x, y, w, max(fit["height"], 1)], "size": fit["size"], "lines": fit["lines"],
                "paragraphs": fit["paragraphs"], "color": color, "accent": accent, "spacing": spacing, "align": align}, fit["height"]

    def footer(self, els, t, index, total, cover=False):
        if not (self.kit.get("carousel", {}).get("show_handle", True) or cover):
            return
        size = round(self.W * 0.025)
        y = self.H - self.M + size // 2
        if self.handle and self.kit.get("carousel", {}).get("show_handle", True):
            els.append({"kind": "label", "text": self.handle, "pos": [self.M, y], "size": size, "color": t["muted"], "anchor": "ls",
                        "role": "body", "footer": True})
        right = ("向左滑动 →" if self.cjk else "Swipe →") if cover else (f"{index}/{total}" if self.kit.get("carousel", {}).get("show_slide_numbers", True) else "")
        if right:
            els.append({"kind": "label", "text": right, "pos": [self.W - self.M, y], "size": size, "color": t["muted"], "anchor": "rs",
                        "role": "body", "footer": True})

    @staticmethod
    def center_block(els: List[dict], top: int, bottom: int, bias: float = 0.42) -> None:
        """Shift the content block down so it sits optically centered (slightly above middle)."""
        body = [el for el in els if not el.get("footer")]
        if not body:
            return
        used = max((el["box"][1] + el["box"][3]) if "box" in el else el["pos"][1] for el in body)
        shift = int(max(0, bottom - used) * bias)
        if shift <= 0:
            return
        for el in body:
            if "box" in el:
                el["box"][1] += shift
            else:
                el["pos"][1] += shift

    def image_path(self, value) -> Optional[Path]:
        if not value:
            return None
        path = C.resolve_relative(value, *self.base_dirs)
        if not path:
            self.warnings.append(f"slide {self.index}: image '{value}' not found; slide rendered without it")
        return path

    def build(self, slide: dict, index: int, total: int) -> dict:
        self.index = index
        kind = slide.get("type", "text")
        if kind not in SLIDE_TYPES:
            self.warnings.append(f"slide {index}: unknown type '{kind}', drawn as text")
            kind = "text"
        t = self.theme(kind)
        W, H, M = self.W, self.H, self.M
        inner = W - 2 * M
        els: List[dict] = []
        bottom = H - M - round(W * 0.06)  # leave room for the footer

        if kind == "cover":
            image = self.image_path(slide.get("image"))
            if image:
                els.append({"kind": "image", "path": str(image), "box": [0, 0, W, H], "radius": 0, "overlay": 0.48})
                t = dict(t, text="#FFFFFF", muted="#E8E8E8", accent=self.c["accent"])
            y = M + round(H * 0.02)
            if slide.get("kicker"):
                els.append({"kind": "label", "text": slide["kicker"].upper(), "pos": [M, y + round(W * 0.03)],
                            "size": round(W * 0.028), "color": t["accent"], "anchor": "ls", "tracking": 0.12, "role": "heading"})
            head_h = round(H * 0.46)
            head_y = round(H * 0.30)
            el, used = self.text_el("heading", slide.get("headline", ""), (M, head_y, inner, head_h), round(W * 0.105), round(W * 0.06),
                                    t["text"], t["accent"], 1.06, label="headline")
            els.append(el)
            if slide.get("subhead"):
                sub_y = head_y + used + round(W * 0.035)
                el, _ = self.text_el("body", slide["subhead"], (M, sub_y, inner, bottom - sub_y), round(W * 0.04), round(W * 0.03),
                                     t["muted"], t["accent"], 1.3, label="subhead")
                els.append(el)
            self.footer(els, t, index, total, cover=True)

        elif kind == "cta":
            y = round(H * 0.26)
            el, used = self.text_el("heading", slide.get("headline", ""), (M, y, inner, round(H * 0.32)), round(W * 0.085), round(W * 0.055),
                                    t["text"], t["text"], 1.08, label="headline")
            els.append(el)
            y += used + round(W * 0.04)
            if slide.get("body"):
                el, used = self.text_el("body", slide["body"], (M, y, inner, round(H * 0.2)), round(W * 0.042), round(W * 0.032),
                                        t["text"], t["text"], 1.32, label="body")
                els.append(el)
                y += used + round(W * 0.06)
            if slide.get("button"):
                size = round(W * 0.036)
                font = self.fonts.get("heading", size)
                bw = int(font.getlength(slide["button"])) + 2 * round(W * 0.05)
                bh = round(size * 2.3)
                els.append({"kind": "rect", "box": [M, y, bw, bh], "fill": t["text"], "radius": bh // 2})
                els.append({"kind": "label", "text": slide["button"], "pos": [M + bw // 2, y + bh // 2], "size": size,
                            "color": t["bg"], "anchor": "mm", "role": "heading"})
            self.footer(els, t, index, total)

        else:
            y = M + round(H * 0.04)
            els.append({"kind": "rect", "box": [M, y, round(W * 0.07), round(W * 0.008)], "fill": t["accent"], "radius": 0})
            y += round(W * 0.05)
            if kind == "stat":
                el, used = self.text_el("heading", slide.get("stat", ""), (M, y, inner, round(H * 0.24)), round(W * 0.2), round(W * 0.1),
                                        t["accent"], t["accent"], 1.0, label="stat")
                els.append(el)
                y += used + round(W * 0.03)
            if kind == "quote":
                els.append({"kind": "label", "text": "“", "pos": [M - round(W * 0.01), y + round(W * 0.14)], "size": round(W * 0.2),
                            "color": t["accent"], "anchor": "ls", "role": "heading"})
                y += round(W * 0.13)
                el, used = self.text_el("heading", slide.get("quote", ""), (M, y, inner, round(H * 0.45)), round(W * 0.062), round(W * 0.042),
                                        t["text"], t["accent"], 1.22, label="quote")
                els.append(el)
                y += used + round(W * 0.04)
                if slide.get("attribution"):
                    el, _ = self.text_el("body", "— " + slide["attribution"], (M, y, inner, round(H * 0.08)), round(W * 0.034),
                                         round(W * 0.028), t["muted"], t["accent"], 1.3, label="attribution")
                    els.append(el)
            if kind == "image":
                image = self.image_path(slide.get("image"))
                img_h = round(H * 0.48)
                if image:
                    els.append({"kind": "image", "path": str(image), "box": [M, y, inner, img_h], "radius": round(W * 0.028), "overlay": 0})
                else:
                    els.append({"kind": "rect", "box": [M, y, inner, img_h], "fill": self.c["secondary"], "radius": round(W * 0.028)})
                y += img_h + round(W * 0.045)
            if slide.get("headline") and kind != "quote":
                big = kind in ("text", "list") and not slide.get("body") and not slide.get("items")
                start = round(W * (0.078 if big else 0.064))
                el, used = self.text_el("heading", slide["headline"], (M, y, inner, round(H * (0.4 if big else 0.22))), start,
                                        round(W * 0.044), t["text"], t["accent"], 1.12, label="headline")
                els.append(el)
                y += used + round(W * 0.04)
            if kind == "list" and slide.get("items"):
                items = slide["items"][:7]
                gap = round(W * 0.03)
                avail = bottom - y
                per = (avail - gap * (len(items) - 1)) // max(1, len(items))
                size = round(W * 0.04)
                for n, item in enumerate(items, 1):
                    dot = round(W * 0.056)
                    els.append({"kind": "ellipse", "box": [M, y, dot, dot], "fill": t["accent"]})
                    els.append({"kind": "label", "text": str(n), "pos": [M + dot // 2, y + dot // 2], "size": round(dot * 0.5),
                                "color": readable_on(t["accent"], t["bg"], "#FFFFFF"), "anchor": "mm", "role": "heading"})
                    tx = M + dot + round(W * 0.03)
                    el, used = self.text_el("body", item, (tx, y + round(dot * 0.12), inner - (tx - M), per), size, round(W * 0.03),
                                            t["text"], t["accent"], 1.28, label=f"list item {n}")
                    els.append(el)
                    y += max(used, dot) + gap
            if slide.get("body"):
                el, _ = self.text_el("body", slide["body"], (M, y, inner, max(60, bottom - y)), round(W * 0.04), round(W * 0.03),
                                     t["text"], t["accent"], 1.38, label="body")
                els.append(el)
            self.center_block(els, M, bottom)
            self.footer(els, t, index, total)
        return {"bg": t["bg"], "elements": els, "type": kind, "notes": slide.get("notes", "")}


# --------------------------------------------------------------------------- PNG backend

def draw_png(scene: dict, W: int, H: int, fonts: Fonts, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageOps  # type: ignore
    img = Image.new("RGB", (W, H), rgb(scene["bg"]))
    draw = ImageDraw.Draw(img)
    for el in scene["elements"]:
        kind = el["kind"]
        if kind == "image":
            x, y, w, h = el["box"]
            with Image.open(el["path"]) as src:
                photo = ImageOps.fit(ImageOps.exif_transpose(src).convert("RGB"), (w, h))
            if el.get("overlay"):
                photo = Image.blend(photo, Image.new("RGB", (w, h), (0, 0, 0)), el["overlay"])
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=el.get("radius", 0), fill=255)
            img.paste(photo, (x, y), mask)
            draw = ImageDraw.Draw(img)
        elif kind == "rect":
            x, y, w, h = el["box"]
            draw.rounded_rectangle([x, y, x + w, y + h], radius=el.get("radius", 0), fill=rgb(el["fill"]))
        elif kind == "ellipse":
            x, y, w, h = el["box"]
            draw.ellipse([x, y, x + w, y + h], fill=rgb(el["fill"]))
        elif kind == "label":
            font = fonts.get(el.get("role", "body"), el["size"])
            tracking = el.get("tracking", 0)
            if tracking:
                x, y = el["pos"]
                for ch in el["text"]:
                    draw.text((x, y), ch, font=font, fill=rgb(el["color"]), anchor="ls")
                    x += font.getlength(ch) + tracking * el["size"]
            else:
                draw.text(tuple(el["pos"]), el["text"], font=font, fill=rgb(el["color"]), anchor=el.get("anchor", "la"))
        elif kind == "text":
            font = fonts.get(el["role"], el["size"])
            x, y, w, _ = el["box"]
            line_h = el["size"] * el["spacing"]
            ascent = font.getmetrics()[0]
            space = font.getlength(" ")
            for i, line in enumerate(el["lines"]):
                width = line_width(line, font)
                cx = x + (w - width) / 2 if el["align"] == "center" else x
                base = y + i * line_h + ascent
                for k, (word, emph, glued, _nobreak) in enumerate(line):
                    if k and not glued:
                        cx += space
                    draw.text((cx, base), word, font=font, fill=rgb(el["accent"] if emph else el["color"]), anchor="ls")
                    cx += font.getlength(word)
    img.save(out, "PNG", optimize=True)


# --------------------------------------------------------------------------- PPTX backend

def write_pptx(scenes: List[dict], W: int, H: int, fonts: Fonts, out: Path) -> None:
    from pptx import Presentation  # type: ignore
    from pptx.dml.color import RGBColor  # type: ignore
    from pptx.enum.shapes import MSO_SHAPE  # type: ignore
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR  # type: ignore
    from pptx.util import Emu, Pt  # type: ignore

    px = 9525  # EMU per pixel at 96 dpi
    deck = Presentation()
    deck.slide_width, deck.slide_height = Emu(W * px), Emu(H * px)
    blank = deck.slide_layouts[6]

    def color(hex_color):
        return RGBColor(*rgb(hex_color))

    for scene in scenes:
        slide = deck.slides.add_slide(blank)
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = color(scene["bg"])
        for el in scene["elements"]:
            kind = el["kind"]
            if kind == "image":
                x, y, w, h = el["box"]
                pic = slide.shapes.add_picture(el["path"], Emu(x * px), Emu(y * px), Emu(w * px), Emu(h * px))
                iw, ih = pic.image.size
                target, source = w / h, iw / ih
                if source > target:
                    crop = (1 - target / source) / 2
                    pic.crop_left = pic.crop_right = crop
                else:
                    crop = (1 - source / target) / 2
                    pic.crop_top = pic.crop_bottom = crop
                if el.get("overlay"):
                    shade = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x * px), Emu(y * px), Emu(w * px), Emu(h * px))
                    shade.fill.solid()
                    shade.fill.fore_color.rgb = RGBColor(0, 0, 0)
                    shade.line.fill.background()
                    _set_alpha(shade, int(el["overlay"] * 100000))
            elif kind in ("rect", "ellipse"):
                x, y, w, h = el["box"]
                shape_type = MSO_SHAPE.OVAL if kind == "ellipse" else (MSO_SHAPE.ROUNDED_RECTANGLE if el.get("radius") else MSO_SHAPE.RECTANGLE)
                shape = slide.shapes.add_shape(shape_type, Emu(x * px), Emu(y * px), Emu(max(w, 1) * px), Emu(max(h, 1) * px))
                shape.fill.solid()
                shape.fill.fore_color.rgb = color(el["fill"])
                shape.line.fill.background()
                if kind == "rect" and el.get("radius") and h:
                    shape.adjustments[0] = min(0.5, el["radius"] / min(w, h))
            elif kind == "label":
                size = el["size"]
                font = fonts.get(el.get("role", "body"), size)
                width = int(font.getlength(el["text"])) + size
                x, y = el["pos"]
                anchor = el.get("anchor", "la")
                left = x - width if anchor.startswith("r") else x - width // 2 if anchor.startswith("m") else x
                top = y - size // 2 - size // 4 if anchor.endswith("m") else y - size
                box = slide.shapes.add_textbox(Emu(int(left) * px), Emu(int(top) * px), Emu(width * px), Emu(int(size * 1.4) * px))
                frame = box.text_frame
                frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
                frame.word_wrap = False
                para = frame.paragraphs[0]
                para.alignment = PP_ALIGN.RIGHT if anchor.startswith("r") else PP_ALIGN.CENTER if anchor.startswith("m") else PP_ALIGN.LEFT
                run = para.add_run()
                run.text = el["text"]
                run.font.size = Pt(size * 0.75)
                run.font.name = fonts.family[el.get("role", "body")]
                _set_east_asian(run, fonts.cjk_family)
                run.font.bold = el.get("role") == "heading"
                run.font.color.rgb = color(el["color"])
            elif kind == "text":
                x, y, w, h = el["box"]
                box = slide.shapes.add_textbox(Emu(x * px), Emu(y * px), Emu(w * px), Emu(int(h * 1.08) * px))
                frame = box.text_frame
                frame.word_wrap = True
                frame.vertical_anchor = MSO_ANCHOR.TOP
                frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
                for p_index, tokens in enumerate(el["paragraphs"]):
                    para = frame.paragraphs[0] if p_index == 0 else frame.add_paragraph()
                    para.line_spacing = el["spacing"] * 0.92
                    para.alignment = PP_ALIGN.CENTER if el["align"] == "center" else PP_ALIGN.LEFT
                    groups: List[Tuple[str, bool]] = []
                    for k, (word, emph, glued, _nobreak) in enumerate(tokens):
                        sep = "" if (k == 0 or glued) else " "
                        if groups and groups[-1][1] == emph:
                            groups[-1] = (groups[-1][0] + sep + word, emph)
                        else:
                            groups.append((sep + word, emph))
                    for text, emph in groups:
                        run = para.add_run()
                        run.text = text
                        run.font.size = Pt(el["size"] * 0.75)
                        run.font.name = fonts.family[el["role"]]
                        _set_east_asian(run, fonts.cjk_family)
                        run.font.bold = el["role"] == "heading"
                        run.font.color.rgb = color(el["accent"] if emph else el["color"])
        if scene.get("notes"):
            slide.notes_slide.notes_text_frame.text = scene["notes"]
    deck.save(out)


def _set_east_asian(run, family: str) -> None:
    """Tell PowerPoint which font to use for Chinese characters (a:ea), so the deck keeps its look."""
    if not family:
        return
    from pptx.oxml.ns import qn  # type: ignore
    rpr = run._r.get_or_add_rPr()
    for old in rpr.findall(qn("a:ea")):
        rpr.remove(old)
    ea = rpr.makeelement(qn("a:ea"), {"typeface": family})
    latin = rpr.find(qn("a:latin"))
    if latin is not None:
        latin.addnext(ea)
    else:
        rpr.append(ea)


def _set_alpha(shape, alpha_thousandths: int) -> None:
    """python-pptx has no transparency API; set <a:alpha> on the solid fill directly."""
    from pptx.oxml.ns import qn  # type: ignore
    solid = shape.fill._xPr.find(qn("a:solidFill"))
    if solid is None:
        return
    clr = solid[0]
    for old in clr.findall(qn("a:alpha")):
        clr.remove(old)
    alpha = clr.makeelement(qn("a:alpha"), {"val": str(100000 - alpha_thousandths)})
    clr.append(alpha)


# --------------------------------------------------------------------------- validation + CLI

def validate_spec(spec: dict) -> Tuple[List[str], List[str]]:
    errors, warnings = [], []
    slides = spec.get("slides")
    if not isinstance(slides, list) or not slides:
        return ["spec needs a non-empty 'slides' list"], warnings
    if len(slides) > MAX_SLIDES:
        errors.append(f"{len(slides)} slides; Instagram allows at most {MAX_SLIDES}")
    if not 5 <= len(slides) <= 10:
        warnings.append(f"{len(slides)} slides; 5-10 usually performs best")
    if slides[0].get("type") != "cover":
        warnings.append("first slide is not a 'cover' slide")
    if slides[-1].get("type") != "cta":
        warnings.append("last slide is not a 'cta' slide")
    for i, slide in enumerate(slides, 1):
        kind = slide.get("type")
        if kind not in SLIDE_TYPES:
            errors.append(f"slide {i}: type must be one of {', '.join(SLIDE_TYPES)}")
            continue
        needs = {"cover": ["headline"], "text": ["headline"], "list": ["headline", "items"], "quote": ["quote"],
                 "stat": ["stat", "headline"], "image": ["headline"], "cta": ["headline"]}[kind]
        for field in needs:
            if not slide.get(field):
                errors.append(f"slide {i} ({kind}): missing '{field}'")
        text = " ".join(str(slide.get(k, "")) for k in ("headline", "body", "quote")) + " " + \
            " ".join(str(it) for it in slide.get("items", []))
        cjk_chars = sum(1 for ch in text if C.has_cjk(ch))
        words = len(re.sub(f"[{C.CJK_CHARS}]", " ", text).split())
        if cjk_chars > 90 or words + cjk_chars / 2 > 60:
            warnings.append(f"slide {i}: too much text ({cjk_chars} Chinese characters, {words} words); "
                            "aim for under 60 characters or 40 words so it reads in 3 seconds")
    return errors, warnings


def cmd_validate(args) -> None:
    spec = C.load_json(Path(args.spec))
    errors, warnings = validate_spec(spec)
    C.print_json({"ok": not errors, "errors": errors, "warnings": warnings, "slides": len(spec.get("slides", []))})
    sys.exit(0 if not errors else 1)


def cmd_render(args) -> None:
    try:
        from PIL import Image  # type: ignore  # noqa: F401
    except ImportError:
        print('{"ok": false, "rendered": false, "reason": "Pillow is not installed, so no slide images were created. pip install pillow"}')
        sys.exit(2)
    spec_path = Path(args.spec).resolve()
    spec = C.load_json(spec_path)
    errors, warnings = validate_spec(spec)
    if errors:
        C.print_json({"ok": False, "rendered": False, "errors": errors})
        sys.exit(1)
    workspace = C.workspace_dir(args.workspace)
    kit, kit_path = C.load_brand_kit(workspace, args.brand_kit)
    brand_dirs = [d for d in (kit_path.parent if kit_path else None, workspace / "brand", C.BAKED_BRAND_DIR) if d]
    if not C.brand_kit_configured(kit_path):
        warnings.append("brand kit not configured: rendered with neutral default colors and system fonts")
    all_text = " ".join(str(v) for slide in spec["slides"] for v in slide.values())
    fonts = Fonts(kit, brand_dirs, need_cjk=C.has_cjk(all_text))
    warnings += fonts.warnings
    base_dirs = [spec_path.parent, workspace, workspace / "media", workspace / "brand" / "assets"]
    builder = Builder(spec, kit, fonts, base_dirs)
    total = len(spec["slides"])
    scenes = [builder.build(slide, i, total) for i, slide in enumerate(spec["slides"], 1)]
    warnings += builder.warnings
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pngs = []
    for i, scene in enumerate(scenes, 1):
        path = out_dir / f"slide-{i:02d}.png"
        draw_png(scene, builder.W, builder.H, fonts, path)
        pngs.append(path)
    from PIL import Image  # type: ignore
    thumbs = [Image.open(p).convert("RGB") for p in pngs]
    tw = 270
    th = round(builder.H * tw / builder.W)
    cols = min(5, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 12, rows * th + (rows + 1) * 12), (230, 228, 224))
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb.resize((tw, th)), (12 + (i % cols) * (tw + 12), 12 + (i // cols) * (th + 12)))
    overview = out_dir / "overview.png"
    sheet.save(overview)
    outputs = {"slides": [str(p) for p in pngs], "overview": str(overview)}
    if args.pdf:
        pdf = out_dir / "carousel.pdf"
        thumbs[0].save(pdf, save_all=True, append_images=thumbs[1:], resolution=144)
        outputs["pdf"] = str(pdf)
    if args.pptx:
        try:
            pptx_path = out_dir / "carousel.pptx"
            write_pptx(scenes, builder.W, builder.H, fonts, pptx_path)
            outputs["pptx"] = str(pptx_path)
        except ImportError:
            warnings.append("python-pptx not installed: no editable deck (pip install python-pptx)")
    if spec.get("caption") or spec.get("hashtags"):
        caption = out_dir / "caption.txt"
        caption.write_text((spec.get("caption") or "") + ("\n\n" + " ".join(spec.get("hashtags", [])) if spec.get("hashtags") else ""),
                           encoding="utf-8")
        outputs["caption"] = str(caption)
    missing = [p for p in pngs if not p.exists() or p.stat().st_size == 0]
    C.print_json({"ok": not missing, "rendered": not missing, "size": f"{builder.W}x{builder.H}", "count": len(pngs),
                  "fonts": {k: str(v) if v else "built-in" for k, v in fonts.paths.items()}, "outputs": outputs,
                  "warnings": warnings})
    sys.exit(0 if not missing else 3)


def main() -> None:
    C.setup_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("render")
    p.add_argument("spec")
    p.add_argument("--out", required=True, help="Output folder")
    p.add_argument("--pptx", action="store_true", help="Also write an editable carousel.pptx")
    p.add_argument("--pdf", action="store_true", help="Also write carousel.pdf")
    p.add_argument("--workspace")
    p.add_argument("--brand-kit")
    p.set_defaults(func=cmd_render)
    p = sub.add_parser("validate")
    p.add_argument("spec")
    p.set_defaults(func=cmd_validate)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
