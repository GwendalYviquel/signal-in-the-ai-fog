"""Pipeline of one show: script (Claude) -> audio (ElevenLabs) -> GitHub release -> RSS feed.

Environment variables:
  SHOW=<slug>   the show (shows/<slug>/), signal-in-the-ai-fog by default
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

from . import catalog, chapters, context, corrections, costs, feed, generate, publish, site, tts, watchdog
from . import show as shows


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


def report_factcheck(ep: dict) -> str:
    """One line for the log, the run summary and the notification; the doubts that remain."""
    fc = ep.get("factcheck") or {}
    if not fc:
        return ""
    line = (f"Fact-check: {fc['checked']} claims checked, {len(fc['doubts'])} doubt(s) left, "
            f"{len(fc['unverifiable'])} part(s) unverifiable")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Fact-check\n\n" + line + "\n\n" + "".join(f"- {d}\n" for d in fc["doubts"])
                    + (f"\nUnverifiable: {', '.join(fc['unverifiable'])}\n" if fc["unverifiable"] else "") + "\n")
    for d in fc["doubts"]:
        print(f"Fact-check doubt left: {d}")
    return line


def current_time(cfg: dict) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(cfg["generation"]["timezone"]))


def scheduled_run_is_due(cfg: dict, cron: str, now_utc: dt.datetime) -> bool:
    """Scheduled runs are attempts every 15 minutes on weekday mornings, one cron line for both
    seasons. An attempt goes on once it is publish_at or later in Paris; the duplicate guards stop
    the others once the episode is out. It reads the clock: an attempt GitHub starts hours late
    still publishes the day's episode, with the news cutoff at publish_at.

    Learning (2026-10-21/22): with one run at 4:05, GitHub dropped the morning's run or started it
    five hours late, and there was no episode at 7:00."""
    if not cron:
        return True  # manual run
    local = now_utc.astimezone(ZoneInfo(cfg["generation"]["timezone"]))
    return f"{local:%H:%M}" >= cfg["generation"]["publish_at"]


def failed_attempts_today(today: dt.date) -> int:
    """Daily runs that failed today; 0 if GitHub cannot be asked (the attempt then goes on)."""
    try:
        return sum(r["conclusion"] == "failure" for r in watchdog.daily_runs_today(today))
    except (RuntimeError, OSError, ValueError) as e:
        print(f"Could not count today's failed attempts ({e}): going on.")
        return 0


def themes_covered(structured: dict) -> list[str]:
    themes = [structured["story_of_the_day"]["theme"]] + [s["theme"] for s in structured["segments"]]
    return list(dict.fromkeys(themes))


def check_config(cfg: dict, dry_run: bool) -> None:
    to_fill = [k for k, v in cfg["podcast"].items() if v == "TO_FILL"]
    voices = cfg["tts"].get("voices") or {"host": cfg["tts"].get("voice_id", "TO_FILL")}
    to_fill += [f"tts.voices.{role}" for role, v in voices.items() if v == "TO_FILL"]
    if to_fill and not dry_run:
        raise SystemExit(f"show.yaml: fill in before publishing -> {', '.join(to_fill)}")


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


def main(show: shows.Show | None = None) -> None:
    """Run, then record what the run spent in the show's costs.json and COSTS.md, even if it failed."""
    show = show or shows.load()
    cfg = show.cfg
    dry_run, preview = flag("DRY_RUN"), flag("PREVIEW")
    mode = "dry run" if dry_run else "preview" if preview else "publish"
    spend = {"claude": costs.empty_claude_usage(cfg["generation"]["model"]), "voice_check": 0, "speech": [0]}
    outcome = "failed"
    try:
        outcome = run(show, spend) or "ok"
    finally:
        chars = spend["voice_check"] + spend["speech"][0]
        if spend["claude"]["api_calls"] or chars:
            costs.record(cfg, mode, outcome, spend["claude"], chars, ledger=show.cost_ledger,
                         report=show.cost_report, charts=show.charts,
                         note=f"voice check {spend['voice_check']} + episode {spend['speech'][0]} characters"
                         if mode == "publish" else "")


