"""Episode and topic pages, sitemap (engine/site.py): built offline into a temporary docs folder."""
import json
import re
import xml.etree.ElementTree as ET

import pytest

from conftest import make_episode
from engine import site

BASE = "https://owner.github.io/podcast/"
PODCAST = {"title": "Signal in the AI Fog", "description": "D", "cover": "cover.jpg", "feed_url": BASE + "feed.xml",
           "spotify_url": "https://open.spotify.com/show/x", "themes": []}


def item(date, status="published", **kw):
    ep = {"date": date, "status": status, "title": f"Episode {date}", "summary": f"Summary {date}.",
          "headlines": ["A", "B", "C"], "themes": ["Platform"], "topics": [], "duration_seconds": 330,
          "audio_url": f"https://x/{date}.mp3" if status == "published" else "", "sources": [],
          "transcript": "Good morning.", "page": f"episodes/{date}.html", "chapters": []}
    ep.update(kw)
    return ep


@pytest.fixture
def build(tmp_path, cfg):
    """build(items, structured={date: episode}) -> docs folder."""
    def go(items, structured=None):
        docs, data = tmp_path / "docs", tmp_path / "data"
        for d in (docs, data / "scripts", data / "previews"):
            d.mkdir(parents=True, exist_ok=True)
        for date, ep in (structured or {}).items():
            folder = "scripts" if next(i for i in items if i["date"] == date)["status"] == "published" else "previews"
            (data / folder / f"{date}.json").write_text(json.dumps(ep), encoding="utf-8")
        (docs / "catalog.json").write_text(json.dumps({"podcast": PODCAST, "episodes": items}), encoding="utf-8")
        site.write_site(cfg, docs / "catalog.json", data, docs, BASE)
        return docs
    return go


def test_structured_episode_page_shows_every_story_with_label_layers_topics_and_sources(build):
    ep = make_episode(follow_up={"text": "The vote happened.", "source": {"title": "Vote", "url": "https://v"}})
    docs = build([item("2026-10-22", topics=["Microsoft"])], {"2026-10-22": ep})
    page = (docs / "episodes/2026-10-22.html").read_text()
    assert page.count('class="story"') == 1 + len(ep["segments"])
    assert 'class="label confirmed"' in page and 'class="label reported"' in page
    assert ep["story_of_the_day"]["read"] in page and 'class="read"' in page
    assert 'href="../topics/microsoft.html"' in page and 'href="https://example.com/a"' in page
    for heading in ("Follow-up", "Number of the day", "What to watch", "Question for your team"):
        assert f"<h2>{heading}</h2>" in page
    assert '<link rel="canonical" href="https://owner.github.io/podcast/episodes/2026-10-22.html">' in page


def test_episode_without_structured_data_falls_back_to_the_script(build):
    docs = build([item("2026-10-19", transcript="Good morning.\n\nStory.",
                       sources=[{"title": "Src", "url": "https://src"}])])
    page = (docs / "episodes/2026-10-19.html").read_text()
    assert '<div class="transcript">Good morning.\n\nStory.</div>' in page and 'href="https://src"' in page


def test_everything_from_the_web_is_escaped(build):
    # Titles, topics and sources come from the web through Claude: no HTML may get through.
    evil = '<img src=x onerror=alert(1)>'
    ep = make_episode()
    ep["story_of_the_day"].update(facts=f"Facts {evil}", topics=[f"Topic {evil}"],
                                  sources=[{"title": evil, "url": 'https://x" onmouseover="alert(1)'}])
    docs = build([item("2026-10-22", title=f"Title {evil}", summary=f"</script>{evil}", topics=[f"Topic {evil}"],
                       corrections=[{"added": "2026-10-23", "text": f"Fix {evil}", "aired_in": None}])],
                 {"2026-10-22": ep})
    for page in [docs / "episodes/2026-10-22.html", docs / "corrections.html", *(docs / "topics").glob("*.html")]:
        html = page.read_text()
        assert "<img src=x" not in html and 'onmouseover="' not in html, page.name
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', (docs / "episodes/2026-10-22.html").read_text(), re.S)
    assert json.loads(ld.group(1))["description"].startswith("</script>")  # stays inside the JSON


def test_chapters_are_listed_and_seek_the_player(build):
    docs = build([item("2026-10-22", chapters=[{"start": 0, "title": "Opening"}, {"start": 75.4, "title": "Story"}])])
    page = (docs / "episodes/2026-10-22.html").read_text()
    assert '<button type="button" data-t="75.4">01:15</button><span>Story</span>' in page
    assert "a.currentTime = Number(b.dataset.t)" in page


def test_feedback_opens_the_issue_forms_with_the_episode_filled_in(build):
    docs = build([item("2026-10-22", title="Voxtral 3")])
    page = (docs / "episodes/2026-10-22.html").read_text()
    links = re.findall(r'href="(https://github\.com/owner/podcast/issues/new\?[^"]+)"', page)
    assert any("template=episode-feedback.yml" in u and "episode=2026-10-22" in u for u in links)
    assert any("template=topic-suggestion.yml" in u for u in links)
    assert "Issues are public" in page


