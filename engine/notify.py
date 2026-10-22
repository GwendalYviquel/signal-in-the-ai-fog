"""Phone notifications through ntfy.sh: no account, the topic name is the secret (NTFY_TOPIC).

Never blocks a run: without the secret, or if ntfy is down, it only logs. The topic is never printed.

Usage in a workflow:
  python -m engine.notify daily <job status> <run url>   after the daily run (SHOW selects the show)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

NTFY = "https://ntfy.sh/"


def send(title: str, message: str, priority: int = 3, tags: list[str] | None = None, click: str = "") -> bool:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        print(f"Notification not sent (NTFY_TOPIC not set): {title}")
        return False
    body = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": tags or []}
    if click:
        body["click"] = click
    try:
        ok = requests.post(NTFY, json=body, timeout=15).status_code == 200
    except requests.RequestException:
        ok = False
    print(f"Notification {'sent' if ok else 'failed'}: {title}")
    return ok


def daily(status: str, run_url: str, published: Path | None = None) -> bool:
    """After the daily run: published, or failed. Quiet otherwise (weekend, other cron, already out)."""
    from . import show as shows
    show = shows.load()
    published = published or show.build / "published.json"
    if status != "success":
        return send(f"Episode failed: {show.cfg['podcast']['title']}", f"The daily run ended with status {status}. The next attempt, in "
                    "15 minutes, retries if no episode is out.", priority=5, tags=["rotating_light"], click=run_url)
    if not published.exists():
        return False
    ep = json.loads(published.read_text(encoding="utf-8"))
    return send(f"Episode out: {ep['title']}", ep.get("message", ""), tags=["studio_microphone"],
                click=ep.get("page_url", ""))


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "daily":
        daily(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("usage: python -m engine.notify daily <job status> <run url>")
