"""Check that episodes reach Spotify, and measure how long Spotify takes to pick them up.

Spotify's public embed page for a show needs no login: it says "Page not available" until the
show is public, then shows the latest episode. Each check compares that episode with the latest
one in data/episodes.json and records in data/spotify.json when an episode was first seen live.

Usage: python -m podcast.spotify   (see .github/workflows/check-spotify.yml)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
LOG = ROOT / "data" / "spotify.json"
EMBED = "https://open.spotify.com/embed/show/{show_id}"


def show_id(url: str) -> str:
    m = re.fullmatch(r"https://open\.spotify\.com/show/([A-Za-z0-9]{22})", url or "")
    if not m:
        raise SystemExit(f"podcast.spotify_url is not a Spotify show link: {url!r}")
    return m.group(1)


def latest_episode(html: str) -> str | None:
    """Title of the latest episode on the embed page, or None if the show is not available."""
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(entity, dict) or entity.get("type") != "episode":
        return None
    return entity.get("title") or entity.get("name")


def fetch(show: str) -> str:
    r = requests.get(EMBED.format(show_id=show), headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return r.text


def check(cfg: dict, html: str, now: dt.datetime, episodes_path: Path = EPISODES, log_path: Path = LOG) -> str:
    """Compare Spotify with our latest episode; record the first time it is seen live."""
    episodes = json.loads(episodes_path.read_text(encoding="utf-8")) if episodes_path.exists() else []
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    on_spotify = latest_episode(html)
    if not episodes:
        return "No episode published yet."
    ours = max(episodes, key=lambda e: e["published_at"])
    if on_spotify is None:
        return "The show is not available on Spotify yet (review or indexing in progress)."
    if on_spotify.strip() != ours["title"].strip():
        return f"Spotify still shows {on_spotify!r}; our latest episode {ours['title']!r} is not there yet."
    if ours["date"] not in log:
        published = dt.datetime.fromisoformat(ours["published_at"])
        reference = dt.datetime.fromisoformat(ours["catch_up"]["generated_at"]) if ours.get("catch_up") else published
        log[ours["date"]] = {"title": ours["title"], "first_seen_live": now.replace(microsecond=0).isoformat(),
                             "minutes_after_publication": round((now - reference).total_seconds() / 60)}
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    seen = log[ours["date"]]
    return (f"Live on Spotify: {ours['title']!r} (first seen {seen['first_seen_live']}, "
            f"{seen['minutes_after_publication']} minutes after publication).")


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    status = check(cfg, fetch(show_id(cfg["podcast"]["spotify_url"])), dt.datetime.now(dt.timezone.utc))
    print(status)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Spotify\n\n{status}\n")


if __name__ == "__main__":
    main()
