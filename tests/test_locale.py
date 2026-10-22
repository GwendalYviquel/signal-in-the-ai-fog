"""Languages and cadences (engine/locale.py, engine/locales/): what a show says, in its language.

Learning (2026-10-22): the engine runs shows in English and in French; every fixed text (opening
with the AI disclosure, transitions, sign-off, chapters, feed) comes from the show's locale, and
the first show must not change by a single character.
"""
import copy
import datetime as dt
import re
import string
import xml.etree.ElementTree as ET

import pytest

from conftest import TUESDAY, make_episode
from engine import chapters, context, corrections, feed, generate, locale

MONDAY = dt.datetime(2026, 10, 26, 4, 5)


def keys(tree, prefix=""):
    """{dotted key: set of {placeholders}} of a locale."""
    found = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            found |= keys(v, f"{prefix}{k}.")
        elif isinstance(v, list):
            found[f"{prefix}{k}"] = len(v)
        else:
            found[f"{prefix}{k}"] = {f for _, f, _, _ in string.Formatter().parse(str(v)) if f}
    return found


@pytest.fixture
def french(cfg):
    """A weekly French show."""
    fr = copy.deepcopy(cfg)
    fr["podcast"].update(title="Le Fil RH", tagline="l'actualité RH de la semaine", language="fr")
    fr["generation"]["cadence"] = "weekly:monday"
    return fr


def test_every_locale_has_the_same_keys_and_placeholders():
    en, fr = keys(locale.load("en")), keys(locale.load("fr"))
    assert en == fr


def test_the_first_show_speaks_exactly_as_before(cfg):
    script = generate.assemble(make_episode(), cfg, TUESDAY)
    assert script.startswith("Good morning, it's Tuesday, October 20. This is Signal in the AI Fog, your daily "
                             "briefing on enterprise AI in production, written and read by AI. Today: ")
    assert "\n\nFirst, the story of the day.\n\n" in script and "The number of the day." in script
    assert script.endswith("That's it for today. Sources are in the episode description. This was Signal in the AI "
                           "Fog. See you tomorrow.")


def test_a_weekly_french_show_speaks_french(french):
    script = generate.assemble(make_episode(), french, MONDAY)
    assert script.startswith("Bonjour, ici Le Fil RH, l'actualité RH de la semaine, écrit et lu par une intelligence "
                             "artificielle. Au programme de ce lundi 26 octobre : ")
    for text in ("D'abord, le sujet de la semaine.", "Ensuite, Platform.", "Le chiffre de la semaine.",
                 "À surveiller.", "Et une question pour votre équipe."):
        assert text in script
    assert script.endswith("C'est tout pour cette semaine. Les sources sont dans la description de l'épisode. "
                           "C'était Le Fil RH. À la semaine prochaine.")


def test_fixed_french_texts_never_use_the_first_person(french):
    rule = generate.first_person(french)
    fixed = generate.assemble(make_episode(follow_up={"text": "x.", "source": {}},
                                           corrections=[{"text": "y."}]), french, MONDAY)
    assert not rule.search(fixed)


@pytest.mark.parametrize("text,blocked", [("Nous verrons", True), ("notre équipe", True), ("nos clients", True),
                                          ("Les noues", False), ("Nouvelle loi", False)])
def test_french_first_person(french, text, blocked):
    assert bool(generate.first_person(french).search(text)) == blocked


def test_english_first_person_still_allows_the_us(cfg):
    assert not generate.first_person(cfg).search("The US market") and generate.first_person(cfg).search("our team")


def test_french_validation_rejects_nous(french):
    ep = make_episode()
    ep["question"] = "Comment nous préparer à la facture électronique, et avec quel calendrier pour votre équipe ?"
    assert any("First person 'nous'" in e for e in generate.validate(ep, french)[0])


