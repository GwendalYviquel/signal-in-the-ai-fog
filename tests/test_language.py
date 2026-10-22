"""Language guard: every step answers in the show's language. Learning (2026-10-22): the fact-check
of a French episode listed its claims in English, and a filter on the episode's words then dropped them."""
import copy

from conftest import make_episode
from engine import factcheck, generate, locale

FR = "La commission des affaires sociales a rejeté le texte, qui sera examiné en séance par les députés."
EN = "The committee rejected the bill, which will be debated by the members of parliament this week."


def test_the_language_of_a_text_is_told_only_when_it_is_clear():
    assert locale.detect(FR) == "fr" and locale.detect(EN) == "en"
    assert locale.detect("Signal in the HR Fog") is None  # too short to tell
    assert locale.detect("Le Model Context Protocol est adopté par les éditeurs pour leurs agents.") == "fr"


def french(cfg):
    fr = copy.deepcopy(cfg)
    fr["podcast"]["language"] = "fr"
    return fr


def test_a_part_in_another_language_than_the_show_is_an_error(cfg):
    ep = make_episode()
    ep["story_of_the_day"]["read"] = EN
    errors, _ = generate.validate(ep, french(cfg))
    assert any("story read is in English: write it in French" in e for e in errors)
    ep = make_episode(summary=FR + " " + FR)
    errors, _ = generate.validate(ep, cfg)
    assert any("summary is in French: write it in English" in e for e in errors)


def test_a_claim_in_another_language_than_the_text_is_kept_not_dropped():
    assert not factcheck.in_text("The committee rejected the bill on October 14", FR)
    assert factcheck.made_by("The committee rejected the bill on October 14", FR)  # translated: still checked
    assert factcheck.made_by("The committee rejected the bill, which was debated by the members", FR)
    assert not factcheck.made_by("Le PLFSS autorise les laboratoires à stocker des vaccins", FR)  # from a source page


def test_every_step_is_told_the_language_of_the_episode():
    from engine import dossier
    assert "{language}" in factcheck.INSTRUCTIONS and "{language}" in dossier.RESEARCH and "{language}" in dossier.WRITING
    assert "Write the whole episode in French" in dossier.writing_request({"items": []}, 1400, "French")
