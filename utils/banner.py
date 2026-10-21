"""Now-playing banner drawn with Pillow (blocking: call it with asyncio.to_thread).

Look: blurred + darkened album art as the background, a rounded cover with shadow, big title,
artist, a waveform strip tinted with a colour taken from the artwork, source / duration chips and
chips for the remix effects that are on (Bass 18 dB, Atmos, Vol 200% ...).

Works without artwork too (gradient background + vinyl graphic) and without internet.
Fonts: Poppins from data/fonts (Latin + Hindi). Falls back to utils/arial.ttf, then Pillow's default.
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from utils import config

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = BASE_DIR / "data" / "fonts"
FALLBACK_FONT = BASE_DIR / "utils" / "arial.ttf"

W, H = 1000, 400
SS = 3  # supersampling factor for smooth rounded shapes

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3\U000E0020-\U000E007F]+"
)
_CJK_RE = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_CJK_FONTS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/malgunbd.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/system/fonts/NotoSansCJK-Regular.ttc",  # Android / Termux
)


# ───────────────────────────── fonts ─────────────────────────────
@lru_cache(maxsize=64)
def _font(weight: str, size: int, cjk: bool = False) -> ImageFont.FreeTypeFont:
    candidates = []
    if cjk:
        candidates += [Path(p) for p in _CJK_FONTS]
    candidates += [FONT_DIR / f"Poppins-{weight}.ttf", FALLBACK_FONT]
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _clean(text: str) -> str:
    """Drop emoji (Poppins has none and would draw empty boxes) and collapse whitespace."""
    return re.sub(r"\s+", " ", _EMOJI_RE.sub("", text or "")).strip()


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, weight: str, size: int, max_w: int, max_lines: int):
    """Word-wrap `text` into at most `max_lines` lines (last one ends with an ellipsis if cut)."""
    font = _font(weight, size, bool(_CJK_RE.search(text)))
    words = text.split(" ") if " " in text else list(text)
    sep = " " if " " in text else ""
    lines, line = [], ""
    for word in words:
        trial = f"{line}{sep}{word}" if line else word
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
        if len(lines) == max_lines:
            break
    else:
        lines.append(line)
    if len(lines) > max_lines or (len(lines) == max_lines and "".join(lines).replace(" ", "") != text.replace(" ", "")):
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines or [""], font


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


# ───────────────────────────── colours ─────────────────────────────
def _seed_color(text: str) -> Tuple[int, int, int]:
    h = int(hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hsv_to_rgb(h, 0.65, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def _accent(img: Image.Image, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Pick a lively colour from the artwork (most common colour weighted by saturation)."""
    small = img.convert("RGB").resize((64, 64))
    best, best_score = None, 0.0
    for count, (r, g, b) in small.getcolors(64 * 64) or []:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.25 or s < 0.25:
            continue
        score = count * (s ** 1.5) * (0.5 + v)
        if score > best_score:
            best, best_score = (h, s, v), score
    if best is None:
        return fallback
    h, s, v = best
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, max(s, 0.55)), max(v, 0.9))
    return int(r * 255), int(g * 255), int(b * 255)


# ───────────────────────────── drawing helpers ─────────────────────────────
def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, big.width - 1, big.height - 1), radius * SS, fill=255)
    return big.resize(size, Image.LANCZOS)


def _trim_bars(img: Image.Image) -> Image.Image:
    """YouTube thumbnails often come with black bars on top and bottom: cut them."""
    gray = img.convert("L")
    w, h = gray.size
    top = 0
    while top < h // 4 and sum(gray.crop((0, top, w, top + 1)).getdata()) / w < 14:
        top += 1
    bottom = h
    while bottom > h - h // 4 and sum(gray.crop((0, bottom - 1, w, bottom)).getdata()) / w < 14:
        bottom -= 1
    return img.crop((0, top, w, bottom)) if (top or bottom != h) else img


def _gradient(size: Tuple[int, int], c1, c2) -> Image.Image:
    """Diagonal gradient c1 -> c2."""
    w, h = size
    base = Image.linear_gradient("L").resize((w, h))
    diag = Image.linear_gradient("L").rotate(90).resize((w, h))
    mix = ImageChops.add(base, diag, scale=2)
    return Image.composite(Image.new("RGB", size, c2), Image.new("RGB", size, c1), mix)


def _vinyl(size: int, accent: Tuple[int, int, int]) -> Image.Image:
    """Cover used when a track has no artwork."""
    img = _gradient((size, size), tuple(int(c * 0.45) for c in accent), (14, 14, 22)).convert("RGBA")
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    for i, r in enumerate(range(int(size * 0.44), int(size * 0.14), -9)):
        shade = 26 + (i % 2) * 10
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(shade, shade, shade + 6, 255), width=2)
    d.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), fill=accent + (255,))
    d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(12, 12, 18, 255))
    return img


