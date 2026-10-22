"""Spotify check: show availability, latest episode, and the delay before an episode is live."""
import datetime as dt
import json

import pytest
import yaml

from conftest import ROOT
from podcast import spotify

UTC = dt.timezone.utc


def embed_page(next_data: dict) -> str:
    """Same structure as Spotify's public embed page (checked on 2026-10-21)."""
    return ('<html><body><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(next_data) + "</script></body></html>")


def live(title):
    return embed_page({"props": {"pageProps": {"state": {"data": {"entity": {
        "type": "episode", "title": title, "name": title}}}, "config": {}}}})


UNAVAILABLE = embed_page({"props": {"pageProps": {"status": 404, "title": "Page not available",
                                                   "description": "", "links": [], "rtl": False}}})


@pytest.fixture
def data(tmp_path):
    episodes = [{"date": "2026-10-19", "title": "Argon's Pricing Cliff", "published_at": "2026-10-19T04:05:00+02:00",
                 "catch_up": {"generated_at": "2026-10-21T00:01:49+02:00"}},
                {"date": "2026-10-20", "title": "Mistral Large 4 awaits its licence",
                 "published_at": "2026-10-20T04:20:00+02:00"}]
    path = tmp_path / "episodes.json"
    path.write_text(json.dumps(episodes))
    return path, tmp_path / "spotify.json"


def test_latest_episode_parsing():
    assert spotify.latest_episode(live("Mistral Large 4 awaits its licence")) == "Mistral Large 4 awaits its licence"
    assert spotify.latest_episode(UNAVAILABLE) is None
    assert spotify.latest_episode("<html>no data</html>") is None


def test_show_not_yet_available(cfg, data):
    episodes, log = data
    status = spotify.check(cfg, UNAVAILABLE, dt.datetime(2026, 10, 20, 3, tzinfo=UTC), episodes, log)
    assert status.startswith("The show is not available on Spotify yet") and not log.exists()


def test_previous_episode_still_showing(cfg, data):
    episodes, log = data
    status = spotify.check(cfg, live("Argon's Pricing Cliff"), dt.datetime(2026, 10, 20, 3, tzinfo=UTC), episodes, log)
    assert "is not there yet" in status and not log.exists()


def test_first_time_live_is_recorded_once_with_the_delay(cfg, data):
    episodes, log = data
    first = dt.datetime(2026, 10, 20, 4, 50, tzinfo=UTC)  # 6:50 Paris, 2 h 30 after 4:20
    status = spotify.check(cfg, live("Mistral Large 4 awaits its licence"), first, episodes, log)
    assert "150 minutes after publication" in status
    spotify.check(cfg, live("Mistral Large 4 awaits its licence"), first + dt.timedelta(hours=1), episodes, log)
    assert json.loads(log.read_text()) == {"2026-10-20": {"title": "Mistral Large 4 awaits its licence",
                                                          "first_seen_live": "2026-10-20T04:50:00+00:00",
                                                          "minutes_after_publication": 150}}


def test_show_id_comes_from_the_config(cfg):
    assert spotify.show_id(cfg["podcast"]["spotify_url"]) == "6yv1oUk4Qdlr4gFp7FYDPZ"
    with pytest.raises(SystemExit):
        spotify.show_id("https://example.com/podcast")


def test_checks_cover_the_morning_window_in_both_seasons():
    wf = yaml.safe_load((ROOT / ".github/workflows/check-spotify.yml").read_text())
    [cron] = [s["cron"] for s in wf.get("on", wf.get(True))["schedule"]]
    minute, hours, *_, days = cron.split()
    first, last = (int(h) for h in hours.split("-"))
    assert len(minute.split(",")) == 4 and "0" not in minute.split(",") and days == "1-5"  # every 15 min, off the hour
    # Publication at 2:05 UTC in summer and 3:05 UTC in winter; the listen at 5:00 or 6:00 UTC.
    assert first <= 2 and last >= 6
