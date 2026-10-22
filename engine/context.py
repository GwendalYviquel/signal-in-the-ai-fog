"""What the request gives Claude besides the previous scripts: open items to follow up,
the existing topics, and the listener suggestions the owner accepted."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import locale

def watch_pattern(cfg: dict | None = None) -> re.Pattern:
    """The What to watch part of an archived script, between the fixed words of the show's locale."""
    sp = locale.of(cfg or {})["spoken"]
    return re.compile(re.escape(sp["watch"]) + r"\n\n(.*?)\n\n" + re.escape(sp["question"]), re.S)


WATCH = watch_pattern()  # English
SUGGESTION_LABELS = ("topic-suggestion", "accepted")  # only a maintainer can add "accepted"
SUGGESTION_MAX_CHARS = 300  # untrusted text from the public: kept short


def open_items(scripts_dir: Path, before: str, count: int = 5, cfg: dict | None = None) -> list[tuple[str, str]]:
    """(date, What to watch) of the last aired episodes before that date, oldest first."""
    items, watch = [], watch_pattern(cfg)
    for path in sorted(scripts_dir.glob("*.md")):
        if path.stem >= before:
            continue
        if m := watch.search(path.read_text(encoding="utf-8")):
            items.append((path.stem, " ".join(m.group(1).split())))
    return items[-count:]


def known_topics(episodes: list[dict]) -> list[str]:
    """Every topic already used, most frequent first, so Claude reuses their spelling."""
    counts: dict[str, int] = {}
    for ep in episodes:
        for topic in ep.get("topics", []):
            counts[topic] = counts.get(topic, 0) + 1
    return sorted(counts, key=lambda t: (-counts[t], t.lower()))


def _one_line(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def accepted_suggestions(limit: int = 10) -> list[str]:
    """Open issues labelled topic-suggestion and accepted. Never blocks an episode: [] on any failure."""
    cmd = ["gh", "issue", "list", "--state", "open", "--limit", str(limit), "--json", "number,title,body"]
    for label in SUGGESTION_LABELS:
        cmd += ["--label", label]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        issues = json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        issues = None
    if not isinstance(issues, list):
        print("Listener suggestions: could not read the issues, none used")
        return []
    found = [f"#{i['number']} {_one_line(i.get('title', ''), 120)}: "
             f"{_one_line(i.get('body', ''), SUGGESTION_MAX_CHARS)}" for i in issues]
    print(f"Listener suggestions: {len(found)} accepted")
    return found
