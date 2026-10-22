"""Public corrections: an error found after publication is corrected on the site, in the feed, and
read at the start of the closing part of the next episode.

A correction is kept on the record of the episode it corrects (data/episodes.json):
{"added": "YYYY-MM-DD", "text": "...", "aired_in": None or the date of the episode that read it}.
Its text is spoken as written, so it follows the rules of the voice: no first person, no markdown,
no forbidden term. Example: "The episode of October twentieth gave Mistral Large 4 a two-week
discount. Mistral set it at one week."

Usage: python -m engine.corrections add YYYY-MM-DD "correction text"
       (adds it, then rebuilds the feed, the catalog and the pages)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import generate

ROOT = Path(__file__).resolve().parent.parent
MIN_WORDS, MAX_WORDS = 8, 70


def problems(text: str) -> list[str]:
    """What stops a correction from being read aloud as written."""
    found = []
    n = generate.words(text)
    if not MIN_WORDS <= n <= MAX_WORDS:
        found.append(f"{n} words: a correction is {MIN_WORDS} to {MAX_WORDS} words")
    if m := generate.UNSPEAKABLE.search(text):
        found.append(f"{m.group(0)!r} cannot be read aloud: no markdown, brackets or links")
    if m := generate.FIRST_PERSON.search(text):
        found.append(f"first person {m.group(0)!r}: write \"The episode of October twentieth said...\"")
    if any(term.lower() in text.lower() for term in generate._forbidden_terms()):
        found.append("a forbidden term")
    return found


def add(episodes: list[dict], day: str, text: str, today: dt.date) -> dict:
    """Attach a correction to a published episode; raises ValueError with the reason otherwise."""
    target = next((e for e in episodes if e["date"] == day), None)
    if target is None:
        raise ValueError(f"No published episode on {day}")
    text = " ".join(text.split())
    if issues := problems(text):
        raise ValueError("Correction not added: " + "; ".join(issues))
    entry = {"added": today.isoformat(), "text": text, "aired_in": None}
    target.setdefault("corrections", []).append(entry)
    return entry


def pending(episodes: list[dict]) -> list[dict]:
    """Corrections not read in an episode yet, oldest first, with the date they correct."""
    found = [{"episode": e["date"], **c} for e in episodes for c in e.get("corrections", []) if not c.get("aired_in")]
    return sorted(found, key=lambda c: (c["added"], c["episode"]))


def mark_aired(episodes: list[dict], read: list[dict], day: str) -> None:
    for c in read:
        for entry in next(e for e in episodes if e["date"] == c["episode"]).get("corrections", []):
            if entry["text"] == c["text"] and not entry.get("aired_in"):
                entry["aired_in"] = day


def main(argv: list[str]) -> None:
    from . import catalog, feed, publish, site
    if len(argv) != 3 or argv[0] != "add":
        raise SystemExit('usage: python -m engine.corrections add YYYY-MM-DD "correction text"')
    from . import show as shows
    show = shows.load()
    cfg = show.cfg
    path = show.episodes
    episodes = json.loads(path.read_text(encoding="utf-8"))
    try:
        add(episodes, argv[1], argv[2], dt.date.today())
    except ValueError as e:
        raise SystemExit(str(e)) from None
    path.write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8")
    base_url = show.base_url(publish.pages_url() if os.getenv("GITHUB_REPOSITORY") else site.local_pages_url())
    previews = json.loads(show.previews.read_text(encoding="utf-8")) if show.previews.exists() else []
    feed.write_feed(cfg, episodes, show.docs / "feed.xml", base_url)
    catalog.write_catalog(cfg, episodes, previews, show.data, show.docs / "catalog.json", base_url)
    site.write_site(cfg, show.docs / "catalog.json", show.data, show.docs, base_url)
    print(f"Correction added to the episode of {argv[1]}; it will be read in the next episode.")


if __name__ == "__main__":
    main(sys.argv[1:])
