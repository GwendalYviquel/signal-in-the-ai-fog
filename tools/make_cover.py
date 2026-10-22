"""Generate the podcast cover art in docs/cover.jpg (3000 x 3000 px, RGB JPEG).

Usage: pip install -r requirements-dev.txt && python tools/make_cover.py [output.jpg]
       python tools/make_cover.py --show <slug>   (another show's cover, from its show.yaml)

Every coordinate is designed for 3000 px and scaled to the requested size, so the
same cover can be rendered small and fast (tests) or full size (publication).
"""
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

DESIGN = 3000  # design size: all coordinates below are in these units
OUT = Path(__file__).resolve().parent.parent / "docs" / "cover.jpg"

# Bold fonts tried in order: DejaVu (Linux, CI), then common macOS and Windows fonts.
BOLD_FONTS = [
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def font(size: float) -> ImageFont.FreeTypeFont:
    """A scalable bold font at this size. Never the tiny fixed-size bitmap default:
    on a machine without DejaVu it erased every word of the cover."""
    size = max(1, round(size))
    for path in BOLD_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    default = ImageFont.load_default(size=size)  # scalable since Pillow 10.1
    if not isinstance(default, ImageFont.FreeTypeFont):
        raise RuntimeError("No scalable font found: install DejaVu fonts or upgrade Pillow")
    return default


def render(size: int = DESIGN, seed: int = 11) -> Image.Image:
    rng = random.Random(seed)
    k = size / DESIGN

    def px(v):
        return v * k

    def gradient(c1, c2, c3):
        """Three-colour diagonal gradient."""
        yy, xx = np.mgrid[0:size, 0:size]
        t = ((xx + yy) / (2 * size))[..., None]
        c1, c2, c3 = (np.array(c, float) for c in (c1, c2, c3))
        out = np.where(t < 0.55, c1 + (c2 - c1) * (t / 0.55), c2 + (c3 - c2) * ((t - 0.55) / 0.45))
        return Image.fromarray(out.clip(0, 255).astype("uint8"))

    def glow_layer(draw_fn, blur, color, strength=1.0):
        mask = Image.new("L", (size, size), 0)
        draw_fn(ImageDraw.Draw(mask))
        mask = mask.filter(ImageFilter.GaussianBlur(px(blur)))
        mask = mask.point(lambda v: min(255, int(v * strength)))
        return Image.composite(Image.new("RGB", (size, size), color), Image.new("RGB", (size, size), 0), mask)

    # 1. Background: night -> purple -> teal gradient
    img = gradient((8, 10, 32), (52, 22, 96), (6, 70, 96))

    # 2. Coloured fog (blurred patches, "screen" blend)
    for color, n in (((120, 70, 200), 14), ((30, 170, 190), 12), ((220, 90, 170), 6)):
        def blobs(d, n=n):
            for _ in range(n):
                x, y = rng.randint(-600, DESIGN), rng.randint(-300, DESIGN)
                r = rng.randint(400, 1000)
                d.ellipse([px(x), px(y), px(x + 2.2 * r), px(y + r)], fill=rng.randint(60, 120))
        img = ImageChops.screen(img, glow_layer(blobs, 220, color, 0.55))

    # 3. Darkened area behind "AI" for contrast
    cx, cy = DESIGN // 2, 1230
    dark = Image.new("L", (size, size), 0)
    ImageDraw.Draw(dark).ellipse([px(cx - 1100), px(cy - 650), px(cx + 1100), px(cy + 650)], fill=170)
    dark = dark.filter(ImageFilter.GaussianBlur(px(260)))
    img = Image.composite(Image.new("RGB", (size, size), (6, 6, 22)), img, dark)

    # 4. Glowing particles
    part = Image.new("L", (size, size), 0)
    pd = ImageDraw.Draw(part)
    for _ in range(260):
        x, y, r = rng.randint(0, DESIGN), rng.randint(0, DESIGN), rng.choice([3, 4, 5, 7, 10])
        pd.ellipse([px(x - r), px(y - r), px(x + r), px(y + r)], fill=rng.randint(90, 230))
    img = ImageChops.screen(img, Image.merge("RGB", [part.filter(ImageFilter.GaussianBlur(px(2)))] * 3))

    draw = ImageDraw.Draw(img)

    def spaced(text, f, y, color, tracking):
        widths = [draw.textlength(ch, font=f) for ch in text]
        total = sum(widths) + px(tracking) * (len(text) - 1)
        x = (size - total) / 2
        for ch, w in zip(text, widths):
            draw.text((x, px(y)), ch, font=f, fill=color)
            x += w + px(tracking)

    # 5. "SIGNAL IN THE"
    spaced("SIGNAL IN THE", font(px(175)), 470, (230, 232, 245), 34)

    # 6. Giant "AI": drop shadow, outer glow, vivid gradient and light outline
    f_ai = font(px(1100))
    bbox = draw.textbbox((0, 0), "AI", font=f_ai)
    w = bbox[2] - bbox[0]
    ax, ay = (size - w) / 2 - bbox[0], px(800) - bbox[1]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).text((ax, ay), "AI", font=f_ai, fill=255)
    outline = Image.new("L", (size, size), 0)
    ImageDraw.Draw(outline).text((ax, ay), "AI", font=f_ai, fill=255,
                                 stroke_width=max(1, round(px(16))), stroke_fill=255)

    shadow = outline.filter(ImageFilter.GaussianBlur(px(45)))
    img = Image.composite(Image.new("RGB", (size, size), (0, 0, 8)), img, shadow)
    grown = outline.filter(ImageFilter.MaxFilter(max(3, round(px(41)) | 1)))  # odd kernel size
    glow = ImageChops.subtract(grown, outline).filter(ImageFilter.GaussianBlur(px(55)))
    img = ImageChops.screen(img, Image.composite(Image.new("RGB", (size, size), (150, 90, 255)),
                                                 Image.new("RGB", (size, size), 0), glow))
    img.paste(Image.new("RGB", (size, size), (245, 250, 255)), (0, 0), outline)   # light outline

    yy, xx = np.mgrid[0:size, 0:size]
    t = ((xx - (size - w) / 2) / w).clip(0, 1)[..., None]
    c1, c2, c3 = (np.array(c, float) for c in ((40, 245, 210), (80, 170, 255), (255, 90, 210)))
    fill = np.where(t < 0.5, c1 + (c2 - c1) * (t / 0.5), c2 + (c3 - c2) * ((t - 0.5) / 0.5)).astype("uint8")
    img.paste(Image.fromarray(fill), (0, 0), mask)
    draw = ImageDraw.Draw(img)

    # 7. "FOG"
    spaced("FOG", font(px(330)), 1760, (240, 240, 250), 90)

    # 8. Signal wave: noise on the left, sharp pulse in the centre, calm on the right
    base, pts = 2400, []
    for x in range(250, DESIGN - 250, 8):
        u = (x - DESIGN / 2) / (DESIGN / 2)
        noise = (1 - min(1, abs(u + 0.45) * 2.2)) * rng.uniform(-70, 70) if u < -0.1 else 0
        pulse = math.exp(-((u * 9) ** 2)) * 190 * math.sin(u * 60)
        pts.append((px(x), px(base + noise + pulse)))
    img = ImageChops.screen(img, glow_layer(lambda d: d.line(pts, fill=255, width=max(1, round(px(30)))),
                                            40, (60, 230, 220), 1.4))
    draw = ImageDraw.Draw(img)
    draw.line(pts, fill=(200, 255, 248), width=max(1, round(px(9))))

    # 9. Tagline
    spaced("DAILY AI BRIEFING", font(px(92)), 2760, (190, 200, 225), 26)
    return img


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def render_show(title: str, kicker: str, palette: list[str], size: int = DESIGN, seed: int = 7) -> Image.Image:
    """Cover of a show other than the first: its colours, its title as large as it fits, a kicker
    line above and the signal wave below. The same title always gives the same cover."""
    rng = random.Random(seed)
    k = size / DESIGN
    c1, c2, c3 = (np.array(_hex(c), float) for c in palette)
    yy, xx = np.mgrid[0:size, 0:size]
    t = ((xx + yy) / (2 * size))[..., None]
    out = np.where(t < 0.55, c1 + (c2 - c1) * (t / 0.55), c2 + (c3 - c2) * ((t - 0.55) / 0.45))
    img = Image.fromarray(out.clip(0, 255).astype("uint8"))
    draw = ImageDraw.Draw(img)

    def centred(text, f, y, color):
        box = draw.textbbox((0, 0), text, font=f)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], y * k - box[1]), text, font=f, fill=color)

    # Title: one or two lines, the largest size that fits 84 % of the width.
    words = title.upper().split()
    lines = [title.upper()] if len(words) < 2 else [" ".join(words[:len(words) // 2]), " ".join(words[len(words) // 2:])]
    fsize = 900
    while fsize > 100 and max(draw.textlength(line, font=font(fsize * k)) for line in lines) > 0.84 * size:
        fsize -= 20
    y = 1250 - (len(lines) - 1) * fsize * 0.55
    for line in lines:
        centred(line, font(fsize * k), y, (250, 250, 255))
        y += fsize * 1.1
    centred(kicker.upper(), font(130 * k), 520, (235, 240, 255))

    # Signal wave, as on the first show's cover: noise, then a sharp pulse, then calm.
    pts = []
    for x in range(250, DESIGN - 250, 8):
        u = (x - DESIGN / 2) / (DESIGN / 2)
        noise = (1 - min(1, abs(u + 0.45) * 2.2)) * rng.uniform(-60, 60) if u < -0.1 else 0
        pulse = math.exp(-((u * 9) ** 2)) * 170 * math.sin(u * 60)
        pts.append((x * k, (2450 + noise + pulse) * k))
    draw.line(pts, fill=(255, 255, 255), width=max(1, round(14 * k)))
    return img


def show_cover(slug: str, size: int = DESIGN) -> Path:
    """Render a show's cover from its show.yaml (podcast.title, podcast.cover_kicker, podcast.cover_palette)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from engine import show as shows
    show = shows.load(slug)
    p = show.cfg["podcast"]
    out = show.docs / p["cover_file"]
    out.parent.mkdir(parents=True, exist_ok=True)
    render_show(p["title"], p.get("cover_kicker", ""), p["cover_palette"], size).save(out, "JPEG", quality=92)
    print(f"Cover saved: {out}")
    return out


def main(out: Path = OUT, size: int = DESIGN) -> Path:
    render(size).save(out, "JPEG", quality=92)
    print(f"Cover saved: {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--show":
        show_cover(sys.argv[2])
    else:
        main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
