"""Chapters and a timed transcript, from the chunk timings of the speech synthesis.

Each ElevenLabs chunk has an exact start and end in the episode; inside a chunk, times are
interpolated by characters. Close enough for chapters (seconds) and transcript cues (sentences).
Podcast apps read them from the feed: podcast:chapters (JSON) and podcast:transcript (WebVTT);
Spotify reads chapters from timestamps in the episode description.
"""
from __future__ import annotations

import re

from . import locale

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def marks(structured: dict, cfg: dict) -> list[tuple[str, str]]:
    """(chapter title, the fixed words that open it in the spoken script), in reading order.
    The fixed words come from the show's locale, as generate.assemble_parts speaks them."""
    loc = locale.of(cfg)
    ch, sp = loc["chapters"], loc["spoken"]
    story = locale.period_text(ch["story"], cfg)
    found = [(ch["opening"], sp["opening"].split("{")[0].split(",")[0].strip()),  # "Good morning", "Bonjour"
             (ch["with"].format(name=story, detail=structured["headlines"][0]) if structured.get("headlines")
              else story, locale.period_text(sp["story"], cfg))]
    for s in structured["segments"]:
        topics = s.get("topics") or []
        found.append((ch["with"].format(name=s["theme"], detail=topics[0]) if topics else s["theme"],
                      sp["segment"].format(theme=s["theme"])))
    if structured.get("follow_up"):
        found.append((ch["follow_up"], sp["follow_up"]))
    if structured.get("corrections"):
        found.append((ch["correction"], sp["correction"]))
    found += [(locale.period_text(ch["number"], cfg), locale.period_text(sp["number"], cfg)),
              (ch["watch"], sp["watch"]), (ch["question"], sp["question"])]
    return found


def _at(chunk: dict, offset: int) -> float:
    span = chunk["end"] - chunk["start"]
    return chunk["start"] + span * offset / max(len(chunk["text"]), 1)


def build_chapters(structured: dict, timeline: list[dict], cfg: dict) -> list[dict]:
    """[{"start": seconds, "title"}], in order; a mark not found in the audio is left out."""
    chapters, index = [], 0
    for title, words in marks(structured, cfg):
        for i in range(index, len(timeline)):
            pos = timeline[i]["text"].find(words)
            if pos != -1:
                start = 0.0 if not chapters else round(_at(timeline[i], pos), 1)
                chapters.append({"start": start, "title": title})
                index = i
                break
    return chapters


def chapters_json(chapters: list[dict]) -> dict:
    """Podcasting 2.0 JSON chapters (https://podcastindex.org/namespace/1.0#chapters)."""
    return {"version": "1.2.0", "chapters": [{"startTime": c["start"], "title": c["title"]} for c in chapters]}


def timestamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def _vtt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def build_vtt(timeline: list[dict]) -> str:
    """WebVTT transcript, one cue per sentence."""
    cues = []
    for chunk in timeline:
        flat = {**chunk, "text": " ".join(chunk["text"].split())}
        cursor = 0
        for sentence in filter(None, SENTENCE_END.split(flat["text"])):
            pos = flat["text"].find(sentence, cursor)
            start, end = _at(flat, pos), _at(flat, pos + len(sentence))
            cursor = pos + len(sentence)
            cues.append(f"{_vtt_time(start)} --> {_vtt_time(end)}\n{sentence}")
    return "WEBVTT\n\n" + "\n\n".join(cues) + "\n"
