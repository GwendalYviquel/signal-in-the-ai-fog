"""The prompt and the validation must agree: a model that follows the prompt exactly must pass.

Learning (2026-10-20): drift between the prompt and the checks (headline length, numbers)
caused correction rounds that cost about three times a normal run.
"""
import re

from conftest import ROOT, TUESDAY, make_episode
from podcast import generate

PROMPT = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")


def prompt_number(pattern):
    m = re.search(pattern, PROMPT)
    assert m, f"prompt no longer matches {pattern!r}"
    return int(m.group(1))


def test_headline_limit_matches_the_check():
    assert prompt_number(r"noun phrases of at most (\d+) words") == generate.HEADLINE_MAX_WORDS


def test_prompt_targets_are_inside_the_checked_ranges():
    targets = {
        "story facts": prompt_number(r"Story of the day\*\*:.*?Facts about (\d+) words"),
        "story read": prompt_number(r"Story of the day\*\*:.*?read about (\d+) words"),
        "segment facts": prompt_number(r"Segments\*\*:.*?Facts about (\d+) words"),
        "segment read": prompt_number(r"Segments\*\*:.*?read about (\d+) words"),
        "number_of_the_day": prompt_number(r"Number of the day\*\*:.*?about (\d+) words"),
        "what_to_watch": prompt_number(r"What to watch\*\*:.*?about (\d+) words"),
        "question": prompt_number(r"Question for your team\*\*:.*?about (\d+) words"),
    }
    for part, target in targets.items():
        lo, hi = generate.LENGTHS[part]
        assert lo <= target <= hi, f"{part}: prompt asks {target} words, check allows {lo} to {hi}"


def test_segment_count_in_prompt_is_allowed():
    assert "three or four of the themes" in PROMPT
    assert generate.SEGMENTS_MIN <= 3 and 4 <= generate.SEGMENTS_MAX


def episode_at_prompt_targets(n_segments):
    def words(n):
        return " ".join(["word"] * n)
    ep = make_episode()
    ep["story_of_the_day"].update(facts=words(130), read=words(110))
    ep["segments"] = [dict(s, facts=words(45), read=words(35)) for s in ep["segments"][:n_segments]]
    ep["number_of_the_day"]["text"] = words(30)
    ep.update(what_to_watch=words(60), question=words(25))
    return ep


def test_an_episode_written_exactly_to_the_prompt_passes(cfg):
    # With three or four segments, as the prompt allows, the total length must be accepted.
    for n in (3, 4):
        errors, warnings = generate.validate(episode_at_prompt_targets(n), cfg)
        assert errors == [] and warnings == [], (n, errors, warnings)


def test_prompt_states_the_rules_the_code_enforces():
    for rule in ('Never use "we", "our" or "us"', "No comma anywhere", "no brackets",
                 "call the submit_episode tool", "never name that organisation".lower()):
        assert rule.lower() in PROMPT.lower(), rule


def test_fixed_texts_are_never_asked_from_the_model():
    assert "added automatically. Never write them yourself" in PROMPT
    opening = generate.assemble(make_episode(), {"podcast": {"title": "T"}}, TUESDAY).split("\n\n")[0]
    assert "written and read by AI" in opening  # AI Act disclosure comes from the code
