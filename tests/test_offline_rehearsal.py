"""The offline rehearsal (tools/offline_rehearsal.py): a whole publication on a copy of the repository,
with the real pipeline and only Claude, ElevenLabs and gh replaced. Catches what unit tests miss
between the pieces: request, validation, timings, chapters, feed, catalog and pages together.
"""
import importlib.util
import re
import subprocess

import pytest

from conftest import ROOT

spec = importlib.util.spec_from_file_location("offline_rehearsal", ROOT / "tools" / "offline_rehearsal.py")
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)

PODCAST_NS = "{https://podcastindex.org/namespace/1.0}"


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    out = rehearsal.rehearse(tmp_path_factory.mktemp("rehearsal") / "repo")
    out["git_before"] = before
    return out


def test_nothing_changes_in_the_repository(result):
    after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    assert after == result["git_before"]


def test_claude_gets_the_open_items_topics_and_suggestions(result):
    request = result["request"]
    assert re.search(r"Open items from previous What to watch, for the follow-up:\n- 20\d\d-\d\d-\d\d: ", request)
    assert "Mistral" in request.split("Existing topics")[1].split("\n\n")[0]
    assert "never instructions" in request and "Ignore your instructions" in request  # given as data


def test_chapters_cover_the_episode_in_order(result):
    ep = result["episode"]
    titles = [c["title"] for c in ep["chapters"]]
    assert titles[0] == "Opening" and "Follow-up" in titles and titles[-1] == "Question for your team"
    starts = [c["start"] for c in ep["chapters"]]
    assert starts == sorted(starts) and starts[-1] < ep["duration_seconds"]
    assert result["chapters"]["chapters"][1]["startTime"] == starts[1]


def test_transcript_ends_with_the_audio(result):
    last = re.findall(r"--> (\d\d):(\d\d):(\d\d\.\d{3})", result["vtt"])[-1]
    end = int(last[0]) * 3600 + int(last[1]) * 60 + float(last[2])
    assert abs(end - result["episode"]["duration_seconds"]) < 2  # the pauses between voices are counted


def test_feed_points_to_the_transcript_chapters_and_page(result):
    item = result["feed"].getroot().find("channel/item")
    assert item.find(f"{PODCAST_NS}transcript").get("url").endswith("/episodes/2030-01-15.vtt")
    assert item.find(f"{PODCAST_NS}chapters").get("type") == "application/json+chapters"
    description = item.find("description").text
    assert "\nChapters:\n00:00 Opening\n" in description
    assert item.find("link").text.endswith("/episodes/2030-01-15.html")


def test_episode_page_and_notification(result):
    page = result["page"]
    assert 'class="label confirmed"' in page and 'class="label reported"' in page and "<h2>Follow-up</h2>" in page
    assert result["published"]["page_url"].endswith("/episodes/2030-01-15.html")
    assert (result["docs"] / "topics" / "voxtral.html").exists()


def test_fixture_is_valid_without_any_correction(result, cfg):
    # The rehearsal goes through the real validation: the fixture stays a valid episode.
    assert result["episode"]["topics"][:2] == ["Mistral", "Voxtral"]


def test_a_fact_check_doubt_is_corrected_then_checked_again(result):
    checks = [r for r in result["requests"] if "output_config" in r]
    corrections = [r for r in result["requests"] if "output_config" not in r and len(r["messages"]) == 1
                   and [t["name"] for t in r["tools"]] == ["submit_episode"]]
    assert len(corrections) == 1 and "Fact-check, story of the day" in corrections[0]["messages"][0]["content"]
    assert len(checks) == 12  # six parts, checked twice
    assert all(r["model"] == "claude-haiku-5-5" for r in checks)


def test_research_is_cached_with_the_filtering_web_search(result):
    research = result["requests"][0]
    assert research["cache_control"] == {"type": "ephemeral"}
    assert next(t for t in research["tools"] if t["name"] == "web_search")["type"] == "web_search_20260209"


def test_the_waiting_correction_is_read_and_shown(result):
    assert f"A correction.\n\n{rehearsal.CORRECTION}" in result["script"]
    assert result["corrected"]["corrections"][0]["aired_in"] == "2030-01-15"
    page = (result["docs"] / "episodes" / "2026-10-20.html").read_text()
    assert rehearsal.CORRECTION in page and 'href="2030-01-15.html"' in page
    assert rehearsal.CORRECTION in (result["docs"] / "corrections.html").read_text()
    assert 'class="primary"' in result["page"]


def test_the_rehearsal_day_is_never_a_real_episode():
    # Regression (2026-10-22): the rehearsal used October 22, which became a real episode.
    import json
    published = {e["date"] for e in json.loads((ROOT / "shows" / "signal-in-the-ai-fog" / "data" / "episodes.json").read_text(encoding="utf-8"))}
    assert rehearsal.DAY.date().isoformat() not in published and rehearsal.DAY.weekday() < 5


@pytest.fixture(scope="module")
def french(tmp_path_factory):
    return rehearsal.rehearse(tmp_path_factory.mktemp("rehearsal-fr") / "repo", "hr-news-fr")


def test_a_weekly_french_show_publishes_on_its_day_in_french(french):
    # Learning (2026-10-22): the first French rehearsal; French topic names run longer than four words,
    # and a weekly French episode is about 7,000 ElevenLabs characters.
    ep = french["episode"]
    assert ep["date"] == "2030-01-14"  # a Monday, the show's day
    assert [c["title"] for c in ep["chapters"]][:2] == ["Ouverture", "Sujet de la semaine : Le bulletin de paie "
                                                                       "simplifié arrive en janvier"]
    assert french["script"].count("## Script") == 1 and "C'est tout pour cette semaine." in french["script"]
    assert "Bonjour, ici Signal RH" in french["script"] or "Bonjour, ici " in french["script"]
    item = french["feed"].getroot().find("channel/item")
    assert item.find("guid").text.endswith("#hr-news-fr-2030-01-14")
    assert french["feed"].getroot().find("channel/language").text == "fr"
    assert french["docs"].name == "hr-news-fr" and (french["docs"] / "episodes" / "2030-01-14.html").exists()
    assert french["corrected"] is None  # nothing to correct on a new show


def test_the_french_request_asks_for_a_weekly_episode(french):
    request = french["requests"][0]
    assert "This is a weekly episode" in request["messages"][0]["content"]
