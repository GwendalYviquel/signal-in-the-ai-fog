"""FinOps dashboard: what the podcast costs, as SVG in a light and a dark version.

Rebuilt from data/costs.json after every run (engine/costs.py calls write()):
- a KPI row: Claude and ElevenLabs this month, cost per published episode, month projection;
- two charts, one per unit (never two axes): Claude USD per day and ElevenLabs characters per
  day over the last 30 days, stacked by kind of run.
Colors: slots 1-3 of the reference categorical palette, validated in both modes (all pairs).
"""
from __future__ import annotations

import calendar
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from .drawing import THEMES, W, Drawing, text_width

PARIS = ZoneInfo("Europe/Paris")
DAYS = 30
KINDS = ["Episodes", "Script only", "Checks"]  # fixed order: the color follows the kind, never its rank
SERIES = {"light": ["#2a78d6", "#eb6834", "#1baf7a"], "dark": ["#3987e5", "#d95926", "#199e70"]}


def kind(mode: str) -> str:
    return {"publish": "Episodes", "preview": "Script only", "dry run": "Script only"}.get(mode, "Checks")


def paris_day(iso: str) -> dt.date:
    return dt.datetime.fromisoformat(iso).astimezone(PARIS).date()


def usd(run: dict) -> float:
    return run["claude"]["usd"] if run.get("claude") else 0.0


def summary(runs: list[dict], today: dt.date) -> dict:
    """Month-to-date figures, per published episode, and a projection over the month's weekdays."""
    month = [r for r in runs if paris_day(r["time"]).strftime("%Y-%m") == today.strftime("%Y-%m")]
    episodes = [r for r in month if r["mode"] == "publish" and r["outcome"] == "ok"]
    weekdays = sum(1 for d in range(1, calendar.monthrange(today.year, today.month)[1] + 1)
                   if dt.date(today.year, today.month, d).weekday() < 5)
    per_usd = sum(usd(r) for r in episodes) / len(episodes) if episodes else None
    per_chars = sum(r["elevenlabs_characters"] for r in episodes) / len(episodes) if episodes else None
    return {"month": today.strftime("%B %Y"), "claude_usd": sum(usd(r) for r in month),
            "chars": sum(r["elevenlabs_characters"] for r in month), "runs": len(month),
            "episodes": len(episodes), "per_episode_usd": per_usd, "per_episode_chars": per_chars,
            "weekdays": weekdays,
            "projection_usd": per_usd * weekdays if per_usd is not None else None,
            "projection_chars": per_chars * weekdays if per_chars is not None else None,
            "untracked": sum(1 for r in month if "not recorded" in r.get("note", ""))}


