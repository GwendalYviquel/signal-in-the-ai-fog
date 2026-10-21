"""Pipeline: script (Claude) -> audio (ElevenLabs) -> GitHub release -> RSS feed.

Environment variables:
  DRY_RUN=true  only generate the script (no ElevenLabs call, nothing published)
  PREVIEW=true  generate the script and publish it to the catalog site only
                (no ElevenLabs call, no release, RSS feed unchanged)
  FORCE=true    regenerate even on weekends or if today's episode already exists
  AS_SCHEDULED=true  news cutoff at today's publish_at, as if run by the schedule
  EPISODE_DATE=YYYY-MM-DD  catch up a past weekday, with that day's news cutoff (publish_at)
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import catalog, chapters, context, costs, feed, generate, publish, site, tts

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
SCRIPTS = ROOT / "data" / "scripts"
PREVIEWS = ROOT / "data" / "previews.json"
PREVIEW_SCRIPTS = ROOT / "data" / "previews"
BUILD = ROOT / "build"
DOCS = ROOT / "docs"
COST_LEDGER, COST_REPORT, COST_CHARTS = costs.LEDGER, costs.REPORT, costs.CHARTS


def flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes")


def to_markdown(ep: dict, day: dt.date) -> str:
    sources = "\n".join(f"- [{s['title']}]({s['url']})" for s in ep["sources"])
    return (f"# {ep['title']}\n\n_{day.isoformat()}_\n\n{ep['summary']}\n\n"
            f"## Script\n\n{ep['script']}\n\n## Sources\n\n{sources}\n")


def episode_date(now: dt.datetime) -> dt.date | None:
    """EPISODE_DATE (YYYY-MM-DD): catch up a past weekday's episode, with that day's news cutoff."""
    value = os.getenv("EPISODE_DATE", "").strip()
    if not value:
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        raise SystemExit(f"EPISODE_DATE must be YYYY-MM-DD, got {value!r}") from None
    if day >= now.date():
        raise SystemExit(f"EPISODE_DATE {day} is not in the past: catch-ups are for earlier days only")
    if day.weekday() >= 5:
        raise SystemExit(f"EPISODE_DATE {day} is a weekend day: there is no episode to catch up")
    return day


def report_overlaps(ep: dict, day: dt.date, episodes: list[dict]) -> list[str]:
    """Stories shared with the nearest published episodes, by source URL. Reported, not blocking:
    a story may move forward from one day to the next."""
    urls = {s["url"] for s in ep["sources"]}
    nearby = sorted(episodes, key=lambda e: abs((dt.date.fromisoformat(e["date"]) - day).days))[:3]
    found = []
    for other in nearby:
        shared = urls & {s["url"] for s in other.get("sources", [])}
        if shared:
            found.append(f"{len(shared)} source(s) shared with the episode of {other['date']}: "
                         + ", ".join(sorted(shared)))
    for line in found or ["No source shared with the nearest episodes."]:
        print(f"Overlap check: {line}")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Overlap check\n\n" + "\n".join(f"- {line}" for line in found or ["none"]) + "\n\n")
    return found


def current_time(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(cfg["generation"]["timezone"]))


def scheduled_run_is_due(cfg: dict, cron: str, now_utc: dt.datetime) -> bool:
    """GitHub cron runs in UTC; one cron line exists for summer time and one for winter time.
    A run proceeds only if the cron that triggered it lands on publish_at in Paris today.
    It reads the cron, not the clock: a run that starts late is still recognised."""
    if not cron:
        return True  # manual run
    minute, hour = (int(v) for v in cron.split()[:2])
    planned = now_utc.astimezone(dt.timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    local = planned.astimezone(ZoneInfo(cfg["generation"]["timezone"]))
    return f"{local:%H:%M}" == cfg["generation"]["publish_at"]


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


def topics_covered(structured: dict) -> list[str]:
    stories = [structured["story_of_the_day"]] + structured["segments"]
    return list(dict.fromkeys(str(t).strip() for s in stories for t in s.get("topics") or []))


def save_structured(ep: dict, folder: Path, today: dt.date) -> None:
    """The episode as Claude submitted it (layers, labels, topics): the episode and topic pages."""
    (folder / f"{today}.json").write_text(json.dumps(ep["structured"], ensure_ascii=False, indent=1),
                                          encoding="utf-8")


def record(ep: dict, today: dt.date, now: dt.datetime) -> dict:
    return {
        "date": today.isoformat(),
        "title": ep["title"],
        "summary": ep["summary"],
        "headlines": ep["structured"]["headlines"],
        "themes": themes_covered(ep["structured"]),
        "topics": topics_covered(ep["structured"]),
        "sources": ep["sources"],
        "published_at": now.replace(microsecond=0).isoformat(),
    }


def main() -> None:
    """Run, then record what the run spent in data/costs.json and COSTS.md, even if it failed."""
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    dry_run, preview = flag("DRY_RUN"), flag("PREVIEW")
    mode = "dry run" if dry_run else "preview" if preview else "publish"
    spend = {"claude": costs.empty_claude_usage(cfg["generation"]["model"]), "voice_check": 0, "speech": [0]}
    outcome = "failed"
    try:
        outcome = run(cfg, spend) or "ok"
    finally:
        chars = spend["voice_check"] + spend["speech"][0]
        if spend["claude"]["api_calls"] or chars:
            costs.record(cfg, mode, outcome, spend["claude"], chars, ledger=COST_LEDGER, report=COST_REPORT,
                         charts=COST_CHARTS,
                         note=f"voice check {spend['voice_check']} + episode {spend['speech'][0]} characters"
                         if mode == "publish" else "")


def run(cfg: dict, spend: dict) -> str | None:
    dry_run, preview, force = flag("DRY_RUN"), flag("PREVIEW"), flag("FORCE")
    check_config(cfg, dry_run or preview)

    now = current_time(cfg)
    cron = os.getenv("SCHEDULE", "").strip()  # the cron line of a scheduled run, empty otherwise
    if not scheduled_run_is_due(cfg, cron, now):
        print(f"Cron {cron!r} is the other side of daylight saving time today: nothing to do.")
        return
    backfill = episode_date(now)  # a past weekday to catch up, or None
    # Editorial time: the news cutoff given to Claude. Scheduled runs, catch-ups and manual runs
    # with AS_SCHEDULED use publish_at, so a late start never moves the cutoff.
    h, m = (int(v) for v in cfg["generation"]["publish_at"].split(":"))
    if backfill:
        editorial_now = dt.datetime.combine(backfill, dt.time(h, m), now.tzinfo)
    elif cron or flag("AS_SCHEDULED"):
        editorial_now = now.replace(hour=h, minute=m, second=0, microsecond=0)
    else:
        editorial_now = now
    today = backfill or now.date()
    if today.weekday() >= 5 and not force:
        print("Weekend: no episode.")
        return

    episodes, previews = load(EPISODES), load(PREVIEWS)
    if any(e["date"] == today.isoformat() for e in episodes) and not force:
        print(f"The episode of {today} is already published.")
        return
    if not (dry_run or preview or force) and publish.release_exists(f"episode-{today}"):
        # A release without its episode in the data: never publish a second one, never pay twice.
        raise SystemExit(f"A release episode-{today} already exists: run with force to replace it.")
    if preview and any(e["date"] == today.isoformat() for e in previews) and not force:
        print("Today's preview already exists.")
        return

    if not (dry_run or preview):  # a few characters: fail before paying for the script
        results = tts.voice_check_results(cfg["tts"])
        spend["voice_check"] = tts.voice_check_characters(results)
        tts.raise_if_failed(results)

    SCRIPTS.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    # Only episodes aired before this one: a catch-up never sees what was published after its date.
    previous = [p.read_text(encoding="utf-8") for p in sorted(SCRIPTS.glob("*.md"))
                if p.stem < today.isoformat()][-3:]

    request = {"open_items": context.open_items(SCRIPTS, today.isoformat()),
               "topics": context.known_topics(episodes),
               "suggestions": context.accepted_suggestions()}
    ep = generate.generate_episode(cfg, editorial_now, previous, usage=spend["claude"], request=request)
    report_overlaps(ep, today, episodes)
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
        save_structured(ep, PREVIEW_SCRIPTS, today)
        save(PREVIEWS, previews + [record(ep, today, now)])
        catalog.write_catalog(cfg, episodes, load(PREVIEWS), ROOT / "data", DOCS / "catalog.json", base_url)
        site.write_site(cfg, DOCS / "catalog.json", ROOT / "data", DOCS, base_url)
        print("PREVIEW: script published to the catalog, no speech synthesis, RSS feed unchanged.")
        return

    mp3 = BUILD / f"episode-{today}.mp3"
    timeline: list[dict] = []
    tts.synthesize(ep["parts"], cfg["tts"], mp3, billed=spend["speech"], timeline=timeline)

    tag = f"episode-{today}"
    if force:
        publish.delete_release(tag)
        episodes = [e for e in episodes if e["date"] != today.isoformat()]
    audio_url = publish.upload_audio(mp3, tag, ep["title"], ep["summary"])

    published_at = editorial_now if backfill else now  # a catch-up takes its place in the feed
    extra = {"catch_up": {"generated_at": now.replace(microsecond=0).isoformat(),
                          "news_cutoff": editorial_now.isoformat()}} if backfill else {}
    marks = chapters.build_chapters(ep["structured"], timeline)
    if timeline:  # timed transcript and chapters, served next to the episode page
        (DOCS / "episodes").mkdir(parents=True, exist_ok=True)
        (DOCS / "episodes" / f"{today}.vtt").write_text(chapters.build_vtt(timeline), encoding="utf-8")
        (DOCS / "episodes" / f"{today}.chapters.json").write_text(
            json.dumps(chapters.chapters_json(marks), indent=1), encoding="utf-8")
    episodes.append(record(ep, today, published_at) | extra | {
        "guid": f"{publish.repo()}#{tag}",
        "audio_url": audio_url,
        "audio_bytes": mp3.stat().st_size,
        "duration_seconds": tts.mp3_duration(mp3.read_bytes()),
        "chapters": marks,
    })
    save(EPISODES, episodes)
    # Archived only once published: the next episodes treat archived scripts as already aired.
    (SCRIPTS / f"{today}.md").write_text(md, encoding="utf-8")
    save_structured(ep, SCRIPTS, today)
    save(PREVIEWS, previews)  # a published episode replaces its preview
    (PREVIEW_SCRIPTS / f"{today}.md").unlink(missing_ok=True)  # only once the episode is out
    (PREVIEW_SCRIPTS / f"{today}.json").unlink(missing_ok=True)

    feed.write_feed(cfg, episodes, DOCS / "feed.xml", base_url)
    catalog.write_catalog(cfg, episodes, previews, ROOT / "data", DOCS / "catalog.json", base_url)
    site.write_site(cfg, DOCS / "catalog.json", ROOT / "data", DOCS, base_url)
    page_url = site.episode_url(base_url, today.isoformat())
    (BUILD / "published.json").write_text(json.dumps({  # read by the notification step
        "date": today.isoformat(), "title": ep["title"], "page_url": page_url,
        "message": " · ".join(ep["structured"]["headlines"])}, ensure_ascii=False), encoding="utf-8")
    print(f"Episode published: {audio_url}")


if __name__ == "__main__":
    main()
