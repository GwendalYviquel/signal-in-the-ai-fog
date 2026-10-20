"""Cover art: the published file meets the podcast platforms' specs, and the generator works anywhere.

Renders are small (300 to 600 px) to stay fast: every coordinate scales from the 3000 px design.
"""
import sys

import numpy as np
import pytest
from PIL import Image, ImageFont

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import make_cover  # noqa: E402


def test_published_cover_meets_spotify_and_apple_specs():
    # Square, 1400 to 3000 px, RGB (no alpha, no CMYK), JPEG: otherwise the show can be refused.
    with Image.open(ROOT / "docs" / "cover.jpg") as img:
        assert img.format == "JPEG" and img.mode == "RGB"
        assert img.width == img.height and 1400 <= img.width <= 3000


def test_config_points_to_the_cover(cfg):
    assert (ROOT / "docs" / cfg["podcast"]["cover_file"]).exists()


def test_render_size_mode_and_determinism():
    a, b = make_cover.render(300), make_cover.render(300)
    assert a.size == (300, 300) and a.mode == "RGB"
    assert np.array_equal(np.asarray(a), np.asarray(b))


def bright_share(img, top, bottom):
    """Share of near-white or vivid pixels in a horizontal band (design units)."""
    k = img.width / make_cover.DESIGN
    band = np.asarray(img)[int(top * k):int(bottom * k)]
    return float((band.max(axis=2) > 200).mean())


def assert_text_is_drawn(img):
    # Measured: the broken cover has about 0.1 % bright pixels in these bands, good covers 4.5 %
    # (thin built-in font) to 24 % (DejaVu): thresholds sit well between the two.
    assert bright_share(img, 470, 680) > 0.02, "SIGNAL IN THE is missing"
    assert bright_share(img, 850, 1650) > 0.05, "AI is missing"
    assert bright_share(img, 1760, 2100) > 0.02, "FOG is missing"


def test_every_word_is_drawn():
    assert_text_is_drawn(make_cover.render(600))


@pytest.fixture
def no_system_fonts(monkeypatch):
    """No font file on disk; Pillow's built-in font (loaded from memory) still works."""
    real = ImageFont.truetype

    def truetype(font=None, size=10, *args, **kw):
        if isinstance(font, (str, bytes)) or hasattr(font, "__fspath__"):
            raise OSError("cannot open resource")
        return real(font, size, *args, **kw)
    monkeypatch.setattr(make_cover.ImageFont, "truetype", truetype)


def test_without_dejavu_the_text_is_still_drawn(no_system_fonts):
    # Regression (2026-10-20): on a Mac without DejaVu, the tiny fixed-size bitmap font was used
    # and the cover lost every word, silently.
    f = make_cover.font(120)
    assert isinstance(f, ImageFont.FreeTypeFont) and f.size == 120
    assert_text_is_drawn(make_cover.render(600))


def test_no_scalable_font_fails_loudly(no_system_fonts, monkeypatch):
    monkeypatch.setattr(make_cover.ImageFont, "load_default", lambda size=None: object())
    with pytest.raises(RuntimeError, match="No scalable font"):
        make_cover.font(120)


def test_main_writes_a_jpeg(tmp_path):
    out = make_cover.main(tmp_path / "cover.jpg", size=300)
    with Image.open(out) as img:
        assert img.format == "JPEG" and img.size == (300, 300)
