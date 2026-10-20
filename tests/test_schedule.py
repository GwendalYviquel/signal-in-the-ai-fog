"""Scheduling: one episode every weekday at publish_at Paris time, all year, holidays included."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
import yaml

from conftest import ROOT
from podcast import main

WORKFLOW = ROOT / ".github" / "workflows" / "daily-episode.yml"
UTC = dt.timezone.utc


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def crons():
    wf = workflow()
    return [s["cron"] for s in wf.get("on", wf.get(True))["schedule"]]


def fires_on(cron, day):
    """GitHub fires the cron on this UTC date: weekdays 1-5 only (Monday to Friday)."""
    return cron.split()[4] == "1-5" and day.weekday() < 5


def test_exactly_one_run_publishes_every_weekday_of_two_years(cfg):
    # Covers both daylight saving changes each year, and every public holiday.
    day = dt.date(2026, 1, 1)
    while day <= dt.date(2027, 12, 31):
        now = dt.datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
        due = [c for c in crons() if fires_on(c, day) and main.scheduled_run_is_due(cfg, c, now)]
        assert len(due) == (1 if day.weekday() < 5 else 0), (day, due)
        day += dt.timedelta(days=1)


@pytest.mark.parametrize("day,expected", [(dt.date(2026, 7, 15), "5 2 * * 1-5"),   # summer, UTC+2
                                          (dt.date(2026, 10, 26), "5 3 * * 1-5"),  # Monday after the change
                                          (dt.date(2027, 3, 29), "5 2 * * 1-5")])  # Monday after the change
def test_the_right_cron_runs_each_side_of_daylight_saving(cfg, day, expected):
    now = dt.datetime(day.year, day.month, day.day, 3, tzinfo=UTC)
    assert [c for c in crons() if main.scheduled_run_is_due(cfg, c, now)] == [expected]


def test_the_run_starts_at_publish_at_paris_time(cfg):
    for day in (dt.date(2026, 7, 15), dt.date(2027, 1, 13)):
        for cron in crons():
            m, h = (int(v) for v in cron.split()[:2])
            local = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UTC).astimezone(ZoneInfo("Europe/Paris"))
            if main.scheduled_run_is_due(cfg, cron, dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)):
                assert f"{local:%H:%M}" == cfg["generation"]["publish_at"] == "04:05"


def test_a_late_start_is_still_recognised(cfg):
    # GitHub can start a scheduled run late: the cron line decides, not the clock.
    late = dt.datetime(2026, 7, 15, 3, 50, tzinfo=UTC)  # the 2:05 UTC cron, 1 h 45 late
    assert main.scheduled_run_is_due(cfg, "5 2 * * 1-5", late)
    assert not main.scheduled_run_is_due(cfg, "5 3 * * 1-5", late)


def test_publication_leaves_time_before_a_7am_listen(cfg):
    # About 15 minutes to publish, then Spotify needs time to read the feed: start by 5:00.
    hour, minute = (int(v) for v in cfg["generation"]["publish_at"].split(":"))
    assert dt.time(hour, minute) <= dt.time(5, 0)


def test_holidays_are_not_skipped(cfg):
    for holiday in (dt.date(2026, 12, 25), dt.date(2027, 1, 1), dt.date(2026, 7, 14)):  # Fri, Fri, Tue
        now = dt.datetime(holiday.year, holiday.month, holiday.day, 3, tzinfo=UTC)
        assert any(fires_on(c, holiday) and main.scheduled_run_is_due(cfg, c, now) for c in crons())


def test_manual_runs_are_always_due(cfg):
    assert main.scheduled_run_is_due(cfg, "", dt.datetime(2026, 7, 15, 15, tzinfo=UTC))


def test_workflow_passes_the_cron_and_can_be_paused():
    wf = workflow()
    job = wf["jobs"]["episode"]
    assert job["env"]["SCHEDULE"] == "${{ github.event.schedule }}"
    assert job["if"] == "github.event_name != 'schedule' || vars.SCHEDULE_ENABLED == 'true'"


def test_the_other_cron_does_nothing(repo, mocks, monkeypatch, cfg):  # noqa: F811
    # In summer the 3:05 UTC run is the winter line: it must stop before any cost.
    monkeypatch.setattr(main, "current_time", lambda cfg: dt.datetime(2026, 7, 15, 5, 5,
                                                                      tzinfo=ZoneInfo("Europe/Paris")))
    monkeypatch.setenv("SCHEDULE", "5 3 * * 1-5")
    main.main()
    assert mocks["generate"] == 0 and mocks.get("voice_checks", 0) == 0
    monkeypatch.setenv("SCHEDULE", "5 2 * * 1-5")
    main.main()
    assert mocks["generate"] == 1


from test_main import mocks, repo  # noqa: E402,F401  (temporary repository fixtures)
