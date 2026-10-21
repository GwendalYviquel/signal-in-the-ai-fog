"""Chapters and timed transcript from the chunk timings of the speech synthesis."""
import json
import re

from conftest import TUESDAY, make_episode
from podcast import chapters, generate


def timeline_for(ep, cfg, chars_per_second=15):
    """One chunk per spoken part, as tts.synthesize records them."""
    out, position = [], 0.0
    for _, text in generate.assemble_parts(ep, cfg, TUESDAY):
        out.append({"text": text, "start": position, "end": position + len(text) / chars_per_second})
        position += len(text) / chars_per_second
    return out


def test_every_part_of_the_episode_is_a_chapter_in_reading_order(cfg):
    ep = make_episode(follow_up={"text": "A follow-up text.", "source": {"title": "S", "url": "https://s"}})
    found = chapters.build_chapters(ep, timeline_for(ep, cfg))
    titles = [c["title"] for c in found]
    assert titles == ["Opening", f"Story of the day: {ep['headlines'][0]}",
                      "Models and vendors: Topic 0", "Platform: Topic 1", "Regulation: Topic 2",
                      "Retail and agents: Topic 3", "Follow-up", "Number of the day", "What to watch",
                      "Question for your team"]
    starts = [c["start"] for c in found]
    assert starts[0] == 0 and starts == sorted(starts) and len(set(starts)) == len(starts)


def test_no_follow_up_chapter_without_a_follow_up(cfg):
    ep = make_episode()
    assert "Follow-up" not in [c["title"] for c in chapters.build_chapters(ep, timeline_for(ep, cfg))]


def test_chapter_inside_a_chunk_is_placed_by_its_characters():
    # The host's closing parts share one chunk: What to watch starts part-way through it.
    text = "The number of the day.\n\nTen.\n\nWhat to watch.\n\nThings."
    timeline = [{"text": "Good morning, intro.", "start": 0, "end": 10},
                {"text": text, "start": 10, "end": 10 + len(text)}]  # one second per character
    ep = make_episode(segments=[])
    found = {c["title"]: c["start"] for c in chapters.build_chapters(ep, timeline)}
    assert found["Number of the day"] == 10
    assert found["What to watch"] == 10 + text.index("What to watch.")


def test_a_part_missing_from_the_audio_is_left_out():
    ep = make_episode()
    timeline = [{"text": "Good morning. First, the story of the day. Facts.", "start": 0, "end": 5}]
    assert [c["title"] for c in chapters.build_chapters(ep, timeline)] == [
        "Opening", f"Story of the day: {ep['headlines'][0]}"]


def test_chapters_json_follows_podcasting_2_0():
    data = chapters.chapters_json([{"start": 0, "title": "Opening"}, {"start": 20.5, "title": "Story"}])
    assert data == {"version": "1.2.0", "chapters": [{"startTime": 0, "title": "Opening"},
                                                     {"startTime": 20.5, "title": "Story"}]}
    json.dumps(data)


def test_timestamps_as_spotify_reads_them():
    assert [chapters.timestamp(s) for s in (0, 9.9, 75, 3725)] == ["00:00", "00:09", "01:15", "1:02:05"]


def test_transcript_is_webvtt_with_one_cue_per_sentence_in_time_order(cfg):
    ep = make_episode()
    timeline = timeline_for(ep, cfg)
    vtt = chapters.build_vtt(timeline)
    assert vtt.startswith("WEBVTT\n\n")
    cues = re.findall(r"(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})\n(.+)", vtt)
    assert cues and cues[0][2].startswith("Good morning")
    times = [(a, b) for a, b, _ in cues]
    assert all(a < b for a, b in times) and [a for a, _ in times] == sorted(a for a, _ in times)
    spoken = " ".join(" ".join(t["text"].split()) for t in timeline)
    assert " ".join(c for _, _, c in cues) == spoken  # every word, once
    assert times[-1][1] <= chapters._vtt_time(timeline[-1]["end"])
