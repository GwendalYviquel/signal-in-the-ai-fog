"""The catalog page (docs/episodes.html, the first show's) and the home page in a real headless browser, with catalog.json mocked.

Needs Playwright and Chromium (requirements-dev.txt, then `python -m playwright install chromium`).
Skipped when the browser is missing, unless REQUIRE_BROWSER=1 (set in the CI tests workflow).
"""
import functools
import http.server
import json
import os
import threading

import pytest

from conftest import ROOT

sync_api = pytest.importorskip("playwright.sync_api")

PODCAST = {"title": "Signal in the AI Fog", "description": "Daily briefing.", "cover": "cover.jpg",
           "feed_url": "https://site.example/feed.xml", "spotify_url": "",
           "themes": ["Models and vendors", "Sovereignty and Europe", "Platform", "Quality", "Regulation",
                      "Retail and agents"]}


def episode(date, status, **kw):
    ep = {"date": date, "status": status, "title": f"Episode {date}", "summary": f"Summary {date}.",
          "headlines": ["first headline", "second headline", "third headline"], "themes": ["Platform"],
          "duration_seconds": 400 if status == "published" else 0,
          "audio_url": f"https://x/{date}.mp3" if status == "published" else "", "spotify_url": "",
          "sources": [{"title": "Source", "url": "https://example.com"}], "transcript": "Good morning."}
    ep.update(kw)
    return ep


@pytest.fixture(scope="module")
def server():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(ROOT / "docs"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    try:
        with sync_api.sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()
    except Exception as e:  # browser binaries not installed
        if os.getenv("REQUIRE_BROWSER") == "1":
            raise
        pytest.skip(f"Chromium not available: {e}")


@pytest.fixture
def open_site(browser, server):
    """open_site(catalog dict or None for a failed fetch, width=1200) -> page."""
    pages = []

    def go(catalog, width=1200, hash_=""):
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        if catalog is None:
            page.route("**/catalog.json", lambda r: r.fulfill(status=404, body="not found"))
        else:
            page.route("**/catalog.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                               body=json.dumps(catalog)))
        page.goto(server + "episodes.html" + hash_)
        page.wait_for_selector("#list > *")
        page.js_errors = errors
        pages.append(page)
        return page

    yield go
    for page in pages:
        assert page.js_errors == [], page.js_errors
        page.close()


def test_empty_catalog(open_site):
    page = open_site({"podcast": PODCAST, "episodes": []})
    assert "No episodes yet" in page.inner_text("#list")
    assert page.inner_text("#stats") == ""


def test_failed_catalog_fetch_still_renders(open_site):
    page = open_site(None)
    assert "No episodes yet" in page.inner_text("#list")
    assert page.inner_text("#title") == "Signal in the AI Fog"


def test_preview_card(open_site):
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "preview")]})
    card = page.locator("article.card")
    assert card.locator(".badge").inner_text().lower() == "preview"
    assert card.locator(".placeholder").inner_text() == "Audio coming soon · script preview"
    assert card.locator("audio").count() == 0
    assert card.locator("img.thumb").get_attribute("src") == "cover.jpg"
    assert card.locator("details summary").first.inner_text() == "Script"


def test_spotify_is_always_a_button_never_a_visible_url(open_site):
    # The user wants a button, not a URL in clear: until the show URL is set it opens a Spotify search.
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "preview")]})
    for link in page.locator("a", has_text="Listen on Spotify").all():
        assert link.get_attribute("href") == "https://open.spotify.com/search/Signal%20in%20the%20AI%20Fog"
    assert page.locator("a", has_text="Listen on Spotify").count() == 2  # header and card
    assert "open.spotify.com" not in page.inner_text("body")


