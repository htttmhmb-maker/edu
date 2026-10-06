"""generate_image.py — بطاقات المشاهد (1080x1920) بالعربية، من اليمين إلى اليسار."""
import os

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, features

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

W, H = 1080, 1920
MARGIN = 80
SAFE_BOTTOM = 260

TOP, BOTTOM = (28, 58, 128), (8, 14, 44)
ACCENT = (255, 196, 61)
CARD = (255, 255, 255, 30)
OPTION = (255, 255, 255, 38)
GREEN = (46, 204, 113)
WHITE = (255, 255, 255)
MUTED = (255, 255, 255, 150)

HEADER_TITLE = "اختبر معلوماتك التربوية"
LETTERS = ["أ", "ب", "ج", "د"]
FONT_CANDIDATES = [
    os.path.join(ASSETS_DIR, "Cairo-ExtraBold.ttf"),
    os.path.join(ASSETS_DIR, "Tajawal-ExtraBold.ttf"),
    os.path.join(ASSETS_DIR, "NotoNaskhArabic-Bold.ttf"),
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

_reshaper = arabic_reshaper.ArabicReshaper()
_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# إذا كان محرك raqm متوفرًا يتولى التشكيل والاتجاه بنفسه، وإلا نستعمل reshaper + bidi
RAQM = features.check("raqm")
_KW = {"direction": "rtl", "language": "ar"} if RAQM else {}


def shape(text):
    return text if RAQM else get_display(_reshaper.reshape(text))


def tlen(draw, text, font):
    return draw.textlength(text, font=font, **_KW)


def dtext(draw, xy, text, font, fill):
    draw.text(xy, text, font=font, fill=fill, **_KW)


def _font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _background():
    mask = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), BOTTOM), Image.new("RGB", (W, H), TOP), mask)
    return img.convert("RGBA")


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if tlen(draw, shape(trial), font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, max_w, max_h, start=72, minimum=34):
    size = start
    while size >= minimum:
        font = _font(size)
        lines = _wrap(draw, text, font, max_w)
        lh = int(size * 1.55)  # الخط العربي يحتاج تباعد أسطر أكبر
        if lh * len(lines) <= max_h:
            return font, lines, lh
        size -= 2
    font = _font(minimum)
    return font, _wrap(draw, text, font, max_w), int(minimum * 1.55)


def _centered(draw, y, text, font, fill=WHITE):
    t = shape(text)
    w = tlen(draw, t, font)
    dtext(draw, ((W - w) / 2, y), t, font, fill)


def _header(draw, data):
    _centered(draw, 110, HEADER_TITLE, _font(76), ACCENT)
    f = _font(36)
    t = shape(data["category"])
    pw = tlen(draw, t, f) + 90
    x0 = (W - pw) / 2
    draw.rounded_rectangle([x0, 240, x0 + pw, 310], radius=35, fill=(255, 255, 255, 40))
    dtext(draw, (x0 + 45, 245), t, f, WHITE)


def _question_box(draw, text, top, height):
    draw.rounded_rectangle([MARGIN, top, W - MARGIN, top + height], radius=40, fill=CARD)
    font, lines, lh = _fit(draw, text, W - 2 * MARGIN - 80, height - 70)
    y = top + (height - lh * len(lines)) / 2
    for line in lines:
        _centered(draw, y, line, font)
        y += lh


def _render(data, mode, path, number=None):
    base = _background()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _header(d, data)

    if mode == "countdown":
        _centered(d, 520, "فكّر بسرعة!", _font(70), MUTED)
        _centered(d, 640, str(number).translate(_AR_DIGITS), _font(520), ACCENT)
    else:
        _question_box(d, data["question"], 370, 520)
        top = 950
        gap = 28
        row_h = (H - SAFE_BOTTOM - top - 3 * gap) // 4
        right = W - MARGIN
        for i, ans in enumerate(data["all_answers"]):
            y = top + i * (row_h + gap)
            is_correct = mode == "answer" and i == data["correct_index"]
            dim = mode == "answer" and not is_correct
            fill = GREEN + (255,) if is_correct else ((255, 255, 255, 14) if dim else OPTION)
            d.rounded_rectangle([MARGIN, y, right, y + row_h], radius=34, fill=fill)

            badge = (255, 255, 255, 255) if is_correct else ACCENT + (255,)
            cy = y + row_h / 2
            d.ellipse([right - 108, cy - 40, right - 28, cy + 40], fill=badge)
            lf = _font(46)
            lw = tlen(d, LETTERS[i], lf)
            dtext(d, (right - 68 - lw / 2, cy - 38), LETTERS[i], lf, (20, 20, 40))

            font, lines, lh = _fit(d, ans, W - 2 * MARGIN - 190, row_h - 24, start=52, minimum=26)
            ty = cy - lh * len(lines) / 2
            col = (255, 255, 255, 255) if not dim else (255, 255, 255, 110)
            for line in lines:
                t = shape(line)
                tw = tlen(d, t, font)
                dtext(d, (right - 140 - tw, ty), t, font, col)
                ty += lh

    Image.alpha_composite(base, layer).convert("RGB").save(path, "PNG")
    return path


def render_question(data, path):
    return _render(data, "question", path)


def render_countdown(data, number, path):
    return _render(data, "countdown", path, number)


def render_answer(data, path):
    return _render(data, "answer", path)
