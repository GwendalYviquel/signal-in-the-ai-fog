"""Génère une pochette simple (3000 x 3000 px) dans docs/cover.jpg.

Usage : pip install pillow && python tools/make_cover.py "Veille IA en production"
Remplacez-la par votre propre visuel si vous en avez un.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

title = sys.argv[1] if len(sys.argv) > 1 else "Veille IA en production"
size = 3000
img = Image.new("RGB", (size, size), (20, 24, 38))
draw = ImageDraw.Draw(img)
draw.rectangle([200, 200, size - 200, size - 200], outline=(120, 200, 180), width=24)
try:
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 220)
except OSError:
    font = ImageFont.load_default()
words, lines, line = title.split(), [], ""
for w in words:
    test = f"{line} {w}".strip()
    if draw.textlength(test, font=font) > size - 700 and line:
        lines.append(line)
        line = w
    else:
        line = test
lines.append(line)
y = size // 2 - len(lines) * 140
for ln in lines:
    x = (size - draw.textlength(ln, font=font)) / 2
    draw.text((x, y), ln, font=font, fill=(240, 240, 240))
    y += 280
out = Path(__file__).resolve().parent.parent / "docs" / "cover.jpg"
img.save(out, quality=90)
print(f"Pochette enregistrée : {out}")
