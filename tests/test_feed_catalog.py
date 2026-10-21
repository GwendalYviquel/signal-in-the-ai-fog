"""RSS feed and catalog data."""
import xml.etree.ElementTree as ET

from podcast import catalog, feed

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def published(date="2026-10-20", **kw):
    ep = {"date": date, "guid": f"repo#episode-{date}", "title": "Risks & rewards <today>",
          "summary": "A summary.", "headlines": ["a b"], "themes": ["Platform"],
          "sources": [{"title": "Example", "url": "https://example.com/?a=1&b=2"}],
          "published_at": f"{date}T07:15:00+02:00", "audio_url": f"https://x/{date}.mp3",
          "audio_bytes": 1234, "duration_seconds": 402.6}
    ep.update(kw)
    return ep


def test_feed_is_valid_xml_with_escaped_text(cfg):
    xml = feed.build_feed(cfg, [published(), published("2026-10-19")], "https://site.example/podcast")
    root = ET.fromstring(xml)  # raises if special characters were not escaped
    channel = root.find("channel")
    items = channel.findall("item")
    assert [i.find("title").text for i in items] == ["Risks & rewards <today>"] * 2
    assert items[0].find("pubDate").text.startswith("Tue, 20 Oct 2026")  # newest first
    enclosure = items[0].find("enclosure")
    assert enclosure.get("url") == "https://x/2026-10-20.mp3" and enclosure.get("type") == "audio/mpeg"
    assert items[0].find(f"{ITUNES}duration").text == "402"
    assert channel.find(f"{ITUNES}image").get("href") == "https://site.example/podcast/cover.jpg"


def test_episode_description_lists_sources_and_ai_disclosure(cfg):
    xml = feed.build_feed(cfg, [published()], "https://site.example/")
    desc = ET.fromstring(xml).find("channel/item/description").text
    assert "Sources:" in desc and "https://example.com/?a=1&b=2" in desc
    assert desc.endswith(feed.DISCLAIMER)


def write_script(dir_, date, body):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{date}.md").write_text(f"# t\n\n## Script\n\n{body}\n\n## Sources\n\n- x\n", encoding="utf-8")


def test_catalog_merges_previews_and_published(cfg, tmp_path):
    write_script(tmp_path / "scripts", "2026-10-19", "Published script.")
    write_script(tmp_path / "previews", "2026-10-20", "Preview script.")
    previews = [{"date": "2026-10-20", "title": "P", "summary": "s"}]
    data = catalog.build_catalog(cfg, [published("2026-10-19")], previews, tmp_path, "feed.xml")
    eps = data["episodes"]
    assert [(e["date"], e["status"]) for e in eps] == [("2026-10-20", "preview"), ("2026-10-19", "published")]
    assert eps[0]["transcript"] == "Preview script." and eps[0]["audio_url"] == ""
    assert eps[1]["transcript"] == "Published script." and eps[1]["duration_seconds"] == 403


def test_published_episode_replaces_its_preview(cfg, tmp_path):
    previews = [{"date": "2026-10-20", "title": "P", "summary": "s"}]
    data = catalog.build_catalog(cfg, [published("2026-10-20")], previews, tmp_path, "feed.xml")
    assert [(e["date"], e["status"]) for e in data["episodes"]] == [("2026-10-20", "published")]


def test_catalog_podcast_metadata(cfg, tmp_path):
    data = catalog.build_catalog(cfg, [], [], tmp_path, "https://site.example/feed.xml")
    assert data["episodes"] == []
    assert data["podcast"]["feed_url"] == "https://site.example/feed.xml"
    assert data["podcast"]["themes"] == [t["name"] for t in cfg["themes"]]


PODCAST = "{https://podcastindex.org/namespace/1.0}"
CHAPTERS = [{"start": 0, "title": "Opening"}, {"start": 20.4, "title": "Story of the day: X"},
            {"start": 75, "title": "Platform: Y"}]


def test_episode_with_chapters_has_transcript_chapters_and_timestamps(cfg):
    xml = feed.build_feed(cfg, [published(chapters=CHAPTERS)], "https://site.example/podcast")
    item = ET.fromstring(xml).find("channel/item")
    assert item.find(f"{PODCAST}transcript").attrib == {
        "url": "https://site.example/podcast/episodes/2026-10-20.vtt", "type": "text/vtt", "language": "en"}
    assert item.find(f"{PODCAST}chapters").get("url") == "https://site.example/podcast/episodes/2026-10-20.chapters.json"
    description = item.find("description").text
    assert "Chapters:\n00:00 Opening\n00:20 Story of the day: X\n01:15 Platform: Y\n" in description  # Spotify format
    assert "Transcript, topics and sources: https://site.example/podcast/episodes/2026-10-20.html" in description
    assert item.find("link").text == "https://site.example/podcast/episodes/2026-10-20.html"


def test_episode_without_chapters_has_no_podcast_tags(cfg):
    item = ET.fromstring(feed.build_feed(cfg, [published()], "https://site.example/")).find("channel/item")
    assert item.find(f"{PODCAST}transcript") is None and item.find(f"{PODCAST}chapters") is None
    assert "Chapters:" not in item.find("description").text  # Spotify needs at least three timestamps


def test_catalog_items_link_their_page_and_topics(cfg, tmp_path):
    data = catalog.build_catalog(cfg, [published(topics=["Mistral"], chapters=CHAPTERS)], [], tmp_path, "f")
    [ep] = data["episodes"]
    assert ep["page"] == "episodes/2026-10-20.html" and ep["topics"] == ["Mistral"] and ep["chapters"] == CHAPTERS


def test_fewer_than_three_chapters_are_not_listed_in_the_description(cfg):
    # Spotify only builds chapters from three timestamps or more, the first at 00:00.
    item = ET.fromstring(feed.build_feed(cfg, [published(chapters=CHAPTERS[:2])], "https://s/")).find("channel/item")
    assert "Chapters:" not in item.find("description").text
    assert item.find(f"{PODCAST}chapters") is not None  # podcast apps still get them
