"""Data for the episode catalog site (docs/index.html reads docs/catalog.json)."""
import json
import re
from pathlib import Path


def _transcript(script_md: Path) -> str:
    if not script_md.exists():
        return ""
    m = re.search(r"## Script\n\n(.*?)\n\n## Sources", script_md.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else ""


def build_catalog(cfg: dict, episodes: list[dict], scripts_dir: Path, feed_url: str) -> dict:
    p = cfg["podcast"]
    items = []
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        items.append({
            "date": ep["date"],
            "title": ep["title"],
            "summary": ep["summary"],
            "headlines": ep.get("headlines", []),
            "themes": ep.get("themes", []),
            "duration_seconds": round(ep.get("duration_seconds", 0)),
            "audio_url": ep["audio_url"],
            "sources": ep.get("sources", []),
            "transcript": _transcript(scripts_dir / f"{ep['date']}.md"),
        })
    return {
        "podcast": {
            "title": p["title"],
            "description": p["description"],
            "cover": p["cover_file"],
            "feed_url": feed_url,
            "spotify_url": p.get("spotify_url", ""),
            "themes": [t["name"] for t in cfg["themes"]],
        },
        "episodes": items,
    }


def write_catalog(cfg: dict, episodes: list[dict], scripts_dir: Path, out_path: Path, base_url: str) -> None:
    feed_url = base_url.rstrip("/") + "/feed.xml"
    data = build_catalog(cfg, episodes, scripts_dir, feed_url)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
