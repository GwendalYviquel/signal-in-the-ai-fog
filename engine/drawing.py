"""Drawing helpers shared by the README diagrams (tools/make_diagrams.py) and the FinOps
dashboard (engine/finops.py): same palette, light and dark themes, and boxes whose text can be
checked in a browser (every text sits in a <g class="box"> with its frame rect)."""
from xml.sax.saxutils import escape

W = 880  # GitHub's README column: the drawings scale down from here, never up
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

THEMES = {
    "light": dict(ink="#1f2333", muted="#5b6178", line="#a3a9bf", stage="#ffffff", stage_stroke="#e3e6f0",
                  card="#f6f7fb", card_stroke="#dfe3ee", host="#e3fbf7", host_stroke="#14a394",
                  host_ink="#0a4a43", analyst="#efe9ff", analyst_stroke="#7b52e0", analyst_ink="#3a1d6e",
                  accent="#6d3fd6", accent_ink="#ffffff", ok="#e3fbf7", ok_stroke="#14a394", ok_ink="#0a4a43",
                  warn="#fff4e0", warn_stroke="#e8a33a", warn_ink="#7a4b00", chip="#f4f1ff",
                  chip_stroke="#b9a5f2", chip_ink="#4b2a96"),
    "dark": dict(ink="#e6e8f0", muted="#a0a6bd", line="#5d6480", stage="#0f141d", stage_stroke="#262d3d",
                 card="#161b26", card_stroke="#2d3446", host="#0e3a35", host_stroke="#3ee6cc",
                 host_ink="#d6fff8", analyst="#251c46", analyst_stroke="#a98bff", analyst_ink="#ece6ff",
                 accent="#8f6cf0", accent_ink="#ffffff", ok="#0e3a35", ok_stroke="#3ee6cc", ok_ink="#d6fff8",
                 warn="#3a2a10", warn_stroke="#e8a33a", warn_ink="#ffd79a", chip="#221a3f",
                 chip_stroke="#6f58c9", chip_ink="#d8ccff"),
}


class Drawing:
    def __init__(self, height, theme):
        self.h, self.c, self.parts, self.markers = height, THEMES[theme], [], set()

    def rect(self, x, y, w, h, fill, stroke="none", r=10, dash=None, width=1.2, cls=None):
        attrs = f' stroke-dasharray="{dash}"' if dash else ""
        attrs += f' class="{cls}"' if cls else ""
        self.parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{attrs}/>')

    def text(self, x, y, s, size=13, weight=400, color=None, anchor="middle", mono=False):
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO if mono else FONT}" '
                          f'font-size="{size}" font-weight="{weight}" fill="{color or self.c["ink"]}" '
                          f'text-anchor="{anchor}">{escape(s)}</text>')

    def box(self, x, y, w, h, lines, fill, stroke="none", r=12, dash=None, align="middle", pad=14,
            frame_visible=True):
        """A frame with lines of (text, size, weight, color, mono) centred vertically inside."""
        self.parts.append('<g class="box">')
        if frame_visible:
            self.rect(x, y, w, h, fill, stroke, r, dash, cls="frame")
        else:
            self.rect(x, y, w, h, "none", "none", r, cls="frame")
        heights = [ln[1] * 1.32 for ln in lines]
        cy = y + (h - sum(heights)) / 2
        tx = x + w / 2 if align == "middle" else x + pad
        for (s, size, weight, color, *mono), lh in zip(lines, heights):
            cy += lh
            self.text(tx, cy - lh * 0.28, s, size, weight, color, align, bool(mono and mono[0]))
        self.parts.append("</g>")

    def arrow(self, d, color=None, width=1.6, dash=None, head=True):
        color = color or self.c["line"]
        marker = "a" + color.lstrip("#")
        if head and marker not in self.markers:
            self.markers.add(marker)
            self.parts.insert(0, f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="8.5" refY="5" '
                                 f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                                 f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker></defs>')
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        extra += f' marker-end="url(#{marker})"' if head else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
                          f'stroke-linecap="round" stroke-linejoin="round"{extra}/>')

    def svg(self, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" '
                f'height="{self.h}" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
                + "".join(self.parts) + "</svg>\n")


def text_width(s, size):
    return len(s) * size * 0.56