def run(show: shows.Show, spend: dict) -> str | None:
    cfg = show.cfg
    dry_run, preview, force = flag("DRY_RUN"), flag("PREVIEW"), flag("FORCE")
    check_config(cfg, dry_run or preview)

    now = current_time(cfg)
    cron = os.getenv("SCHEDULE", "").strip()  # the cron line of a scheduled run, empty otherwise
    if not scheduled_run_is_due(cfg, cron, now):
        print(f"Attempt at {now:%H:%M}, before {cfg['generation']['publish_at']} Paris time: nothing to do.")
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

    episodes, previews = load(show.episodes), load(show.previews)
    if any(e["date"] == today.isoformat() for e in episodes) and not force:
        print(f"The episode of {today} is already published.")
        return
    if cron and failed_attempts_today(today) >= watchdog.MAX_FAILED_RUNS:
        # Each failed attempt paid Claude: after two, the next attempts stop until someone looks.
        print(f"{watchdog.MAX_FAILED_RUNS} attempts already failed today: stopping, see the failed runs.")
        return
    tag = show.tag(today.isoformat())
    if not (dry_run or preview or force) and publish.release_exists(tag):
        # A release without its episode in the data: never publish a second one, never pay twice.
        raise SystemExit(f"A release episode-{today} already exists: run with force to replace it.")
    if preview and any(e["date"] == today.isoformat() for e in previews) and not force:
        print("Today's preview already exists.")
        return

    if not (dry_run or preview):  # a few characters: fail before paying for the script
        results = tts.voice_check_results(cfg["tts"])
        spend["voice_check"] = tts.voice_check_characters(results)
        tts.raise_if_failed(results)

    show.scripts.mkdir(parents=True, exist_ok=True)
    show.build.mkdir(parents=True, exist_ok=True)
    # Only episodes aired before this one: a catch-up never sees what was published after its date.
    previous = [p.read_text(encoding="utf-8") for p in sorted(show.scripts.glob("*.md"))
                if p.stem < today.isoformat()][-3:]

    request = {"open_items": context.open_items(show.scripts, today.isoformat(), cfg=cfg),
               "topics": context.known_topics(episodes),
               "suggestions": context.accepted_suggestions()}
    ep = generate.generate_episode(cfg, editorial_now, previous, usage=spend["claude"], request=request, show=show)
    report_overlaps(ep, today, episodes)
    report_factcheck(ep)
    # Corrections of earlier episodes, read as written before the number of the day. Not in a
    # catch-up: it would read a correction published after its own date.
    to_read = [] if backfill else corrections.pending(episodes)
    if to_read:
        ep["structured"]["corrections"] = [{"episode": c["episode"], "text": c["text"]} for c in to_read]
        ep["script"] = generate.assemble(ep["structured"], cfg, editorial_now)
        ep["parts"] = generate.assemble_parts(ep["structured"], cfg, editorial_now)
        print(f"Corrections read in this episode: {len(to_read)}")
    md = to_markdown(ep, today)
    (show.build / f"{today}.md").write_text(md, encoding="utf-8")
    print(md)
    if dry_run:
        print("DRY_RUN: script generated, no speech synthesis or publication.")
        return

    base_url = show.base_url("" if cfg["podcast"].get("base_url") else publish.pages_url())
    previews = [e for e in previews if e["date"] != today.isoformat()]

    if preview:
        # Catalog only, without audio: never added to the RSS feed, so Spotify never sees it.
        show.preview_scripts.mkdir(parents=True, exist_ok=True)
        (show.preview_scripts / f"{today}.md").write_text(md, encoding="utf-8")
        save_structured(ep, show.preview_scripts, today)
        save(show.previews, previews + [record(ep, today, now)])
        catalog.write_catalog(cfg, episodes, load(show.previews), show.data, show.docs / "catalog.json", base_url)
        site.write_site(cfg, show.docs / "catalog.json", show.data, show.docs, base_url)
        print("PREVIEW: script published to the catalog, no speech synthesis, RSS feed unchanged.")
        return

    mp3 = show.build / f"{tag}.mp3"
    timeline: list[dict] = []
    tts.synthesize(ep["parts"], cfg["tts"], mp3, billed=spend["speech"], timeline=timeline)

    if force:
        publish.delete_release(tag)
        episodes = [e for e in episodes if e["date"] != today.isoformat()]
    audio_url = publish.upload_audio(mp3, tag, ep["title"], ep["summary"])

    published_at = editorial_now if backfill else now  # a catch-up takes its place in the feed
    extra = {"catch_up": {"generated_at": now.replace(microsecond=0).isoformat(),
                          "news_cutoff": editorial_now.isoformat()}} if backfill else {}
    marks = chapters.build_chapters(ep["structured"], timeline, cfg)
    if timeline:  # timed transcript and chapters, served next to the episode page
        (show.docs / "episodes").mkdir(parents=True, exist_ok=True)
        (show.docs / "episodes" / f"{today}.vtt").write_text(chapters.build_vtt(timeline), encoding="utf-8")
        (show.docs / "episodes" / f"{today}.chapters.json").write_text(
            json.dumps(chapters.chapters_json(marks), indent=1), encoding="utf-8")
    episodes.append(record(ep, today, published_at) | extra | {
        "guid": f"{publish.repo()}#{tag}",
        "audio_url": audio_url,
        "audio_bytes": mp3.stat().st_size,
        "duration_seconds": tts.mp3_duration(mp3.read_bytes()),
        "chapters": marks,
    })
    corrections.mark_aired(episodes, to_read, today.isoformat())
    save(show.episodes, episodes)
    # Archived only once published: the next episodes treat archived scripts as already aired.
    (show.scripts / f"{today}.md").write_text(md, encoding="utf-8")
    save_structured(ep, show.scripts, today)
    save(show.previews, previews)  # a published episode replaces its preview
    (show.preview_scripts / f"{today}.md").unlink(missing_ok=True)  # only once the episode is out
    (show.preview_scripts / f"{today}.json").unlink(missing_ok=True)

    feed.write_feed(cfg, episodes, show.docs / "feed.xml", base_url)
    catalog.write_catalog(cfg, episodes, previews, show.data, show.docs / "catalog.json", base_url)
    site.write_site(cfg, show.docs / "catalog.json", show.data, show.docs, base_url)
    page_url = site.episode_url(base_url, today.isoformat())
    (show.build / "published.json").write_text(json.dumps({  # read by the notification step
        "date": today.isoformat(), "title": ep["title"], "page_url": page_url,
        "message": " · ".join(ep["structured"]["headlines"]) + (
            f"\n⚠ {len(doubts)} fact-check doubt(s) left: check the run summary" if (doubts := (
                ep.get("factcheck") or {}).get("doubts")) else "")}, ensure_ascii=False), encoding="utf-8")
    if output := os.getenv("GITHUB_OUTPUT"):  # the workflow deploys the site only after a publication
        with open(output, "a", encoding="utf-8") as f:
            f.write("published=true\n")
    print(f"Episode published: {audio_url}")


if __name__ == "__main__":
    main()
