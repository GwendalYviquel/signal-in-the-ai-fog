"""Data for the episode catalog site (docs/index.html reads docs/catalog.json).

The catalog lists published episodes and previews (script only, no audio yet).
Previews never reach the RSS feed; a published episode replaces its preview.
"""
import json
import re
from pathlib import Path


def _transcript(script_md: Path) -> str:
    if not script_md.exists():
        return ""
    m = re.search(r"## Script\n\n(.*?)\n\n## Sources", script_md.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else ""


def _item(ep: dict, status: str, script_md: Path, downloads: dict) -> dict:
    return {
        "date": ep["date"],
        "status": status,
        "title": ep["title"],
        "summary": ep["summary"],
        "headlines": ep.get("headlines", []),
        "themes": ep.get("themes", []),
        "topics": ep.get("topics", []),
        "page": f"episodes/{ep['date']}.html",
        "chapters": ep.get("chapters", []),
        "duration_seconds": round(ep.get("duration_seconds", 0)),
        "downloads": downloads.get(ep["date"]) if status == "published" else None,
        "audio_url": ep.get("audio_url", ""),
        "spotify_url": ep.get("spotify_url", ""),
        "sources": ep.get("sources", []),
        "transcript": _transcript(script_md),
    }


def _downloads(stats_json: Path) -> dict:
    """Latest download counts (data/stats.json, kept by podcast/stats.py), if any."""
    if not stats_json.exists():
        return {}
    snapshots = json.loads(stats_json.read_text(encoding="utf-8")).get("snapshots", {})
    return snapshots[max(snapshots)] if snapshots else {}


def build_catalog(cfg: dict, episodes: list[dict], previews: list[dict], data_dir: Path, feed_url: str) -> dict:
    p = cfg["podcast"]
    published_dates = {e["date"] for e in episodes}
    downloads = _downloads(data_dir / "stats.json")
    items = [_item(e, "published", data_dir / "scripts" / f"{e['date']}.md", downloads) for e in episodes]
    items += [_item(e, "preview", data_dir / "previews" / f"{e['date']}.md", downloads)
              for e in previews if e["date"] not in published_dates]
    items.sort(key=lambda e: e["date"], reverse=True)
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


def write_catalog(cfg: dict, episodes: list[dict], previews: list[dict], data_dir: Path,
                  out_path: Path, base_url: str) -> None:
    feed_url = base_url.rstrip("/") + "/feed.xml"
    data = build_catalog(cfg, episodes, previews, data_dir, feed_url)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
