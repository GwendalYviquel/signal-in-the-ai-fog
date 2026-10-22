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
        assert f">{heading}</h2>" in page
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
    index = (site.ROOT / "docs" / "episodes.html").read_text(encoding="utf-8")  # the first show's catalog
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


def french_cfg(cfg):
    import copy
    fr = copy.deepcopy(cfg)
    fr["podcast"].update(title="Signal RH", language="fr", site_path="hr-news-fr", description="Chaque semaine.")
    fr["generation"]["cadence"] = "weekly:monday"
    return fr


def test_a_french_show_gets_french_pages_that_reach_the_shared_files(tmp_path, cfg):
    # Learning (2026-10-22): a show in a subfolder (docs/<slug>/) still uses docs/pages.css, i18n.js
    # and the home page; its pages are written in its language, with keys for the language switch.
    fr = french_cfg(cfg)
    docs = tmp_path / "docs" / "hr-news-fr"
    (tmp_path / "data" / "scripts").mkdir(parents=True)
    docs.mkdir(parents=True)
    (tmp_path / "data" / "scripts" / "2026-10-26.json").write_text(json.dumps(make_episode(
        follow_up={"text": "Suivi.", "source": {"title": "S", "url": "https://s", "primary": True}})))
    (docs / "catalog.json").write_text(json.dumps({"podcast": dict(PODCAST, title="Signal RH"),
                                                   "episodes": [item("2026-10-26")]}))
    site.write_site(fr, docs / "catalog.json", tmp_path / "data", docs, BASE + "hr-news-fr/")
    page = (docs / "episodes" / "2026-10-26.html").read_text()
    assert '<html lang="fr">' in page and 'href="../../pages.css"' in page and 'src="../../i18n.js"' in page
    assert 'href="../../index.html"' in page and ">Signal RH</a>" in page  # the button back to the home page
    assert 'href="../index.html">Signal RH</a>' in page and 'href="../agenda.html"' in page
    for text in ('data-i18n="stories">Sujets</h2>', 'data-i18n="story.week">Sujet de la semaine</span>',
                 'data-i18n="number.week">Chiffre de la semaine</h2>', ">lundi 26 octobre 2026</span>",
                 'data-i18n="label_confirmed"', ">Confirmé</span>", 'data-i18n="read">L&#x27;analyse</span>'):
        assert text in page, text
    catalog = (docs / "index.html").read_text()
    assert '<html lang="fr">' in catalog and '<script src="../i18n.js"></script>' in catalog
    assert "<title>Signal RH</title>" in catalog and "{{" not in catalog


def test_the_interface_texts_of_every_language_reach_the_browser():
    data = site.i18n_json()
    assert set(data) == set(site.languages()) >= {"en", "fr"}
    assert set(data["en"]) == set(data["fr"])
    assert data["fr"]["story.week"] == "Sujet de la semaine" and data["en"]["story.day"] == "Story of the day"
    assert data["en"]["downloads"] == {"one": "{n} download", "other": "{n} downloads"}


def test_the_committed_translations_match_the_locales():
    committed = json.loads((site.ROOT / "docs" / "i18n.json").read_text(encoding="utf-8"))
    assert committed == site.i18n_json(), "docs/i18n.json is stale: run python -m engine.site"


