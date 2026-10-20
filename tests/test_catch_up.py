"""Catch-up episodes (EPISODE_DATE) and duplicate guards."""
import datetime as dt
import json
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import pytest

from podcast import main

from test_main import mocks, repo  # noqa: F401  (temporary repository fixtures)

PARIS = ZoneInfo("Europe/Paris")
TUESDAY_NIGHT = dt.datetime(2026, 10, 20, 23, 40, tzinfo=PARIS)


@pytest.fixture
def tuesday_night(monkeypatch):
    monkeypatch.setattr(main, "current_time", lambda cfg: TUESDAY_NIGHT)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_catch_up_uses_that_day_and_its_news_cutoff(repo, mocks, tuesday_night, monkeypatch):
    scripts = repo / "data" / "scripts"
    scripts.mkdir(parents=True)
    for day in ("2026-10-15", "2026-10-16", "2026-10-20"):
        (scripts / f"{day}.md").write_text(f"script {day}")
    monkeypatch.setenv("EPISODE_DATE", "2026-10-19")
    main.main()
    assert f"{mocks['editorial_now']:%Y-%m-%d %H:%M %Z}" == "2026-10-19 04:05 CEST"
    # Only what had aired before the 19th: the 20th's script would be news from the future.
    assert mocks["previous"] == ["script 2026-10-15", "script 2026-10-16"]
    assert mocks["upload"] == ["episode-2026-10-19"]
    [ep] = read(repo / "data/episodes.json")
    assert ep["date"] == "2026-10-19" and ep["published_at"].startswith("2026-10-19T04:05")
    assert ep["catch_up"]["generated_at"].startswith("2026-10-20T23:40")


def test_catch_up_is_announced_and_takes_its_place_in_the_feed(repo, mocks, tuesday_night, monkeypatch):
    main.main()  # the 20th
    monkeypatch.setenv("EPISODE_DATE", "2026-10-19")
    main.main()
    items = ET.fromstring((repo / "docs/feed.xml").read_text()).findall("channel/item")
    assert [i.find("pubDate").text[:16] for i in items] == ["Tue, 20 Oct 2026", "Mon, 19 Oct 2026"]
    guids = [i.find("guid").text for i in items]
    assert len(guids) == len(set(guids))
    assert "Catch-up episode, prepared on October 20, 2026 with only the news published before 04:05 on " \
           "October 19 (Paris time)." in items[1].find("description").text
    assert "Catch-up" not in items[0].find("description").text


@pytest.mark.parametrize("value,message", [("2026-10-20", "not in the past"), ("2026-10-21", "not in the past"),
                                           ("2026-10-18", "weekend"), ("19/10/2026", "YYYY-MM-DD")])
def test_invalid_catch_up_dates_stop_before_any_cost(repo, mocks, tuesday_night, monkeypatch, value, message):
    monkeypatch.setenv("EPISODE_DATE", value)
    with pytest.raises(SystemExit, match=message):
        main.main()
    assert mocks["generate"] == 0 and mocks.get("voice_checks", 0) == 0
    assert not (repo / "data/costs.json").exists()


def test_an_existing_episode_is_never_published_twice(repo, mocks, tuesday_night, monkeypatch):
    monkeypatch.setenv("EPISODE_DATE", "2026-10-19")
    main.main()
    main.main()
    assert mocks["generate"] == 1 and mocks["upload"] == ["episode-2026-10-19"]
    assert len(read(repo / "data/episodes.json")) == 1


def test_an_orphan_release_stops_the_run_before_any_cost(repo, mocks, tuesday_night, monkeypatch):
    # A release exists but not its episode (a run that failed after uploading): never a second one.
    mocks["existing_releases"] = {"episode-2026-10-19"}
    monkeypatch.setenv("EPISODE_DATE", "2026-10-19")
    with pytest.raises(SystemExit, match="already exists: run with force"):
        main.main()
    assert mocks["generate"] == 0 and mocks.get("voice_checks", 0) == 0 and mocks["upload"] == []
    monkeypatch.setenv("FORCE", "true")
    main.main()
    assert mocks["delete"] == ["episode-2026-10-19"] and mocks["upload"] == ["episode-2026-10-19"]


def test_overlap_with_neighbouring_episodes_is_reported(capsys):
    ep = {"sources": [{"title": "a", "url": "https://x/1"}, {"title": "b", "url": "https://x/2"}]}
    episodes = [{"date": "2026-10-20", "sources": [{"url": "https://x/2"}]},
                {"date": "2026-10-01", "sources": [{"url": "https://x/1"}]},
                {"date": "2026-10-16", "sources": [{"url": "https://x/9"}]},
                {"date": "2026-10-15", "sources": []}]
    found = main.report_overlaps(ep, dt.date(2026, 10, 19), episodes)
    assert found == ["1 source(s) shared with the episode of 2026-10-20: https://x/2"]  # 10-01 is not nearby
    assert "Overlap check: 1 source(s) shared" in capsys.readouterr().out


def test_workflow_offers_the_catch_up_date():
    import yaml
    from conftest import ROOT
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-episode.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert on["workflow_dispatch"]["inputs"]["episode_date"]["default"] == ""
    assert wf["jobs"]["episode"]["env"]["EPISODE_DATE"] == "${{ inputs.episode_date }}"