def test_spotify_show_and_episode_urls(open_site):
    podcast = dict(PODCAST, spotify_url="https://open.spotify.com/show/abc")
    eps = [episode("2026-10-20", "published", spotify_url="https://open.spotify.com/episode/xyz"),
           episode("2026-10-19", "published")]
    page = open_site({"podcast": podcast, "episodes": eps})
    hrefs = [a.get_attribute("href") for a in page.locator("article a.spotify").all()]
    assert hrefs == ["https://open.spotify.com/episode/xyz", "https://open.spotify.com/show/abc"]


def test_download_counts_on_published_cards(open_site):
    eps = [episode("2026-10-20", "published", downloads=1234), episode("2026-10-19", "published", downloads=1),
           episode("2026-10-21", "preview", downloads=None)]
    page = open_site({"podcast": PODCAST, "episodes": eps})
    assert page.locator("[id='2026-10-20'] .downloads").inner_text() == "1,234 downloads"
    assert page.locator("[id='2026-10-19'] .downloads").inner_text() == "1 download"
    assert page.locator("[id='2026-10-21'] .downloads").count() == 0


def test_published_card_has_the_player(open_site):
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "published")]})
    card = page.locator("article.card")
    assert card.locator(".badge").inner_text().lower() == "published"
    assert card.locator("audio").get_attribute("src") == "https://x/2026-10-20.mp3"
    assert "6 min 40 s" in card.inner_text()


def test_stats_count_published_episodes_and_previews_separately(open_site):
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "preview")]})
    assert page.inner_text("#stats").startswith("1 preview · since")  # no "0 episodes"
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "preview"),
                                                       episode("2026-10-19", "published")]})
    assert page.inner_text("#stats").startswith("1 episode · 1 preview · 0.1 hours of listening")


def test_search_filters_highlights_and_opens_the_script(open_site):
    eps = [episode("2026-10-20", "published", transcript="Talk about sovereign routing."),
           episode("2026-10-19", "published")]
    page = open_site({"podcast": PODCAST, "episodes": eps})
    page.fill("#search", "routing")
    page.wait_for_function("document.querySelectorAll('article.card').length === 1")
    card = page.locator("article.card")
    assert card.get_attribute("id") == "2026-10-20"
    assert card.locator("mark").first.inner_text().lower() == "routing"
    assert card.locator("details[open] summary").inner_text() == "Script"
    page.fill("#search", "nothing matches this")
    page.wait_for_selector("text=No matching episode")


def test_theme_filter(open_site):
    eps = [episode("2026-10-20", "published", themes=["Regulation"]), episode("2026-10-19", "published")]
    page = open_site({"podcast": PODCAST, "episodes": eps})
    chips = [c.inner_text() for c in page.locator(".chip").all()]
    assert chips == ["Platform", "Regulation"]  # only themes used, in config order
    page.click(".chip >> text=Regulation")
    assert [a.get_attribute("id") for a in page.locator("article.card").all()] == ["2026-10-20"]
    page.click(".chip >> text=Regulation")
    assert page.locator("article.card").count() == 2


def test_episode_text_is_never_interpreted_as_html(open_site):
    payload = '<img src=x onerror="window.injected=1">'
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "published", title=payload,
                                                               summary=payload, transcript=payload)]})
    assert page.locator("article img:not(.thumb)").count() == 0
    assert payload in page.inner_text("article h2")
    assert page.evaluate("window.injected") is None


def test_mobile_layout_has_no_horizontal_scroll(open_site):
    eps = [episode(f"2026-10-{d}", "published", title="A rather long episode title " * 3) for d in (19, 20)]
    page = open_site({"podcast": PODCAST, "episodes": eps}, width=375)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_deep_link_highlights_and_shows_the_episode(open_site):
    # Regression (2026-10-20): cards are built after load, so :target never matched a shared link.
    eps = [episode(f"2026-10-{d:02d}", "published") for d in range(20, 5, -1)]
    page = open_site({"podcast": PODCAST, "episodes": eps}, hash_="#2026-10-07")
    card = page.locator("[id='2026-10-07']")
    assert "is-target" in card.get_attribute("class")
    assert card.evaluate("e => getComputedStyle(e).outlineStyle") == "solid"
    assert page.evaluate("document.getElementById('2026-10-07').getBoundingClientRect().top < innerHeight")