def daily(runs: list[dict], today: dt.date, value) -> list[tuple[dt.date, dict[str, float]]]:
    days = [today - dt.timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    totals = {d: {k: 0.0 for k in KINDS} for d in days}
    for r in runs:
        d = paris_day(r["time"])
        if d in totals:
            totals[d][kind(r["mode"])] += value(r)
    return [(d, totals[d]) for d in days]


def nice_max(v: float) -> float:
    """A round axis maximum just above v (1, 2, 2.5 or 5 times a power of ten)."""
    if v <= 0:
        return 1.0
    p = 10 ** len(str(int(v))) / 10 if v >= 1 else 0.1
    while True:
        for m in (1, 2, 2.5, 5, 10):
            if m * p >= v:
                return m * p
        p *= 10


def bar_path(x, y, w, h, r):
    """A bar with rounded data end (top) and a square base."""
    r = min(r, h, w / 2)
    return (f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z")


def chart(d: Drawing, x0, y0, width, height, title, series, fmt, colors):
    c = d.c
    d.box(x0, y0, width, 22, [(title, 13, 700, c["ink"])], "none", align="start", pad=3, frame_visible=False)
    top, bottom, left = y0 + 34, y0 + height - 22, x0 + 44
    vmax = nice_max(max(sum(v.values()) for _, v in series))
    for i in range(5):  # recessive grid, labelled values
        v = vmax * i / 4
        y = bottom - (bottom - top) * i / 4
        d.arrow(f"M{left},{y:.1f} L{x0 + width},{y:.1f}", c["stage_stroke"], 1, head=False)
        d.box(x0, y - 8, 42, 16, [(fmt(v), 10.5, 500, c["muted"])], "none", align="start", pad=3,
              frame_visible=False)
    slot = (x0 + width - left) / len(series)
    bw = max(3.0, slot - 4)
    for i, (day, values) in enumerate(series):
        x = left + i * slot + (slot - bw) / 2
        y = bottom
        stacked = [(k, values[k]) for k in KINDS if values[k] > 0]
        for j, (k, v) in enumerate(stacked):
            h = (bottom - top) * v / vmax
            gap = 2 if j < len(stacked) - 1 else 0  # 2px surface gap between stacked segments
            seg_h = max(h - gap, 1)
            y -= h
            label = f"{day:%b} {day.day} · {k}: {fmt(v)}"
            shape = bar_path(x, y + gap, bw, seg_h, 3) if j == len(stacked) - 1 else \
                f"M{x:.1f},{y + gap:.1f} h{bw:.1f} v{seg_h:.1f} h{-bw:.1f} Z"
            d.parts.append(f'<path d="{shape}" fill="{colors[KINDS.index(k)]}"><title>{label}</title></path>')
        if i % 7 == len(series) % 7 - 1 or i == len(series) - 1:  # a few date labels, last day included
            lx = min(max(x + bw / 2 - 22, left - 4), x0 + width - 44)
            d.box(lx, bottom + 4, 44, 16, [(f"{day:%b} {day.day}", 10.5, 500, c["muted"])], "none",
                  frame_visible=False)
    d.arrow(f"M{left},{bottom} L{x0 + width},{bottom}", c["line"], 1.2, head=False)


def render(runs: list[dict], today: dt.date, theme: str) -> str:
    s = summary(runs, today)
    colors = SERIES[theme]
    d = Drawing(392, theme)
    c = d.c

    def money(v):
        return "—" if v is None else f"${v:,.2f}"

    def credits(v):
        return "—" if v is None else f"{v:,.0f}"

    tiles = [
        (f"Claude · {s['month']}", money(s["claude_usd"]), f"{s['runs']} runs, estimated"),
        (f"ElevenLabs · {s['month']}", credits(s["chars"]), "credits (characters)"),
        ("Per published episode", money(s["per_episode_usd"]),
         f"+ {credits(s['per_episode_chars'])} credits" if s["episodes"] else "no episode yet"),
        ("Month projection", money(s["projection_usd"]),
         f"{credits(s['projection_chars'])} credits · {s['weekdays']} weekdays" if s["episodes"] else "after a first episode"),
    ]
    tw = (W - 2 - 3 * 12) / 4
    for i, (label, value, sub) in enumerate(tiles):
        x = 1 + i * (tw + 12)
        d.rect(x, 1, tw, 92, c["stage"], c["stage_stroke"], r=14)
        d.box(x + 4, 10, tw - 8, 74, [(label, 11.5, 600, c["muted"]), (value, 24, 750, c["ink"]),
                                      (sub, 11, 400, c["muted"])], "none", frame_visible=False)
    ly = 118
    lx = 1
    for k, color in zip(KINDS, colors):
        d.rect(lx, ly - 10, 12, 12, color, r=3)
        label = {"Episodes": "Episodes (publication)", "Script only": "Script only (preview, dry run)",
                 "Checks": "Checks (voices, rehearsals)"}[k]
        bw = text_width(label, 12) + 14
        d.box(lx + 16, ly - 13, bw, 18, [(label, 12, 500, c["ink"])], "none", align="start", pad=2,
              frame_visible=False)
        lx += 16 + bw + 18
    if s["untracked"]:
        d.box(W - 300, ly - 13, 299, 18, [(f"{s['untracked']} earlier Claude runs not tracked", 11, 500,
                                            c["muted"])], "none", frame_visible=False)
    cw = (W - 2 - 28) / 2
    chart(d, 1, 140, cw, 250, f"Claude · USD per day, last {DAYS} days",
          daily(runs, today, usd), lambda v: f"${v:.2f}", colors)
    chart(d, 1 + cw + 28, 140, cw, 250, f"ElevenLabs · characters per day, last {DAYS} days",
          daily(runs, today, lambda r: r["elevenlabs_characters"]), lambda v: f"{v / 1000:.1f}k" if v else "0",
          colors)
    return d.svg(f"FinOps dashboard, {s['month']}")


def write(runs: list[dict], out_dir: Path, today: dt.date | None = None) -> list[Path]:
    today = today or dt.datetime.now(PARIS).date()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for theme in THEMES:
        path = out_dir / f"finops-dashboard-{theme}.svg"
        path.write_text(render(runs, today, theme), encoding="utf-8")
        paths.append(path)
    return paths
