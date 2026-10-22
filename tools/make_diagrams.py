"""Generate the README diagrams as SVG, in a light and a dark version (assets/diagram-*.svg).

Usage: python tools/make_diagrams.py

Every text sits in a group <g class="box"> with its frame rect, so tests can check in a real
browser that no text overflows its box and nothing leaves the drawing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.drawing import THEMES, W, Drawing, text_width  # noqa: E402,F401

OUT = Path(__file__).resolve().parent.parent / "assets"

# Content shared with the tests: the secrets each stage uses, and the episode's word targets.
SECRETS = {"Writing": ["ANTHROPIC_API_KEY", "EDITORIAL_CONTEXT", "FORBIDDEN_TERMS"],
           "Audio": ["ELEVENLABS_API_KEY"], "Distribution": ["NTFY_TOPIC"]}
EPISODE = [  # (part, voice, words): the prompt's targets, 4 segments
    ("Intro", "host", 45), ("Story of the day", "host", 130), ("The read", "analyst", 110),
    *[part for _ in range(4) for part in (("Facts", "host", 45), ("Read", "analyst", 35))],
    ("Closing", "host", 140),
]
PROMPT_TARGETS = {"story facts": 130, "story read": 110, "segment facts": 45, "segment read": 35,
                  "number of the day": 30, "what to watch": 60, "question": 25}


def pipeline(theme):
    """Four stages, each a row of steps, with the secrets each one uses."""
    stages = [
        ("1", "Checks", "weekdays, 4:05",
         [("GitHub Actions", "schedule, watchdog"), ("Offline tests", "before every run"),
          ("Voice check", "one word per voice")]),
        ("2", "Writing", "Claude + validation",
         [("Claude + web search", "news, open items, topics"), ("Validation", "sources, wording, fact-check"),
          ("Corrections", "light, or back to research")]),
        ("3", "Audio", "two voices",
         [("Spoken script", "fixed opening and sign-off"), ("ElevenLabs", "host and analyst voices"),
          ("GitHub release", "the episode MP3")]),
        ("4", "Distribution", "free hosting",
         [("RSS feed", "chapters, transcript"), ("Catalog site", "episode and topic pages"),
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
              ("Closing", ["follow-up · number", "watch · question · end"], 11, 11)]
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
          ("scripts, open items", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
        ([("Claude research", 13.5, 700, c["ink"]), ("up to 15", 11.5, 400, c["muted"]),
          ("web searches", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
        ([("submit_episode", 13, 700, c["accent_ink"], True), ("structured episode", 11.5, 400, c["accent_ink"]),
          ("through a tool", 11.5, 400, c["accent_ink"])], c["accent"], c["accent"]),
        ([("Validation", 13.5, 700, c["ink"]), ("sources, wording,", 11.5, 400, c["muted"]),
          ("fact-check (Haiku)", 11.5, 400, c["muted"])], c["card"], c["card_stroke"]),
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
SCHEDULE = {"publish_at": "04:05", "listen_at": "07:00", "run_minutes": 5, "cron": "7,22,37,52 2-5 * * 1-5",
            "rows": [("Summer time", "UTC+2", 2), ("Winter time", "UTC+1", 1)]}


def attempt_times(cron: str, offset_hours: int) -> list[str]:
    """Paris HH:MM of every attempt of a "m1,m2,... h1-h2 * * 1-5" cron line at that UTC offset."""
    minutes, hours = cron.split()[:2]
    h0, h1 = (int(v) for v in hours.split("-"))
    return [f"{h + offset_hours:02d}:{int(m):02d}" for h in range(h0, h1 + 1) for m in minutes.split(",")]


def schedule(theme):
    """A morning in Paris time: the attempts, the first one that publishes, the margin left for
    Spotify and the 7:00 listen, on each side of daylight saving time."""
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
    first = min(a for a in attempt_times(SCHEDULE["cron"], 2) if a >= pub)
    online = minutes_later(first, SCHEDULE["run_minutes"])
    margin = (int(listen[:2]) * 60 + int(listen[3:])) - (int(online[:2]) * 60 + int(online[3:]))
    rows_y = [16, 108, 188]
    for y, hgt in zip(rows_y, (78, 66, 66)):
        d.rect(1, y, W - 2, hgt, c["stage"], c["stage_stroke"], r=14)

    # Row 1: every weekday
    y = rows_y[0]
    d.box(10, y + 10, x0 - 24, 58, [("Every weekday", 14, 700, c["ink"]), ("Paris time", 11.5, 400, c["muted"]),
                                    ("holidays included", 11.5, 400, c["muted"])], "none", align="start",
          pad=8, frame_visible=False)
    d.box(hx("01:10"), y + 13, hx("03:50") - hx("01:10"), 52,
          [(f"Run · about {SCHEDULE['run_minutes']} min", 12.5, 700, c["ink"]),
           ("tests, voices, Claude, fact-check,", 11, 400, c["muted"]), ("ElevenLabs, release, feed, site", 11, 400, c["muted"])],
          c["card"], c["card_stroke"], r=10)
    d.arrow(f"M{hx('03:50') + 4:.1f},{y + 39} L{hx(first) - 4:.1f},{y + 39}")
    d.parts.append('<g class="box">')
    d.rect(hx(first), y + 17, max(hx(online) - hx(first), 6), 44, c["accent"], c["accent"], r=4, cls="frame")
    d.parts.append("</g>")
    d.box(hx(online) + 8, y + 13, hx(listen) - hx(online) - 14, 52,
          [("Spotify reads the feed", 12.5, 700, c["chip_ink"]),
           (f"about {margin // 60} h {margin % 60:02d} of margin", 11.5, 400, c["chip_ink"])],
          c["chip"], c["chip_stroke"], r=10, dash="4 3")
    d.box(hx(listen) + 2, y + 13, x1 - hx(listen) - 2, 52,
          [("Listen", 13.5, 700, c["ok_ink"]), (listen.lstrip("0"), 12, 600, c["ok_ink"])],
          c["ok"], c["ok_stroke"], r=10)

    # Rows 2 and 3: the attempts of the one cron line, each side of daylight saving time
    for (label, offset_label, offset), y in zip(SCHEDULE["rows"], rows_y[1:]):
        d.box(10, y + 8, x0 - 24, 50, [(label, 14, 700, c["ink"]), (f"Paris = {offset_label}", 11.5, 400, c["muted"])],
              "none", align="start", pad=8, frame_visible=False)
        d.arrow(f"M{x0 - 6},{y + 33} L{x1},{y + 33}", c["stage_stroke"], 1.2, head=False)
        times = [a for a in attempt_times(SCHEDULE["cron"], offset) if a <= "08:00"]
        start = min(a for a in times if a >= pub)
        for a in times:
            x = hx(a)
            if a == start:
                d.parts.append(f'<circle cx="{x:.1f}" cy="{y + 33}" r="7" fill="{c["ok"]}" stroke="{c["ok_stroke"]}" '
                               'stroke-width="2"/>')
            else:
                d.parts.append(f'<circle cx="{x:.1f}" cy="{y + 33}" r="3.5" fill="{c["stage"]}" '
                               f'stroke="{c["line"]}" stroke-width="1.5"/>')
        d.box(hx(start) - 56, y + 6, 112, 18, [(f"{start.lstrip('0')} publishes", 11.5, 700, c["ok_ink"])],
              "none", frame_visible=False)
        later = [a for a in times if a > start]
        d.box(hx(later[0]) - 4, y + 43, hx(later[-1]) - hx(later[0]) + 8, 18,
              [("then every 15 min: stops at once, episode out", 11, 500, c["muted"])], "none", frame_visible=False)
        early = [a for a in times if a < pub]
        if early:
            d.box(hx(early[0]) - 30, y + 43, hx(early[-1]) - hx(early[0]) + 60, 18,
                  [("before 4:05: skip", 11, 500, c["muted"])], "none", frame_visible=False)

    # Guide at listening time (it crosses no label), then the axis
    axis_y = 276
    d.arrow(f"M{hx(listen):.1f},{rows_y[0] + 80} L{hx(listen):.1f},{rows_y[1] - 2}", c["ok_stroke"], 1.2,
            dash="3 4", head=False)
    d.arrow(f"M{x0},{axis_y} L{x1},{axis_y}", c["line"], 1.2, head=False)
    for h in range(h0, h1 + 1):
        x = hx(f"{h:02d}:00")
        d.arrow(f"M{x:.1f},{axis_y - 4} L{x:.1f},{axis_y + 4}", c["line"], 1.2, head=False)
        d.box(x - 22, axis_y + 8, 44, 18, [(f"{h}:00", 11.5, 500, c["muted"])], "none", frame_visible=False)

    # Notes
    notes = ["an attempt started late still publishes", "after 2 failed attempts: stop", "pause: SCHEDULE_ENABLED=false"]
    nx = 1
    for n in notes:
        nw = text_width(n, 11.5) + 26
        d.box(nx, 316, nw, 26, [(n, 11.5, 500, c["chip_ink"])], c["chip"], c["chip_stroke"], r=13)
        nx += nw + 10
    return d.svg("Schedule: attempts every 15 minutes from 4:05 Paris time, the margin for Spotify, the 7:00 listen")


# The test plan: every test file belongs to one area (a test checks none is forgotten).
TEST_AREAS = [
    ("Writing", "Claude, checks, fact-check", ["validate", "generate", "prompt", "assemble", "context",
                                                    "factcheck", "locale"]),
    ("Voices", "ElevenLabs, chapters", ["tts", "chapters"]),
    ("Publication", "every run mode, end to end", ["main", "catch_up", "publish", "feed_catalog", "rehearsal",
                                                   "offline_rehearsal", "corrections"]),
    ("Schedule", "4:05, watchdog, alerts", ["schedule", "watchdog", "notify", "scheduler"]),
    ("Money and audience", "costs, downloads, Spotify", ["costs", "finops", "stats", "spotify"]),
    ("Catalog site", "pages, real browser", ["site", "pages"]),
    ("Visuals and docs", "cover, diagrams, README", ["cover", "docs"]),
    ("Repository and CI", "workflows, secrets, privacy", ["repo"]),
]
TESTS = Path(__file__).resolve().parent.parent / "tests"
TESTING_MD = Path(__file__).resolve().parent.parent / "TESTING.md"


def test_counts() -> dict[str, int]:
    return {f.stem[5:]: f.read_text(encoding="utf-8").count("\ndef test_") for f in sorted(TESTS.glob("test_*.py"))}


def real_runs() -> int:
    journal = TESTING_MD.read_text(encoding="utf-8").split("## Journal of real runs", 1)[1].split("\n## ", 1)[0]
    return sum(1 for line in journal.splitlines() if line.startswith("| 20"))


def testplan(theme):
    """Every area of the offline suite with its test files, and the layers around it."""
    counts = test_counts()
    cols, gap = 4, 12
    rows = [TEST_AREAS[i:i + cols] for i in range(0, len(TEST_AREAS), cols)]
    heights = [62 + 21 * max(len(files) for *_, files in row) + 8 for row in rows]  # each row fits its longest card
    d = Drawing(80 + sum(heights) + gap * len(rows) + 30, theme)
    c = d.c
    total = sum(counts.values())
    kpis = [(f"{total}", "test functions, offline"), (f"{len(counts)}", "test files"),
            (f"{real_runs()}", "real runs in the journal"), ("every push", "and before every run")]
    kw = (W - 2 - 3 * 12) / 4
    for i, (value, label) in enumerate(kpis):
        x = 1 + i * (kw + 12)
        d.box(x, 1, kw, 64, [(value, 22, 750, c["ink"]), (label, 11.5, 500, c["muted"])],
              c["stage"], c["stage_stroke"], r=14)
    cw = (W - 2 - (cols - 1) * gap) / cols
    for i, (title, sub, files) in enumerate(TEST_AREAS):
        r = i // cols
        ch = heights[r]
        x, y = 1 + (i % cols) * (cw + gap), 80 + sum(heights[:r]) + gap * r
        d.rect(x, y, cw, ch, c["stage"], c["stage_stroke"], r=14)
        area_total = sum(counts[f] for f in files)
        d.box(x + 8, y + 10, cw - 58, 40, [(title, 13.5, 700, c["ink"]), (sub, 11, 400, c["muted"])],
              "none", align="start", pad=4, frame_visible=False)
        d.box(x + cw - 50, y + 12, 40, 26, [(str(area_total), 13, 700, c["accent_ink"])], c["accent"], c["accent"], r=13)
        for j, f in enumerate(files):
            fy = y + 58 + j * 21
            d.box(x + 10, fy, cw - 20, 18, [(f"test_{f}.py", 11, 500, c["ink"], True)], "none", align="start",
                  pad=4, frame_visible=False)
            d.box(x + cw - 44, fy, 34, 18, [(str(counts[f]), 11, 700, c["muted"])], "none", frame_visible=False)
    ny = 80 + sum(heights) + gap * len(rows)
    notes = [("Mutation checks", "each regression test fails if its bug returns"),
             ("Real runs", "voice checks, previews, dry runs, rehearsals, episodes")]
    nw = (W - 2 - 12) / 2
    for i, (title, sub) in enumerate(notes):
        d.box(1 + i * (nw + 12), ny, nw, 22, [(f"{title}: {sub}", 11.5, 600, c["chip_ink"])],
              c["chip"], c["chip_stroke"], r=11)
    return d.svg(f"Test plan: {total} offline tests in {len(counts)} files")


DIAGRAMS = {"testplan": testplan, "pipeline": pipeline, "episode": episode, "generation": generation, "testing": testing,
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