def test_language_switch_translates_the_interface_and_is_remembered(open_site):
    # Learning (2026-10-22): the site serves English and French shows; an EN | FR switch translates
    # the interface (not the episodes) and is remembered from one page to the next.
    page = open_site({"podcast": PODCAST, "episodes": [episode("2026-10-20", "published", downloads=1234)]})
    assert page.locator("a.btn.primary").inner_text() == "Listen on Spotify"
    page.click('.lang-switch button[data-lang="fr"]')
    assert page.locator("a.btn.primary").inner_text() == "Écouter sur Spotify"
    assert page.locator(".badge").first.inner_text().lower() == "publié"
    assert "oct" in page.locator(".meta span").nth(1).inner_text() and "mar." in page.locator(".meta span").nth(1).inner_text()
    assert page.get_attribute("#search", "placeholder") == "Chercher dans les titres, résumés, scripts…"
    assert page.locator('[data-i18n="footer"]').inner_text().startswith("Les scripts sont écrits")
    assert page.locator(".card h2").inner_text() == "Episode 2026-10-20"  # episodes stay as written
    page.reload()
    page.wait_for_selector("#list > *")
    page.wait_for_function("document.querySelector('a.btn.primary').textContent === 'Écouter sur Spotify'")
    assert page.get_attribute('.lang-switch button[data-lang="fr"]', "aria-pressed") == "true"


def test_generated_pages_follow_the_switch(browser, server):
    page = browser.new_page()
    page.goto(server + "episodes/2026-10-21.html")
    page.wait_for_function("window.I18N && document.documentElement.dataset.uiLang === 'en'")
    page.click('.lang-switch button[data-lang="fr"]')
    assert page.locator('h2[data-i18n="stories"]').inner_text() == "Sujets"
    assert "octobre" in page.locator("[data-date]").first.inner_text()
    page.close()


def test_the_home_page_lists_the_shows_and_follows_the_browser_language(browser, server):
    # docs/index.html is where a visitor picks a show. A French browser sees it in French until the
    # EN | FR switch is used; the choice is then remembered.
    page = browser.new_page(locale="fr-FR")
    page.goto(server)
    page.wait_for_function("document.documentElement.dataset.uiLang === 'fr'")
    assert page.inner_text("h1") == "Choisissez une émission"
    hrefs = page.eval_on_selector_all(".show-card h2 a", "els => els.map((a) => a.getAttribute('href'))")
    assert hrefs[0] == "episodes.html" and "hr-news-fr/index.html" in hrefs
    page.click('[data-lang="en"]')
    assert page.inner_text("h1") == "Pick a show"
    page.goto(server)
    page.wait_for_function("document.documentElement.dataset.uiLang === 'en'")
    page.click(".show-card h2 a >> nth=0")
    page.wait_for_selector("#list > *")
    page.click(".topbar .home")
    page.wait_for_selector(".show-list")
    page.close()


def test_past_agenda_items_move_under_their_own_heading(browser, server):
    page = browser.new_page()
    page.route("**/agenda.html", lambda r: r.fulfill(status=200, content_type="text/html", body=(
        ROOT / "docs" / "agenda.html").read_text(encoding="utf-8").replace(
        '<ol class="timeline agenda" id="upcoming">',
        '<ol class="timeline agenda" id="upcoming"><li data-day="2000-01-01">Old</li><li data-day="2999-01-01">Far</li>')))
    page.goto(server + "agenda.html")
    assert page.inner_text("#past") .startswith("Old") and "Far" in page.inner_text("#upcoming")
    assert page.is_visible("#past-title") and page.get_attribute("#past li", "class") == "past"
    page.close()
