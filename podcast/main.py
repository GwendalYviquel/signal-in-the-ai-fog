"""Pipeline: script (Claude) -> audio (ElevenLabs) -> GitHub release -> RSS feed.

Environment variables:
  DRY_RUN=true  only generate the script (no ElevenLabs call, nothing published)
  PREVIEW=true  generate the script and publish it to the catalog site only
                (no ElevenLabs call, no release, RSS feed unchanged)
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
PREVIEWS = ROOT / "data" / "previews.json"
PREVIEW_SCRIPTS = ROOT / "data" / "previews"
BUILD = ROOT / "build"


def flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def to_markdown(ep: dict, day: dt.date) -> str:
    sources = "\n".join(f"- [{s['title']}]({s['url']})" for s in ep["sources"])
    return (f"# {ep['title']}\n\n_{day.isoformat()}_\n\n{ep['summary']}\n\n"
            f"## Script\n\n{ep['script']}\n\n## Sources\n\n{sources}\n")


def current_time(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(cfg["generation"]["timezone"]))


def themes_covered(structured: dict) -> list[str]:
    themes = [structured["story_of_the_day"]["theme"]] + [s["theme"] for s in structured["segments"]]
    return list(dict.fromkeys(themes))


def check_config(cfg: dict, dry_run: bool) -> None:
    to_fill = [k for k, v in cfg["podcast"].items() if v == "TO_FILL"]
    voices = cfg["tts"].get("voices") or {"host": cfg["tts"].get("voice_id", "TO_FILL")}
    to_fill += [f"tts.voices.{role}" for role, v in voices.items() if v == "TO_FILL"]
    if to_fill and not dry_run:
        raise SystemExit(f"config.yaml: fill in before publishing -> {', '.join(to_fill)}")


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def record(ep: dict, today: dt.date, now: dt.datetime) -> dict:
    return {
        "date": today.isoformat(),
        "title": ep["title"],
        "summary": ep["summary"],
        "headlines": ep["structured"]["headlines"],
        "themes": themes_covered(ep["structured"]),
        "sources": ep["sources"],
        "published_at": now.replace(microsecond=0).isoformat(),
    }


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    dry_run, preview, force = flag("DRY_RUN"), flag("PREVIEW"), flag("FORCE")
    check_config(cfg, dry_run or preview)

    now = current_time(cfg)
    today = now.date()
    if today.weekday() >= 5 and not force:
        print("Weekend: no episode.")
        return

    episodes, previews = load(EPISODES), load(PREVIEWS)
    if any(e["date"] == today.isoformat() for e in episodes) and not force:
        print("Today's episode is already published.")
        return
    if preview and any(e["date"] == today.isoformat() for e in previews) and not force:
        print("Today's preview already exists.")
        return

    if not (dry_run or preview):
        tts.check_voices(cfg["tts"])  # a few characters: fail before paying for the script

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

    base_url = cfg["podcast"].get("base_url") or publish.pages_url()
    previews = [e for e in previews if e["date"] != today.isoformat()]

    if preview:
        # Catalog only, without audio: never added to the RSS feed, so Spotify never sees it.
        PREVIEW_SCRIPTS.mkdir(parents=True, exist_ok=True)
        (PREVIEW_SCRIPTS / f"{today}.md").write_text(md, encoding="utf-8")
        save(PREVIEWS, previews + [record(ep, today, now)])
        catalog.write_catalog(cfg, episodes, load(PREVIEWS), ROOT / "data", ROOT / "docs" / "catalog.json", base_url)
        print("PREVIEW: script published to the catalog, no speech synthesis, RSS feed unchanged.")
        return

    mp3 = BUILD / f"episode-{today}.mp3"
    tts.synthesize(ep["parts"], cfg["tts"], mp3)

    tag = f"episode-{today}"
    if force:
        publish.delete_release(tag)
        episodes = [e for e in episodes if e["date"] != today.isoformat()]
    audio_url = publish.upload_audio(mp3, tag, ep["title"], ep["summary"])

    episodes.append(record(ep, today, now) | {
        "guid": f"{publish.repo()}#{tag}",
        "audio_url": audio_url,
        "audio_bytes": mp3.stat().st_size,
        "duration_seconds": MP3(mp3).info.length,
    })
    save(EPISODES, episodes)
    # Archived only once published: the next episodes treat archived scripts as already aired.
    (SCRIPTS / f"{today}.md").write_text(md, encoding="utf-8")
    save(PREVIEWS, previews)  # a published episode replaces its preview
    (PREVIEW_SCRIPTS / f"{today}.md").unlink(missing_ok=True)  # only once the episode is out

    feed.write_feed(cfg, episodes, ROOT / "docs" / "feed.xml", base_url)
    catalog.write_catalog(cfg, episodes, previews, ROOT / "data", ROOT / "docs" / "catalog.json", base_url)
    print(f"Episode published: {audio_url}")


if __name__ == "__main__":
    main()
