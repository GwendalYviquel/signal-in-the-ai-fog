"""Morning watchdog: is today's episode out? If not, start the catch-up run and say so.

Learning (2026-10-21): on the first scheduled morning GitHub never started the daily run, and
nobody knew before 7:00. The watchdog runs at generation.watchdog_at (Paris time, after the
4:05 publication) as a separate workflow, so one dropped or failed run is caught in time.

Decisions, in order:
- not one of the watchdog times today (the other side of daylight saving time), or weekend: nothing;
- today's episode is in data/episodes.json: nothing;
- a daily run is queued or running: wait, and say it is late;
- MAX_FAILED_RUNS daily runs already failed today: stop retrying (each costs Claude), alert;
- otherwise: start the daily workflow as scheduled (real publication, news cutoff at publish_at).
The daily run itself refuses to publish twice, so a race with a late run cannot double an episode.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import notify

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
DAILY_WORKFLOW = "daily-episode.yml"
MAX_FAILED_RUNS = 2


def cron_local_time(cron: str, now_utc: dt.datetime, tz: str) -> str:
    """HH:MM in that timezone of today's run of a "M H * * ..." cron line (reads the cron, not the clock)."""
    minute, hour = (int(v) for v in cron.split()[:2])
    planned = now_utc.astimezone(dt.timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return f"{planned.astimezone(ZoneInfo(tz)):%H:%M}"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)


def daily_runs_today(today: dt.date) -> list[dict]:
    out = _gh("run", "list", "--workflow", DAILY_WORKFLOW, "--limit", "20",
              "--created", f">={today.isoformat()}", "--json", "status,conclusion,event,url")
    if out.returncode != 0:
        raise RuntimeError(f"gh run list failed: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def start_catch_up() -> None:
    out = _gh("workflow", "run", DAILY_WORKFLOW, "-f", "dry_run=false", "-f", "as_scheduled=true")
    if out.returncode != 0:
        raise RuntimeError(f"gh workflow run failed: {out.stderr.strip()[:200]}")


def check(cfg: dict, cron: str, now_utc: dt.datetime, episodes: list[dict]) -> str:
    """Return what was decided: "not due", "weekend", "published", "running", "gave up" or "started"."""
    gen = cfg["generation"]
    tz = gen["timezone"]
    slot = cron_local_time(cron, now_utc, tz) if cron else "manual"
    if cron and slot not in gen["watchdog_at"]:
        return "not due"
    today = now_utc.astimezone(ZoneInfo(tz)).date()
    if today.weekday() >= 5:
        return "weekend"
    if any(e["date"] == today.isoformat() for e in episodes):
        print(f"Watchdog {slot}: the episode of {today} is out.")
        return "published"
    runs = daily_runs_today(today)
    if running := [r for r in runs if r["status"] in ("queued", "in_progress", "waiting", "pending")]:
        notify.send("Episode running late", f"No episode yet at {slot} Paris time, a daily run is still going.",
                    tags=["hourglass"], click=running[0]["url"])
        return "running"
    failed = [r for r in runs if r["conclusion"] == "failure"]
    if len(failed) >= MAX_FAILED_RUNS:
        notify.send("Episode missing, no more retries",
                    f"{len(failed)} daily runs failed today: the watchdog stops retrying. Check the last run.",
                    priority=5, tags=["rotating_light"], click=failed[0]["url"])
        return "gave up"
    start_catch_up()
    why = "the scheduled run never started" if not runs else f"{len(failed)} run(s) failed"
    notify.send("Episode missing: catch-up started",
                f"No episode at {slot} Paris time ({why}). A real run is starting, with the {gen['publish_at']} "
                "news cutoff: the episode should be out in about 5 minutes.", priority=4, tags=["warning"])
    return "started"


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    episodes = json.loads(EPISODES.read_text(encoding="utf-8")) if EPISODES.exists() else []
    decision = check(cfg, os.getenv("SCHEDULE", "").strip(), dt.datetime.now(dt.timezone.utc), episodes)
    print(f"Watchdog: {decision}")


if __name__ == "__main__":
    main()
