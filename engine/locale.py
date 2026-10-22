"""The fixed texts of a show's language (engine/locales/<language>.yaml) and its cadence.

A show sets podcast.language (en, fr) in its show.yaml, and generation.cadence: "weekdays" (an
episode each weekday, the default) or "weekly:<day>" (one episode a week, e.g. weekly:monday).
Texts that name the period ("the story of the day", "of the week") follow the cadence.
Dates are formatted from the locale's names, never from the system's locale.
"""
from __future__ import annotations

import datetime as dt
import functools
from pathlib import Path

import yaml

LOCALES = Path(__file__).resolve().parent / "locales"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@functools.cache
def load(language: str) -> dict:
    path = LOCALES / f"{language}.yaml"
    if not path.exists():
        raise SystemExit(f"No locale {language!r}: expected {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def of(cfg: dict) -> dict:
    """The locale of a show's config (English when podcast.language is missing)."""
    return load(str(cfg.get("podcast", {}).get("language", "en"))[:2].lower())


def cadence(cfg: dict) -> tuple[str, int | None]:
    """("day", None) for an episode each weekday, ("week", weekday index) for a weekly show."""
    value = str(cfg.get("generation", {}).get("cadence", "weekdays")).lower()
    if value == "weekdays":
        return "day", None
    kind, _, day = value.partition(":")
    if kind != "weekly" or day not in WEEKDAYS[:5]:
        raise SystemExit(f"generation.cadence must be 'weekdays' or 'weekly:<monday..friday>', got {value!r}")
    return "week", WEEKDAYS.index(day)


def is_episode_day(cfg: dict, day: dt.date) -> bool:
    """Whether the show publishes on that day: every weekday, or its day of the week."""
    _, weekday = cadence(cfg)
    return day.weekday() < 5 if weekday is None else day.weekday() == weekday


def period_text(value, cfg: dict) -> str:
    """A text with a day and a week variant, for the show's cadence."""
    return value[cadence(cfg)[0]] if isinstance(value, dict) else value


def spoken_day(d: dt.date, loc: dict) -> str:
    names = loc["dates"]
    return names["spoken_day"].format(weekday=names["weekdays"][d.weekday()], month=names["months"][d.month - 1],
                                      day=d.day)


def short_date(d: dt.date, loc: dict) -> str:
    names = loc["dates"]
    return names["short_date"].format(month=names["months"][d.month - 1], day=d.day)


def long_date(d: dt.date, loc: dict) -> str:
    names = loc["dates"]
    return names["long_date"].format(month=names["months"][d.month - 1], day=d.day, year=d.year)