def test_the_home_page_lists_every_show_the_first_one_first(tmp_path):
    import yaml
    for slug_, extra in (("signal-in-the-ai-fog", {"site_path": ""}), ("hr-news-fr", {"language": "fr"})):
        home = tmp_path / "shows" / slug_
        home.mkdir(parents=True)
        (home / "show.yaml").write_text(yaml.safe_dump({
            "podcast": {"title": slug_.upper(), "description": "<b>D</b>", "cover_file": "cover.jpg", **extra},
            "generation": {"cadence": "weekdays" if slug_.startswith("signal") else "weekly:monday"}}))
    (tmp_path / "shows" / "hr-news-fr" / "data").mkdir()
    (tmp_path / "shows" / "hr-news-fr" / "data" / "episodes.json").write_text(json.dumps(
        [{"date": "2026-10-26", "title": "Old"}, {"date": "2026-11-02", "title": "<i>New</i>"}]))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "shows.html").write_text(site.GENERATED)  # the list of shows before the home page
    site.write_shared(tmp_path)
    html = (tmp_path / "docs" / "index.html").read_text()
    assert html.index("SIGNAL-IN-THE-AI-FOG") < html.index("HR-NEWS-FR")
    # The first show's catalog is episodes.html: index.html, at the root, is this page.
    assert 'href="episodes.html"' in html and 'href="hr-news-fr/index.html"' in html
    assert 'href="hr-news-fr/episodes/2026-11-02.html">&lt;i&gt;New&lt;/i&gt;</a>' in html and "Old" not in html
    assert "data-auto-lang" in html  # follows the browser's language until one is picked
    assert not (tmp_path / "docs" / "shows.html").exists()
    assert ">Every weekday<" in html and ">Every week<" in html and ">In French<" in html
    assert "<b>" not in html  # descriptions are escaped
    assert (tmp_path / "docs" / "i18n.json").exists()


def test_every_page_has_a_button_back_to_the_home_page_and_the_root_show_keeps_its_urls(build):
    # The first show sits at the root: its catalog moved to episodes.html when index.html became
    # the home page; episodes/, topics/, feed.xml and catalog.json keep their URLs.
    docs = build([item("2026-10-22", topics=["Mistral"])])
    assert (docs / "episodes.html").exists() and not (docs / "index.html").exists()
    page = (docs / "episodes" / "2026-10-22.html").read_text()
    assert 'class="home" href="../index.html"' in page and 'href="../episodes.html">' in page
    for name in ("agenda.html", "corrections.html", "topics/index.html", "topics/mistral.html"):
        assert 'class="home" href="' in (docs / name).read_text(), name
    catalog = (docs / "episodes.html").read_text()
    assert 'class="home" href="index.html"' in catalog and 'href="agenda.html"' in catalog


def test_the_agenda_lists_dated_items_once_with_the_latest_episode(tmp_path, cfg):
    data, docs = tmp_path / "data", tmp_path / "docs"
    (data / "scripts").mkdir(parents=True)
    docs.mkdir()
    agendas = {"2026-10-21": [{"date": "2026-12-02", "text": "AI Act marking"},
                              {"date": "2026-11-12", "text": "Bid <deadline>"}],
               "2026-10-22": [{"date": "2026-12-02", "text": "AI  Act marking"},  # announced again
                              {"date": "next week", "text": "No exact day"}, {"date": "2026-02-30", "text": "Impossible"}]}
    for day, agenda in agendas.items():
        (data / "scripts" / f"{day}.json").write_text(json.dumps(make_episode(agenda=agenda)))
    (docs / "catalog.json").write_text(json.dumps({"podcast": PODCAST,
                                                   "episodes": [item("2026-10-22"), item("2026-10-21")]}))
    site.write_site(cfg, docs / "catalog.json", data, docs, BASE)
    page = (docs / "agenda.html").read_text()
    assert re.findall(r'data-day="([^"]+)"', page) == ["2026-11-12", "2026-12-02"]  # by date, once each
    assert "Bid &lt;deadline&gt;" in page and "No exact day" not in page and "Impossible" not in page
    assert 'href="episodes/2026-10-22.html"' in page  # the latest episode that announced it
    assert 'id="past"' in page and "li.dataset.day < today" in page  # past items move in the browser


def test_primary_sources_carry_a_badge_official_text_in_french():
    assert site.i18n_json()["fr"]["primary"] == "Texte officiel"
    ui = site.Ui({"podcast": {"language": "fr", "site_path": "hr-news-fr"}, "generation": {"cadence": "weekly:monday"}})
    html = site._sources(ui, [{"title": "JO", "url": "https://legifrance.gouv.fr/x", "primary": True},
                              {"title": "Press", "url": "https://p", "primary": False}])
    assert html.count('class="primary"') == 1 and ">Texte officiel</span>" in html
