"""Podcast RSS feed generation (Spotify and Apple Podcasts compatible)."""
import datetime as dt
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import locale
from .chapters import timestamp

DISCLAIMER = locale.load("en")["feed"]["disclaimer"]  # English; each show's in its locale


def episode_page(base_url: str, ep: dict) -> str:
    return f"{base_url}episodes/{ep['date']}.html"


def _episode_description(ep: dict, base_url: str = "", cfg: dict | None = None) -> str:
    loc = locale.of(cfg or {})
    text = loc["feed"]
    lines = [ep["summary"], ""]
    if ep.get("catch_up"):
        made = dt.datetime.fromisoformat(ep["catch_up"]["generated_at"])
        cutoff = dt.datetime.fromisoformat(ep["catch_up"]["news_cutoff"])
        lines += [text["catch_up"].format(made=locale.long_date(made, loc), time=f"{cutoff:%H:%M}",
                                          cutoff=locale.short_date(cutoff, loc)), ""]
    for c in ep.get("corrections") or []:
        lines += [text["correction"].format(added=c["added"], text=c["text"]), ""]
    if len(ep.get("chapters") or []) >= 3:  # Spotify turns these timestamps into chapters
        lines += [text["chapters"]] + [f"{timestamp(c['start'])} {c['title']}" for c in ep["chapters"]] + [""]
    if base_url:
        lines += [text["page"].format(url=episode_page(base_url, ep)), ""]
    lines += [text["sources"]]
    lines += [f"- {s['title']}: {s['url']}" for s in ep.get("sources", [])]
    lines += ["", text["disclaimer"]]
    return "\n".join(lines)


def _podcast_tags(ep: dict, base_url: str) -> str:
    """Podcasting 2.0: the timed transcript and chapters, for the episodes that have them."""
    if not ep.get("chapters"):
        return ""
    url = f"{base_url}episodes/{ep['date']}"
    return (f'      <podcast:transcript url="{escape(url)}.vtt" type="text/vtt" language="en"/>\n'
            f'      <podcast:chapters url="{escape(url)}.chapters.json" type="application/json+chapters"/>\n')


def build_feed(cfg: dict, episodes: list[dict], base_url: str) -> str:
    p = cfg["podcast"]
    base_url = base_url.rstrip("/") + "/"
    explicit = "true" if p.get("explicit") else "false"
    items = []
    for ep in sorted(episodes, key=lambda e: e["date"], reverse=True):
        pub = dt.datetime.fromisoformat(ep["published_at"])
        items.append(f"""    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(_episode_description(ep, base_url, cfg))}</description>
      <link>{escape(episode_page(base_url, ep))}</link>
      <guid isPermaLink="false">{escape(ep['guid'])}</guid>
      <pubDate>{format_datetime(pub)}</pubDate>
      <enclosure url="{escape(ep['audio_url'])}" length="{ep['audio_bytes']}" type="audio/mpeg"/>
      <itunes:duration>{int(ep['duration_seconds'])}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>{explicit}</itunes:explicit>
{_podcast_tags(ep, base_url)}    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>{escape(p['title'])}</title>
    <link>{escape(base_url)}</link>
    <atom:link href="{escape(base_url + 'feed.xml')}" rel="self" type="application/rss+xml"/>
    <language>{escape(p['language'])}</language>
    <description>{escape(p['description'])}</description>
    <itunes:author>{escape(p['author'])}</itunes:author>
    <itunes:owner>
      <itunes:name>{escape(p['owner_name'])}</itunes:name>
      <itunes:email>{escape(p['owner_email'])}</itunes:email>
    </itunes:owner>
    <itunes:image href="{escape(base_url + p['cover_file'])}"/>
    <itunes:category text="{escape(p['category'])}"/>
    <itunes:explicit>{explicit}</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""


def write_feed(cfg: dict, episodes: list[dict], out_path: Path, base_url: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_feed(cfg, episodes, base_url), encoding="utf-8")