def test_french_chapters_follow_the_spoken_words(french):
    ep = make_episode(follow_up={"text": "Suivi.", "source": {}})
    timeline, position = [], 0.0
    for _, text in generate.assemble_parts(ep, french, MONDAY):
        timeline.append({"text": text, "start": position, "end": position + len(text) / 15})
        position += len(text) / 15
    titles = [c["title"] for c in chapters.build_chapters(ep, timeline, french)]
    assert titles[0] == "Ouverture" and titles[1].startswith("Sujet de la semaine : ")
    assert titles[2] == "Models and vendors : Topic 0"
    assert titles[-4:] == ["Retour sur un dossier", "Chiffre de la semaine", "À surveiller", "Question pour votre équipe"]


def test_french_what_to_watch_is_found_in_archived_scripts(french, tmp_path):
    ep = make_episode(what_to_watch="Le vote a lieu jeudi.")
    (tmp_path / "2026-10-19.md").write_text(f"## Script\n\n{generate.assemble(ep, french, MONDAY)}\n\n## Sources\n")
    assert context.open_items(tmp_path, "2026-10-26", cfg=french) == [("2026-10-19", "Le vote a lieu jeudi.")]


def test_french_feed_labels_and_disclosure(french):
    ep = {"date": "2026-10-26", "guid": "g", "title": "T", "summary": "Résumé.", "sources": [{"title": "S", "url": "https://s"}],
          "published_at": "2026-10-26T04:05:00+01:00", "audio_url": "https://a", "audio_bytes": 1, "duration_seconds": 1,
          "chapters": [{"start": 0, "title": "Ouverture"}, {"start": 20, "title": "B"}, {"start": 40, "title": "C"}],
          "catch_up": {"generated_at": "2026-10-27T09:00:00+01:00", "news_cutoff": "2026-10-26T04:05:00+01:00"}}
    item = ET.fromstring(feed.build_feed(french, [ep], "https://x/le-fil-rh/")).find("channel/item")
    text = item.find("description").text
    for part in ("Chapitres :", "Sources :", "Transcription, thèmes et sources : https://x/le-fil-rh/episodes/2026-10-26.html",
                 "Script écrit et voix générée par une intelligence artificielle.",
                 "préparé le 27 octobre 2026 avec uniquement les actualités publiées avant 04:05 le 26 octobre"):
        assert part in text
    assert ET.fromstring(feed.build_feed(french, [ep], "https://x/")).find("channel/language").text == "fr"


def test_french_corrections_follow_french_rules(french):
    with pytest.raises(ValueError, match="L'épisode du vingt octobre indiquait"):
        corrections.add([{"date": "2026-10-19"}], "2026-10-19", "Nous avons indiqué une remise de deux semaines, "
                        "elle était d'une semaine.", MONDAY.date(), french)


@pytest.mark.parametrize("value,expected", [("weekdays", ("day", None)), ("weekly:monday", ("week", 0)),
                                            ("weekly:friday", ("week", 4))])
def test_cadence(value, expected):
    assert locale.cadence({"generation": {"cadence": value}}) == expected


@pytest.mark.parametrize("value", ["daily", "weekly:sunday", "weekly"])
def test_an_unknown_cadence_stops_with_its_value(value):
    with pytest.raises(SystemExit, match=re.escape(repr(value))):
        locale.cadence({"generation": {"cadence": value}})


def test_episode_days_follow_the_cadence(french, cfg):
    days = [dt.date(2026, 10, 26) + dt.timedelta(days=i) for i in range(7)]  # Monday to Sunday
    assert [locale.is_episode_day(cfg, d) for d in days] == [True] * 5 + [False] * 2
    assert [locale.is_episode_day(french, d) for d in days] == [True] + [False] * 6


def test_dates_never_depend_on_the_system_locale():
    d = dt.date(2026, 2, 1)
    assert locale.spoken_day(d, locale.load("fr")) == "dimanche 1 février"
    assert locale.long_date(d, locale.load("en")) == "February 1, 2026"