def _shadow(size: Tuple[int, int], radius: int, blur: int, opacity: int) -> Image.Image:
    pad = blur * 3
    layer = Image.new("L", (size[0] + pad * 2, size[1] + pad * 2), 0)
    layer.paste(_rounded_mask(size, radius).point(lambda v: v * opacity // 255), (pad, pad))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _chip_width(base: Image.Image, text: str, *, size: int = 20, weight: str = "Medium", pad_x: int = 16) -> int:
    font = _font(weight, size, bool(_CJK_RE.search(text)))
    return int(ImageDraw.Draw(base).textlength(text, font=font)) + pad_x * 2


def _chip(base: Image.Image, xy: Tuple[int, int], text: str, *, fill, fg, size: int = 20, weight: str = "Medium",
          pad_x: int = 16, pad_y: int = 7, outline=None) -> int:
    """Draw a rounded pill with text; returns the x just after it (for chaining)."""
    probe = ImageDraw.Draw(base)
    font = _font(weight, size, bool(_CJK_RE.search(text)))
    tw = int(probe.textlength(text, font=font))
    asc, desc = font.getmetrics()
    w, h = tw + pad_x * 2, asc + desc + pad_y * 2
    pill = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), (h // 2) * SS, fill=fill,
                         outline=outline, width=2 * SS if outline else 0)
    pill = pill.resize((w, h), Image.LANCZOS)
    base.alpha_composite(pill, xy)
    ImageDraw.Draw(base).text((xy[0] + pad_x, xy[1] + pad_y - 1), text, font=font, fill=fg)
    return xy[0] + w


def _waveform(base: Image.Image, box: Tuple[int, int, int, int], seed: str, accent) -> None:
    """A decorative equaliser strip (the same title always draws the same bars)."""
    x0, y0, x1, y1 = box
    rng = random.Random(seed)
    n = 58
    gap = 5
    bw = max(3, ((x1 - x0) - gap * (n - 1)) // n)
    mid = (y0 + y1) // 2
    amp = (y1 - y0) // 2
    level = 0.5
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        level = min(1.0, max(0.18, level + rng.uniform(-0.28, 0.28)))
        hh = int(amp * level)
        t = i / (n - 1)
        # accent -> white-ish fade across the strip
        col = tuple(int(a + (255 - a) * 0.35 * t) for a in accent)
        x = x0 + i * (bw + gap)
        d.rounded_rectangle((x, mid - hh, x + bw, mid + hh), bw // 2, fill=col + (235 - int(80 * t),))
    base.alpha_composite(layer)


# ───────────────────────────── the banner ─────────────────────────────
def player_effect_chips(player) -> list:
    """The effect chips for the card, read from what the player is REALLY set to.

    Uses the shared per-guild state (`player.remix_state`) plus the live `player.volume`, so the card,
    the Remix console, `.fx`, `.bass` and `.volume` can never disagree. [] when nothing is changed.
    """
    from utils.remix import banner_chips, get_state  # local: keeps this module importable on its own

    try:
        return banner_chips(get_state(player))
    except Exception:  # a broken chip list must never stop the card from being drawn
        return []


def render_banner(
    *,
    artwork: Optional[bytes],
    title: str,
    artist: str = "",
    duration: str = "",
    source: str = "",
    requester: str = "",
    session_text: str = "",
    effects: Sequence[str] = (),
) -> bytes:
    """Return the banner as PNG bytes."""
    title = _clean(title) or "Unknown title"
    artist = _clean(artist)
    seed_color = _seed_color(title + artist)

    art: Optional[Image.Image] = None
    if artwork:
        try:
            art = _trim_bars(Image.open(io.BytesIO(artwork)).convert("RGB"))
        except Exception:
            art = None

    accent = _accent(art, seed_color) if art is not None else seed_color

    # ── background ──
    if art is not None:
        bg = ImageOps.fit(art, (W, H), centering=(0.5, 0.45)).filter(ImageFilter.GaussianBlur(38))
        bg = ImageEnhance.Color(bg).enhance(1.35)
        bg = ImageEnhance.Brightness(bg).enhance(0.48)
    else:
        bg = _gradient((W, H), tuple(int(c * 0.55) for c in accent), (10, 10, 18))
    canvas = bg.convert("RGBA")

    # darker towards the right so the text stays readable, soft vignette on the edges
    shade = Image.linear_gradient("L").rotate(90).resize((W, H)).point(lambda v: int(150 * (v / 255) ** 0.8))
    canvas.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (W, H), (6, 6, 12)).split(), shade)))
    vignette = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vignette).rectangle((40, 40, W - 40, H - 40), fill=255)
    vignette = ImageChops.invert(vignette.filter(ImageFilter.GaussianBlur(60))).point(lambda v: int(v * 0.55))
    canvas.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (W, H), (0, 0, 0)).split(), vignette)))

    # ── cover ──
    cover_size = 304
    cx, cy = 48, (H - cover_size) // 2
    sh = _shadow((cover_size, cover_size), 28, 18, 190)
    pad = 18 * 3
    canvas.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", sh.size, (0, 0, 0)).split(), sh)),
                           (cx - pad, cy - pad + 14))
    cover = (ImageOps.fit(art, (cover_size, cover_size), centering=(0.5, 0.5)).convert("RGBA")
             if art is not None else _vinyl(cover_size, accent))
    cover.putalpha(_rounded_mask((cover_size, cover_size), 28))
    canvas.alpha_composite(cover, (cx, cy))
    ring = Image.new("RGBA", (cover_size * SS, cover_size * SS), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle((0, 0, cover_size * SS - 1, cover_size * SS - 1), 28 * SS,
                                           outline=(255, 255, 255, 60), width=2 * SS)
    canvas.alpha_composite(ring.resize((cover_size, cover_size), Image.LANCZOS), (cx, cy))

    # ── text column ──
    left = cx + cover_size + 46
    right = W - 48
    max_w = right - left
    draw = ImageDraw.Draw(canvas)

    # top row: "NOW PLAYING" chip + brand
    _chip(canvas, (left, 38), "NOW PLAYING", fill=accent + (255,), fg=(14, 14, 20, 255),
          size=16, weight="Bold", pad_x=14, pad_y=5)
    brand_font = _font("Bold", 16)
    brand = " ".join(config.NAME.upper().replace(" ", "  "))   # bot name from config.NAME, letter-spaced
    draw.text((right - draw.textlength(brand, font=brand_font), 43), brand, font=brand_font, fill=(255, 255, 255, 120))

    # title (max 2 lines) + artist
    lines, tfont = _fit_lines(draw, title, "Bold", 40, max_w, 2)
    y = 84
    line_h = int(sum(tfont.getmetrics()) * 1.02)
    for line in lines:
        draw.text((left, y), line, font=tfont, fill=(255, 255, 255, 255))
        y += line_h
    if artist:
        a_lines, afont = _fit_lines(draw, artist, "Medium", 24, max_w, 1)
        draw.text((left, y + 4), a_lines[0], font=afont, fill=(255, 255, 255, 175))

    # waveform strip
    _waveform(canvas, (left, 262, right, 306), title + artist, accent)
    draw = ImageDraw.Draw(canvas)
    small = _font("Medium", 17)
    t_y = 312
    draw.text((left, t_y), "0:00", font=small, fill=(255, 255, 255, 150))
    if duration:
        draw.text((right - draw.textlength(duration, font=small), t_y), duration, font=small,
                  fill=(255, 255, 255, 150))
    display_info = session_text or (f"session connected - @{requester}" if requester else "")
    if display_info:
        rfont = _font("Regular", 16)
        text = _ellipsize(draw, _clean(display_info), rfont, max_w - 200)
        draw.text((left + (max_w - draw.textlength(text, font=rfont)) / 2, t_y + 1), text, font=rfont,
                  fill=(255, 255, 255, 140))

    # chips row: source + remix effects (as many as fit, then "+N")
    y_chips = 350
    x = left
    chips = ([(source, False)] if source else []) + [(name, True) for name in effects]
    reserve = _chip_width(canvas, "+9", size=17) + 10
    shown = 0
    for i, (text, is_fx) in enumerate(chips):
        w = _chip_width(canvas, text, size=17)
        remaining = len(chips) - i - 1
        if x + w > right - (reserve if remaining else 0):
            break
        if is_fx:
            _chip(canvas, (x, y_chips), text, fill=accent + (60,), fg=(255, 255, 255, 245), size=17,
                  outline=accent + (200,), pad_x=15, pad_y=6)
        else:
            _chip(canvas, (x, y_chips), text, fill=(255, 255, 255, 38), fg=(255, 255, 255, 235), size=17,
                  outline=(255, 255, 255, 70), pad_x=15, pad_y=6)
        x += w + 10
        shown += 1
    if shown < len(chips):
        _chip(canvas, (x, y_chips), f"+{len(chips) - shown}", fill=(255, 255, 255, 30), fg=(255, 255, 255, 220),
              size=17, pad_x=15, pad_y=6)

    # accent line along the bottom edge
    ImageDraw.Draw(canvas).rectangle((0, H - 5, W, H), fill=accent + (255,))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
