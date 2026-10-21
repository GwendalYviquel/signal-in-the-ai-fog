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
    assert item.find(f"{PODCAST_NS}transcript").get("url").endswith("/episodes/2026-10-22.vtt")
    assert item.find(f"{PODCAST_NS}chapters").get("type") == "application/json+chapters"
    description = item.find("description").text
    assert "\nChapters:\n00:00 Opening\n" in description
    assert item.find("link").text.endswith("/episodes/2026-10-22.html")


def test_episode_page_and_notification(result):
    page = result["page"]
    assert 'class="label confirmed"' in page and 'class="label reported"' in page and "<h2>Follow-up</h2>" in page
    assert result["published"]["page_url"].endswith("/episodes/2026-10-22.html")
    assert (result["docs"] / "topics" / "voxtral.html").exists()


def test_fixture_is_valid_without_any_correction(result, cfg):
    # The rehearsal goes through the real validation: the fixture stays a valid episode.
    assert result["episode"]["topics"][:2] == ["Mistral", "Voxtral"]
