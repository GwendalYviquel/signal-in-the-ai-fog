"""Pipeline: script (Claude) -> audio (ElevenLabs) -> GitHub release -> RSS feed.

Environment variables:
  DRY_RUN=true  only generate the script (no ElevenLabs call, nothing published)
  FORCE=true    regenerate even on weekends or if today's episode already exists
"""
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from mutagen.mp3 import MP3

from . import catalog, feed, generate, publish, tts

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
SCRIPTS = ROOT / "data" / "scripts"
BUILD = ROOT / "build"


def flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def to_markdown(ep: dict, day: dt.date) -> str:
    sources = "\n".join(f"- [{s['title']}]({s['url']})" for s in ep["sources"])
    return (f"# {ep['title']}\n\n_{day.isoformat()}_\n\n{ep['summary']}\n\n"
            f"## Script\n\n{ep['script']}\n\n## Sources\n\n{sources}\n")


def themes_covered(structured: dict) -> list[str]:
    themes = [structured["story_of_the_day"]["theme"]] + [s["theme"] for s in structured["segments"]]
    return list(dict.fromkeys(themes))


def check_config(cfg: dict, dry_run: bool) -> None:
    to_fill = [k for k, v in cfg["podcast"].items() if v == "TO_FILL"]
    if not dry_run and cfg["tts"]["voice_id"] == "TO_FILL":
        to_fill.append("tts.voice_id")
    if to_fill and not dry_run:
        raise SystemExit(f"config.yaml: fill in before publishing -> {', '.join(to_fill)}")


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    dry_run, force = flag("DRY_RUN"), flag("FORCE")
    check_config(cfg, dry_run)

    now = dt.datetime.now(ZoneInfo(cfg["generation"]["timezone"]))
    today = now.date()
    if today.weekday() >= 5 and not force:
        print("Weekend: no episode.")
        return

    episodes = json.loads(EPISODES.read_text(encoding="utf-8")) if EPISODES.exists() else []
    if any(e["date"] == today.isoformat() for e in episodes) and not force:
        print("Today's episode is already published.")
        return

    SCRIPTS.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    previous = [p.read_text(encoding="utf-8") for p in sorted(SCRIPTS.glob("*.md"))
                if p.stem != today.isoformat()][-3:]

    ep = generate.generate_episode(cfg, now, previous)
    md = to_markdown(ep, today)
    (BUILD / f"{today}.md").write_text(md, encoding="utf-8")
    print(md)
    if dry_run:
        print("DRY_RUN: script generated, no speech synthesis or publication.")
        return

    (SCRIPTS / f"{today}.md").write_text(md, encoding="utf-8")
    mp3 = BUILD / f"episode-{today}.mp3"
    tts.synthesize(ep["script"], cfg["tts"], mp3)

    tag = f"episode-{today}"
    if force:
        publish.delete_release(tag)
        episodes = [e for e in episodes if e["date"] != today.isoformat()]
    audio_url = publish.upload_audio(mp3, tag, ep["title"], ep["summary"])

    episodes.append({
        "date": today.isoformat(),
        "guid": f"{publish.repo()}#{tag}",
        "title": ep["title"],
        "summary": ep["summary"],
        "headlines": ep["structured"]["headlines"],
        "themes": themes_covered(ep["structured"]),
        "sources": ep["sources"],
        "published_at": now.replace(microsecond=0).isoformat(),
        "audio_url": audio_url,
        "audio_bytes": mp3.stat().st_size,
        "duration_seconds": MP3(mp3).info.length,
    })
    EPISODES.write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8")

    base_url = cfg["podcast"].get("base_url") or publish.pages_url()
    feed.write_feed(cfg, episodes, ROOT / "docs" / "feed.xml", base_url)
    catalog.write_catalog(cfg, episodes, SCRIPTS, ROOT / "docs" / "catalog.json", base_url)
    print(f"Episode published: {audio_url}")


if __name__ == "__main__":
    main()
