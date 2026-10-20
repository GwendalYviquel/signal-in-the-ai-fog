"""Generate the README diagrams as SVG, in a light and a dark version (assets/diagram-*.svg).

Usage: python tools/make_diagrams.py

Every text sits in a group <g class="box"> with its frame rect, so tests can check in a real
browser that no text overflows its box and nothing leaves the drawing.
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "assets"
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

# Content shared with the tests: the secrets each stage uses, and the episode's word targets.
SECRETS = {"Writing": ["ANTHROPIC_API_KEY", "EDITORIAL_CONTEXT", "FORBIDDEN_TERMS"],
           "Audio": ["ELEVENLABS_API_KEY"]}
EPISODE = [  # (part, voice, words): the prompt's targets, 4 segments
    ("Intro", "host", 45), ("Story of the day", "host", 130), ("The read", "analyst", 110),
    *[part for _ in range(4) for part in (("Facts", "host", 45), ("Read", "analyst", 35))],
    ("Closing", "host", 140),
]
PROMPT_TARGETS = {"story facts": 130, "story read": 110, "segment facts": 45, "segment read": 35,
                  "number of the day": 30, "what to watch": 60, "question": 25}


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


def pipeline(theme):
    """Four stages, each a row of steps, with the secrets each one uses."""
    stages = [
        ("1", "Checks", "weekdays · 7:15 Paris",
         [("GitHub Actions", "scheduled run"), ("Offline tests", "before every run"),
          ("Voice check", "one word per voice")]),
        ("2", "Writing", "Claude + validation",
         [("Claude + web search", "news of the last 24–72 h"), ("Validation", "structure, sources, wording"),
          ("Corrections", "light, or back to research")]),
        ("3", "Audio", "two voices",
         [("Spoken script", "fixed opening and sign-off"), ("ElevenLabs", "host and analyst voices"),
          ("GitHub release", "the episode MP3")]),
        ("4", "Distribution", "free hosting",
         [("RSS feed", "docs/feed.xml"), ("Catalog site", "docs/catalog.json"),
          ("Spotify · Apple", "read the feed")]),
    ]
    step_h, gap, left = 58, 30, 196
    step_w = (W - left - 16 - 2 * gap) / 3
    heights = [16 + step_h + (42 if SECRETS.get(name) else 0) + 16 for _, name, _, _ in stages]
    d = Drawing(sum(heights) + 26 * (len(stages) - 1) + 4, theme)
    c, y = d.c, 2
    for i, ((num, name, sub, steps), h) in enumerate(zip(stages, heights)):
        d.rect(1, y, W - 2, h, c["stage"], c["stage_stroke"], r=16)
        cy = y + 16 + step_h / 2
        d.parts.append('<g class="box">')
        d.rect(18, cy - 17, 34, 34, c["accent"], r=17, cls="frame")
        d.text(35, cy + 5, num, 15, 700, c["accent_ink"])
        d.parts.append("</g>")
        d.box(60, cy - 24, left - 72, 48, [(name, 15, 700, c["ink"]), (sub, 11.5, 400, c["muted"])],
              "none", align="start", pad=6, frame_visible=False)
        for j, (title, detail) in enumerate(steps):
            x = left + j * (step_w + gap)
            d.box(x, y + 16, step_w, step_h, [(title, 13.5, 650, c["ink"]), (detail, 11.5, 400, c["muted"])],
                  c["card"], c["card_stroke"])
            if j:
                d.arrow(f"M{x - gap + 5:.1f},{cy:.1f} L{x - 5:.1f},{cy:.1f}")
        secrets = SECRETS.get(name, [])
        if secrets:
            widths = [text_width(s, 11) + 22 for s in secrets]
            sx = left + (W - 16 - left - sum(widths) - 10 * (len(widths) - 1)) / 2
            for s, sw in zip(secrets, widths):
                d.box(sx, y + 16 + step_h + 14, sw, 24, [(s, 11, 600, c["chip_ink"], True)],
                      c["chip"], c["chip_stroke"], r=12, dash="4 3")
                sx += sw + 10
        if i < len(stages) - 1:
            d.arrow(f"M35,{y + h + 4:.1f} L35,{y + h + 22:.1f}", c["accent"], 2)
        y += h + 26
    return d.svg("The pipeline: checks, writing, audio, distribution")


def episode(theme):
    """The episode as an audio timeline: one bar, coloured by voice, with a gap at each change of voice."""
    d = Drawing(212, theme)
    c = d.c
    gap, same, bar_y, bar_h = 9, 3, 34, 48  # wider gap where the voice changes: the pause
    gaps = [gap if a[1] != b[1] else same for a, b in zip(EPISODE, EPISODE[1:])]
    room = W - 2 - sum(gaps)
    widths = [max(w * room / sum(x for *_, x in EPISODE), 104 if part == "Intro" else 0) for part, _, w in EPISODE]
    widths = [w * room / sum(widths) for w in widths]
    d.text(1, 22, "0:00", 11.5, 500, c["muted"], "start")
    d.text(W - 1, 22, "about 6 minutes", 11.5, 500, c["muted"], "end")
    x, xs = 1, []
    for (part, voice, _), w, g in zip(EPISODE, widths, gaps + [0]):
        fill, stroke, ink = c[voice], c[voice + "_stroke"], c[voice + "_ink"]
        d.box(x, bar_y, w, bar_h, [(part, 12 if w > 60 else 11, 650, ink)], fill, stroke, r=7)
        xs.append((x, x + w))
        x += w + g
    groups = [("Opening", ["3 headlines", "AI disclosure"], 0, 0),
              ("Story of the day", ["facts ~130 · read ~110 words"], 1, 2),
              ("3 or 4 segments, in theme order", ["facts ~45 · read ~35 words each"], 3, 10),
              ("Closing", ["number · what to watch", "question · sign-off"], 11, 11)]
    for title, subs, a, b in groups:
        x0, x1 = xs[a][0] + 3, xs[b][1] - 3
        d.arrow(f"M{x0:.1f},{bar_y + bar_h + 12} L{x0:.1f},{bar_y + bar_h + 18} "
                f"L{x1:.1f},{bar_y + bar_h + 18} L{x1:.1f},{bar_y + bar_h + 12}", c["line"], 1.2, head=False)
        lines = [(title, 12.5, 700, c["ink"])] + [(s, 11, 400, c["muted"]) for s in subs]
        d.box(x0 - 2, bar_y + bar_h + 24, x1 - x0 + 4, 54, lines, "none", frame_visible=False)
    ly = 196
    for i, (label, voice) in enumerate([("Host voice: opening, facts, transitions, closing", "host"),
                                        ("Analyst voice: every read", "analyst")]):
        lx = 1 + i * 380
        d.rect(lx, ly - 10, 14, 14, c[voice], c[voice + "_stroke"], r=4)
        d.box(lx + 20, ly - 14, text_width(label, 12) + 24, 22, [(label, 12, 500, c["ink"])], "none",
              align="start", pad=4, frame_visible=False)
    d.box(W - 200, ly - 14, 199, 22, [("wide gap: 0.6 s pause", 12, 500, c["muted"])], "none",
          frame_visible=False)
    return d.svg("Episode structure: two voices, facts then read")


def generation(theme):
    """Research, submission, validation, and the two kinds of correction loops."""
    d = Drawing(306, theme)
    c = d.c
    gap, bh, by = 30, 76, 8
    bw = (W - 2 - 4 * gap) / 5
    steps = [
        ([("Brief", 13.5, 700, c["ink"]), ("date, themes,", 11.5, 400, c["muted"]),
          ("last 3 scripts", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
        ([("Claude research", 13.5, 700, c["ink"]), ("up to 15", 11.5, 400, c["muted"]),
          ("web searches", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
        ([("submit_episode", 13, 700, c["accent_ink"], True), ("structured episode", 11.5, 400, c["accent_ink"]),
          ("through a tool", 11.5, 400, c["accent_ink"])], c["accent"], c["accent"]),
        ([("Validation", 13.5, 700, c["ink"]), ("structure, sources,", 11.5, 400, c["muted"]),
          ("wording, length", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
        ([("Accepted", 13.5, 700, c["ok_ink"]), ("on to the voices", 11.5, 400, c["ok_ink"])],
         c["ok"], c["ok_stroke"]),
    ]
    centers = []
    for i, (lines, fill, stroke) in enumerate(steps):
        x = i * (bw + gap) + 1
        d.box(x, by, bw, bh, lines, fill, stroke)
        centers.append(x + bw / 2)
        if i:
            d.arrow(f"M{x - gap + 4},{by + bh / 2} L{x - 4},{by + bh / 2}")
    bottom = by + bh
    # The second loop starts at the right edge of Validation, beyond the first loop's label.
    loops = [(centers[3] - 30, centers[2] + 30, 136, "Wording issue", "light correction: episode and errors only",
              c["accent"]),
             (centers[3] + bw / 2 - 16, centers[1], 216, "Needs new content",
              "back to research: a source is never invented", c["warn_stroke"])]
    for x_from, x_to, ly, title, sub, color in loops:
        d.arrow(f"M{x_from:.1f},{bottom + 4} L{x_from:.1f},{ly - 10} Q{x_from:.1f},{ly} {x_from - 10:.1f},{ly} "
                f"L{x_to + 10:.1f},{ly} Q{x_to:.1f},{ly} {x_to:.1f},{ly - 10} L{x_to:.1f},{bottom + 6}", color, 1.8)
        lw = max(text_width(sub, 11.5), text_width(title, 12.5)) + 28
        lx = (x_from + x_to) / 2 - lw / 2
        d.box(lx, ly - 21, lw, 42, [(title, 12.5, 700, c["ink"]), (sub, 11.5, 400, c["muted"])],
              c["stage"], color, r=10)
    d.box(1, 258, W - 2, 44, [("At most 3 attempts. If the episode is still invalid, nothing is published.",
                                13, 600, c["warn_ink"])], c["warn"], c["warn_stroke"], r=12)
    return d.svg("Generation and corrections")


def testing(theme):
    """The three testing layers, and the loop from real runs back to the offline suite."""
    layers = [
        ("Offline suite", ["every push", "before every run", "free"],
         ["Fakes for Claude, ElevenLabs, gh", "Pipeline on a temporary copy", "Catalog in headless Chromium"]),
        ("Mutation checks", ["every regression test", "free"],
         ["Reintroduce the bug", "The suite must fail"]),
        ("Real runs on GitHub", ["on demand", "a few cents"],
         ["Check voices · 3 characters", "Preview or dry run · Claude", "Rehearsal · release deleted"]),
    ]
    card_w, card_h, gap = 812, 104, 28
    d = Drawing(3 * card_h + 2 * gap + 96, theme)
    c = d.c
    for i, (title, badges, steps) in enumerate(layers):
        y = 2 + i * (card_h + gap)
        d.rect(1, y, card_w, card_h, c["stage"], c["stage_stroke"], r=16)
        d.parts.append('<g class="box">')
        d.rect(18, y + 14, 30, 30, c["accent"], r=15, cls="frame")
        d.text(33, y + 34, str(i + 1), 14, 700, c["accent_ink"])
        d.parts.append("</g>")
        d.box(56, y + 14, 220, 30, [(title, 15, 700, c["ink"])], "none", align="start", pad=4,
              frame_visible=False)
        bx = card_w - 16
        for b in reversed(badges):
            bw = text_width(b, 11) + 22
            bx -= bw
            d.box(bx, y + 17, bw, 24, [(b, 11, 600, c["chip_ink"])], c["chip"], c["chip_stroke"], r=12)
            bx -= 8
        sw = (card_w - 36 - 26 * (len(steps) - 1)) / len(steps)
        for j, s in enumerate(steps):
            sx = 18 + j * (sw + 26)
            d.box(sx, y + 56, sw, 34, [(s, 12, 500, c["ink"])], c["card"], c["card_stroke"], r=10)
            if j:
                d.arrow(f"M{sx - 22:.1f},{y + 73} L{sx - 4:.1f},{y + 73}")
        if i < len(layers) - 1:
            d.arrow(f"M33,{y + card_h + 4} L33,{y + card_h + gap - 4}", c["accent"], 2)
    ny = 3 * card_h + 2 * gap + 22
    d.arrow(f"M33,{ny - 18} L33,{ny - 2}", c["accent"], 2)
    d.box(1, ny, card_w, 46, [("Every surprise in a real run becomes a fix and a regression test in the suite",
                               13, 600, c["ok_ink"])], c["ok"], c["ok_stroke"], r=12)
    d.arrow(f"M{card_w + 4},{ny + 23} L{W - 20},{ny + 23} Q{W - 8},{ny + 23} {W - 8},{ny + 11} "
            f"L{W - 8},{40} Q{W - 8},{28} {W - 20},{28} L{card_w + 6},{28}", c["ok_stroke"], 1.8)
    return d.svg("Testing layers")


# Shared with the tests: the crons of the daily workflow and the Paris time they land on.
SCHEDULE = {"publish_at": "04:05", "listen_at": "07:00", "run_minutes": 15,
            "rows": [("Summer time", "UTC+2", [("2:05 UTC", "04:05", True), ("3:05 UTC", "05:05", False)]),
                     ("Winter time", "UTC+1", [("2:05 UTC", "03:05", False), ("3:05 UTC", "04:05", True)])]}


def schedule(theme):
    """A morning in Paris time: the run, the margin left for Spotify, the 7:00 listen, and which
    of the two cron lines publishes on each side of daylight saving time."""
    d = Drawing(346, theme)
    c = d.c
    x0, x1, h0, h1 = 168, W - 28, 1, 8  # the axis shows 1:00 to 8:00, Paris time; room for its labels

    def hx(hhmm):
        h, m = (int(v) for v in hhmm.split(":"))
        return x0 + (h + m / 60 - h0) * (x1 - x0) / (h1 - h0)

    def minutes_later(hhmm, minutes):
        h, m = (int(v) for v in hhmm.split(":"))
        total = h * 60 + m + minutes
        return f"{total // 60:02d}:{total % 60:02d}"

    pub, listen = SCHEDULE["publish_at"], SCHEDULE["listen_at"]
    online = minutes_later(pub, SCHEDULE["run_minutes"])
    margin = (int(listen[:2]) * 60 + int(listen[3:])) - (int(online[:2]) * 60 + int(online[3:]))
    rows_y = [16, 108, 188]
    for y, hgt in zip(rows_y, (78, 66, 66)):
        d.rect(1, y, W - 2, hgt, c["stage"], c["stage_stroke"], r=14)

    # Row 1: every weekday
    y = rows_y[0]
    d.box(10, y + 10, x0 - 24, 58, [("Every weekday", 14, 700, c["ink"]), ("Paris time", 11.5, 400, c["muted"]),
                                    ("holidays included", 11.5, 400, c["muted"])], "none", align="start",
          pad=8, frame_visible=False)
    d.box(hx("01:10"), y + 13, hx("03:45") - hx("01:10"), 52,
          [(f"Run · about {SCHEDULE['run_minutes']} min", 12.5, 700, c["ink"]),
           ("tests, voices, Claude, ElevenLabs,", 11, 400, c["muted"]), ("release, feed and site", 11, 400, c["muted"])],
          c["card"], c["card_stroke"], r=10)
    d.arrow(f"M{hx('03:45') + 4:.1f},{y + 39} L{hx(pub) - 4:.1f},{y + 39}")
    d.parts.append('<g class="box">')
    d.rect(hx(pub), y + 17, hx(online) - hx(pub), 44, c["accent"], c["accent"], r=6, cls="frame")
    d.parts.append("</g>")
    d.box(hx(online) + 6, y + 13, hx(listen) - hx(online) - 12, 52,
          [("Spotify reads the feed", 12.5, 700, c["chip_ink"]),
           (f"about {margin // 60} h {margin % 60:02d} of margin", 11.5, 400, c["chip_ink"])],
          c["chip"], c["chip_stroke"], r=10, dash="4 3")
    d.box(hx(listen) + 2, y + 13, x1 - hx(listen) - 2, 52,
          [("Listen", 13.5, 700, c["ok_ink"]), (listen.lstrip("0"), 12, 600, c["ok_ink"])],
          c["ok"], c["ok_stroke"], r=10)

    # Rows 2 and 3: the two cron lines, each side of daylight saving time
    for (label, offset, runs), y in zip(SCHEDULE["rows"], rows_y[1:]):
        d.box(10, y + 8, x0 - 24, 50, [(label, 14, 700, c["ink"]), (f"Paris = {offset}", 11.5, 400, c["muted"])],
              "none", align="start", pad=8, frame_visible=False)
        d.arrow(f"M{x0 - 6},{y + 33} L{x1},{y + 33}", c["stage_stroke"], 1.2, head=False)
        for cron, local, publishes in runs:
            x = hx(local)
            color = c["ok_stroke"] if publishes else c["line"]
            d.parts.append(f'<circle cx="{x:.1f}" cy="{y + 33}" r="7" fill="{c["ok"] if publishes else c["stage"]}" '
                           f'stroke="{color}" stroke-width="2"/>')
            d.box(x - 46, y + 6, 92, 18, [(cron, 11, 600, c["muted"], True)], "none", frame_visible=False)
            d.box(x - 46, y + 43, 92, 18, [("publishes" if publishes else "skips", 11.5, 700,
                                            c["ok_ink"] if publishes else c["muted"])], "none", frame_visible=False)

    # Guide at listening time (it crosses no label), then the axis
    axis_y = 276
    d.arrow(f"M{hx(listen):.1f},{rows_y[0] + 80} L{hx(listen):.1f},{axis_y - 4}", c["ok_stroke"], 1.2,
            dash="3 4", head=False)
    d.arrow(f"M{x0},{axis_y} L{x1},{axis_y}", c["line"], 1.2, head=False)
    for h in range(h0, h1 + 1):
        x = hx(f"{h:02d}:00")
        d.arrow(f"M{x:.1f},{axis_y - 4} L{x:.1f},{axis_y + 4}", c["line"], 1.2, head=False)
        d.box(x - 22, axis_y + 8, 44, 18, [(f"{h}:00", 11.5, 500, c["muted"])], "none", frame_visible=False)

    # Notes
    notes = ["the cron line decides, not the clock: a late start still works",
             "pause: SCHEDULE_ENABLED=false"]
    nx = 1
    for n in notes:
        nw = text_width(n, 11.5) + 26
        d.box(nx, 316, nw, 26, [(n, 11.5, 500, c["chip_ink"])], c["chip"], c["chip_stroke"], r=13)
        nx += nw + 10
    return d.svg("Schedule: the run at 4:05 Paris time, the margin for Spotify, the 7:00 listen")


DIAGRAMS = {"pipeline": pipeline, "episode": episode, "generation": generation, "testing": testing,
            "schedule": schedule}


def main(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in DIAGRAMS.items():
        for theme in THEMES:
            path = out / f"diagram-{name}-{theme}.svg"
            path.write_text(draw(theme), encoding="utf-8")
            written.append(path)
    print(f"{len(written)} diagrams written to {out}")
    return written


if __name__ == "__main__":
    main()
