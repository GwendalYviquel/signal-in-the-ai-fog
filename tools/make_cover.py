"""Génère la pochette du podcast (3000 x 3000 px) dans docs/cover.jpg.

Usage : pip install pillow && python tools/make_cover.py "Signal in the AI Fog"
Le mot « AI » est mis en couleur d'accent. Remplacez par votre propre visuel si besoin.
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

title = sys.argv[1] if len(sys.argv) > 1 else "Signal in the AI Fog"
SIZE = 3000
BG, TEXT, ACCENT = (18, 22, 34), (226, 230, 238), (64, 214, 186)

# Fond : nappes de brouillard floutées
img = Image.new("RGB", (SIZE, SIZE), BG)
fog = Image.new("L", (SIZE, SIZE), 0)
d = ImageDraw.Draw(fog)
random.seed(7)
for _ in range(40):
    x, y = random.randint(-400, SIZE), random.randint(-400, SIZE)
    r = random.randint(300, 900)
    d.ellipse([x, y, x + 2 * r, y + r], fill=random.randint(18, 45))
fog = fog.filter(ImageFilter.GaussianBlur(160))
img = Image.composite(Image.new("RGB", (SIZE, SIZE), (120, 132, 150)), img, fog)
draw = ImageDraw.Draw(img)

# Ligne de signal
mid = SIZE - 700
pts, x = [], 300
while x <= SIZE - 300:
    pts.append((x, mid + (0 if abs(x - SIZE / 2) > 260 else random.randint(-160, 160))))
    x += 40
draw.line(pts, fill=ACCENT, width=14)

try:
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 300)
except OSError:
    font = ImageFont.load_default()

# Découpage en lignes, en gardant chaque mot pour le colorier séparément
words, lines, line = title.split(), [], []
for w in words:
    test = " ".join(line + [w])
    if line and draw.textlength(test, font=font) > SIZE - 600:
        lines.append(line)
        line = [w]
    else:
        line.append(w)
lines.append(line)

space = draw.textlength(" ", font=font)
y = 650
for ln in lines:
    width = sum(draw.textlength(w, font=font) for w in ln) + space * (len(ln) - 1)
    x = (SIZE - width) / 2
    for w in ln:
        draw.text((x, y), w, font=font, fill=ACCENT if w.upper() == "AI" else TEXT)
        x += draw.textlength(w, font=font) + space
    y += 380

out = Path(__file__).resolve().parent.parent / "docs" / "cover.jpg"
img.save(out, quality=90)
print(f"Pochette enregistrée : {out}")
