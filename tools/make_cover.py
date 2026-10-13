"""Génère la pochette du podcast (3000 x 3000 px) dans docs/cover.jpg.

Usage : pip install pillow numpy && python tools/make_cover.py
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

S = 3000
random.seed(11)
np.random.seed(11)
FONT_BOLD = "DejaVuSans-Bold.ttf"
FONT_LIGHT = "DejaVuSans-ExtraLight.ttf"


def font(path, size):
    for p in (path, "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(c1, c2, c3):
    """Dégradé diagonal à trois couleurs."""
    yy, xx = np.mgrid[0:S, 0:S]
    t = ((xx + yy) / (2 * S))[..., None]
    c1, c2, c3 = (np.array(c, float) for c in (c1, c2, c3))
    out = np.where(t < 0.55, c1 + (c2 - c1) * (t / 0.55), c2 + (c3 - c2) * ((t - 0.55) / 0.45))
    return Image.fromarray(out.clip(0, 255).astype("uint8"))


def glow_layer(draw_fn, blur, color, strength=1.0):
    mask = Image.new("L", (S, S), 0)
    draw_fn(ImageDraw.Draw(mask))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    mask = mask.point(lambda v: min(255, int(v * strength)))
    return Image.composite(Image.new("RGB", (S, S), color), Image.new("RGB", (S, S), 0), mask)


# 1. Fond : dégradé nuit -> violet -> bleu canard
img = gradient((8, 10, 32), (52, 22, 96), (6, 70, 96))

# 2. Brouillard coloré (nappes floutées, mélange "screen")
for color, n in (((120, 70, 200), 14), ((30, 170, 190), 12), ((220, 90, 170), 6)):
    def blobs(d, n=n):
        for _ in range(n):
            x, y = random.randint(-600, S), random.randint(-300, S)
            r = random.randint(400, 1000)
            d.ellipse([x, y, x + 2.2 * r, y + r], fill=random.randint(60, 120))
    img = ImageChops.screen(img, glow_layer(blobs, 220, color, 0.55))

# 3. Halo lumineux derrière "AI"
cx, cy = S // 2, 1420
img = ImageChops.screen(img, glow_layer(lambda d: d.ellipse([cx - 900, cy - 700, cx + 900, cy + 700], fill=200),
                                        350, (40, 200, 210), 0.9))

# 4. Particules lumineuses
part = Image.new("L", (S, S), 0)
pd = ImageDraw.Draw(part)
for _ in range(260):
    x, y, r = random.randint(0, S), random.randint(0, S), random.choice([3, 4, 5, 7, 10])
    pd.ellipse([x - r, y - r, x + r, y + r], fill=random.randint(90, 230))
img = ImageChops.screen(img, Image.merge("RGB", [part.filter(ImageFilter.GaussianBlur(2))] * 3))

draw = ImageDraw.Draw(img)


def spaced(text, f, y, color, tracking):
    widths = [draw.textlength(ch, font=f) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (S - total) / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=f, fill=color)
        x += w + tracking


# 5. "SIGNAL IN THE"
spaced("SIGNAL IN THE", font(FONT_BOLD, 165), 520, (230, 232, 245), 34)

# 6. "AI" géant en dégradé turquoise -> rose, avec lueur
f_ai = font(FONT_BOLD, 1100)
bbox = draw.textbbox((0, 0), "AI", font=f_ai)
w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
ax, ay = (S - w) / 2 - bbox[0], 830 - bbox[1]
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).text((ax, ay), "AI", font=f_ai, fill=255)
img = ImageChops.screen(img, Image.composite(Image.new("RGB", (S, S), (60, 230, 220)),
                                             Image.new("RGB", (S, S), 0),
                                             mask.filter(ImageFilter.GaussianBlur(90))))
yy, xx = np.mgrid[0:S, 0:S]
t = ((xx - (S - w) / 2) / w).clip(0, 1)[..., None]
c1, c2, c3 = (np.array(c, float) for c in ((70, 240, 215), (110, 170, 255), (245, 110, 220)))
fill = np.where(t < 0.5, c1 + (c2 - c1) * (t / 0.5), c2 + (c3 - c2) * ((t - 0.5) / 0.5)).astype("uint8")
img.paste(Image.fromarray(fill), (0, 0), mask)
draw = ImageDraw.Draw(img)

# 7. "FOG"
spaced("FOG", font(FONT_BOLD, 330), 1760, (240, 240, 250), 90)

# 8. Onde de signal : bruit à gauche, impulsion nette au centre, calme à droite
base, pts = 2400, []
for x in range(250, S - 250, 8):
    u = (x - S / 2) / (S / 2)
    noise = (1 - min(1, abs(u + 0.45) * 2.2)) * random.uniform(-70, 70) if u < -0.1 else 0
    pulse = math.exp(-((u * 9) ** 2)) * 190 * math.sin(u * 60)
    pts.append((x, base + noise + pulse))
img = ImageChops.screen(img, glow_layer(lambda d: d.line(pts, fill=255, width=30), 40, (60, 230, 220), 1.4))
draw = ImageDraw.Draw(img)
draw.line(pts, fill=(200, 255, 248), width=9)

# 9. Accroche
spaced("DAILY AI BRIEFING", font(FONT_BOLD, 92), 2760, (190, 200, 225), 26)

out = Path(__file__).resolve().parent.parent / "docs" / "cover.jpg"
img.save(out, quality=92)
print(f"Pochette enregistrée : {out}")