def test_topic_pages_gather_stories_from_every_episode_newest_first(build):
    older, newer = make_episode(), make_episode()
    older["story_of_the_day"]["topics"] = ["Mistral"]
    newer["segments"][1]["topics"] = ["Mistral", "EU AI Act"]
    docs = build([item("2026-10-22", topics=["Mistral", "EU AI Act"]), item("2026-10-21", topics=["Mistral"]),
                  item("2026-10-19", topics=["Mistral", "Ecosia"])],
                 {"2026-10-22": newer, "2026-10-21": older})
    page = (docs / "topics/mistral.html").read_text()
    dates = re.findall(r'href="\.\./episodes/(\d{4}-\d\d-\d\d)\.html"', page)
    assert dates == ["2026-10-22", "2026-10-21", "2026-10-19"]  # the last one has no structured data
    assert "3 mentions" in page and "Platform" in page
    index = (docs / "topics/index.html").read_text()
    assert index.index("mistral.html") < index.index("ecosia.html")  # most mentioned first


def test_slugs_match_the_catalog_page():
    assert site.slug("EU AI Act") == "eu-ai-act" and site.slug("LLM-as-a-judge") == "llm-as-a-judge"
    assert site.slug("  Café & AI!  ") == "caf-ai" and site.slug("!!!") == "topic"
    index = (site.ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert '.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "topic"' in index


def test_pages_of_removed_episodes_go_but_other_files_stay(build):
    docs = build([item("2026-10-22"), item("2026-10-21")])
    (docs / "episodes/2026-10-21.vtt").write_text("WEBVTT")
    (docs / "episodes/handmade.html").write_text("<p>mine</p>")
    build([item("2026-10-22")])
    assert not (docs / "episodes/2026-10-21.html").exists()
    assert (docs / "episodes/2026-10-21.vtt").exists() and (docs / "episodes/handmade.html").exists()


def test_sitemap_lists_every_page_and_robots_points_to_it(build):
    docs = build([item("2026-10-22", topics=["Mistral"]), item("2026-10-21", status="preview")])
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = {u.text for u in ET.parse(docs / "sitemap.xml").findall("s:url/s:loc", ns)}
    assert {BASE, BASE + "episodes/2026-10-22.html", BASE + "episodes/2026-10-21.html",
            BASE + "topics/mistral.html", BASE + "topics/index.html"} <= urls
    assert f"Sitemap: {BASE}sitemap.xml" in (docs / "robots.txt").read_text()


def test_preview_page_has_no_player_and_the_pager_links_neighbours(build):
    docs = build([item("2026-10-22", status="preview"), item("2026-10-21"), item("2026-10-20")])
    middle = (docs / "episodes/2026-10-21.html").read_text()
    assert 'href="2026-10-22.html"' in middle and 'href="2026-10-20.html"' in middle
    preview = (docs / "episodes/2026-10-22.html").read_text()
    assert "<audio" not in preview and "Audio coming soon" in preview


def test_repo_is_read_from_the_pages_url():
    assert site.repo_from("https://gwendalyviquel.github.io/signal-in-the-ai-fog/") == "gwendalyviquel/signal-in-the-ai-fog"
    assert site.repo_from("https://podcast.example.com/") == ""


def test_committed_pages_match_the_generator(tmp_path, cfg):
    # docs/episodes and docs/topics are generated: a change to site.py must be followed by a rebuild.
    import shutil
    from engine import show as shows
    root = site.ROOT
    docs = tmp_path / "docs"
    shutil.copytree(root / "docs", docs)
    show = shows.load("signal-in-the-ai-fog")
    site.write_site(cfg, docs / "catalog.json", show.data, docs, show.base_url(site.local_pages_url()))
    for folder in ("episodes", "topics"):
        for page in (root / "docs" / folder).glob("*.html"):
            assert page.read_text() == (docs / folder / page.name).read_text(), \
                f"{folder}/{page.name} is stale: run python -m engine.site"


def test_published_episodes_have_structured_data_that_reassembles_into_what_aired(cfg):
    # Learning (2026-10-21): the first three episodes were rebuilt from their scripts to get labels
    # and topics. The structured episode must give back, word for word, the script that was read.
    import datetime as dt
    from zoneinfo import ZoneInfo
    from engine import generate
    data = site.ROOT / "shows" / "signal-in-the-ai-fog" / "data"
    for ep in json.loads((data / "episodes.json").read_text(encoding="utf-8")):
        path = data / "scripts" / f"{ep['date']}.json"
        assert path.exists(), f"{ep['date']} has no structured episode"
        structured = json.loads(path.read_text(encoding="utf-8"))
        day = dt.datetime.combine(dt.date.fromisoformat(ep["date"]), dt.time(4, 5), ZoneInfo("Europe/Paris"))
        md = (data / "scripts" / f"{ep['date']}.md").read_text(encoding="utf-8")
        aired = md.split("## Script\n\n")[1].split("\n\n## Sources")[0]
        assert generate.assemble(structured, cfg, day) == aired, ep["date"]
        assert generate.validate(structured, cfg)[0] == [], ep["date"]
        stories = [structured["story_of_the_day"]] + structured["segments"]
        assert list(dict.fromkeys(t for s in stories for t in s["topics"])) == ep["topics"], ep["date"]
        assert {s["url"] for s in generate.collect_sources(structured)} == {s["url"] for s in ep["sources"]}


def test_labels_added_after_publication_say_so(build):
    ep = make_episode(labelled_after_publication="2026-10-21")
    docs = build([item("2026-10-19")], {"2026-10-19": ep})
    assert "Reliability labels added after publication" in (docs / "episodes/2026-10-19.html").read_text()
    docs = build([item("2026-10-20")], {"2026-10-20": make_episode()})
    assert "added after publication" not in (docs / "episodes/2026-10-20.html").read_text()
