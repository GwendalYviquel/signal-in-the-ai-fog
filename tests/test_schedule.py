"""Scheduling: attempts every 15 minutes on weekday mornings; the first one at publish_at Paris time
or later publishes, all year, holidays included; the others stop before any cost.

Learning (2026-10-21/22): with a single run at 4:05, GitHub dropped the morning's scheduled run or
started it five hours late. Attempts, and an attempt started late, make one dropped run harmless.
"""
import datetime as dt
import functools
from zoneinfo import ZoneInfo

import yaml

from conftest import ROOT
from engine import main

WORKFLOW = ROOT / ".github" / "workflows" / "daily-episode.yml"
UTC = dt.timezone.utc
PARIS = ZoneInfo("Europe/Paris")


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@functools.cache
def crons():
    wf = workflow()
    return tuple(s["cron"] for s in wf.get("on", wf.get(True))["schedule"])


def expand(field, low, high):
    values = set()
    for part in field.split(","):
        if part == "*":
            values |= set(range(low, high + 1))
        elif "-" in part:
            a, b = (int(v) for v in part.split("-"))
            values |= set(range(a, b + 1))
        else:
            values.add(int(part))
    return sorted(values)


def attempts(day):
    """Every scheduled attempt on that UTC date, as UTC datetimes (weekdays only, as the crons say)."""
    found = []
    for cron in crons():
        minute, hour, _, _, weekdays = cron.split()
        if weekdays != "1-5" or day.weekday() >= 5:
            continue
        found += [dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)
                  for h in expand(hour, 0, 23) for m in expand(minute, 0, 59)]
    return sorted(found)


def test_every_weekday_of_two_years_has_an_attempt_minutes_after_publish_at(cfg):
    # Both daylight saving changes each year, and every public holiday.
    pub = cfg["generation"]["publish_at"]
    day = dt.date(2026, 1, 1)
    while day <= dt.date(2027, 12, 31):
        due = [a for a in attempts(day) if main.scheduled_run_is_due(cfg, crons()[0], a)]
        if day.weekday() >= 5:
            assert due == [], day
        else:
            first = due[0].astimezone(PARIS)
            assert pub <= f"{first:%H:%M}" < "04:20", (day, first)  # within 15 minutes of publish_at
            assert len(due) >= 8, (day, len(due))  # at least two hours of further attempts
        day += dt.timedelta(days=1)


def test_attempts_before_publish_at_do_nothing(cfg):
    winter_early = dt.datetime(2027, 1, 13, 2, 52, tzinfo=UTC)  # 3:52 Paris
    assert not main.scheduled_run_is_due(cfg, crons()[0], winter_early)
    assert main.scheduled_run_is_due(cfg, crons()[0], dt.datetime(2027, 1, 13, 3, 7, tzinfo=UTC))  # 4:07


def test_an_attempt_started_hours_late_still_publishes(cfg):
    # On 2026-10-21 GitHub started the 3:05 UTC run at 8:27 UTC.
    assert main.scheduled_run_is_due(cfg, crons()[0], dt.datetime(2026, 10, 21, 8, 27, tzinfo=UTC))


def test_publication_leaves_time_before_a_7am_listen(cfg):
    # About 5 minutes to publish, then Spotify needs time to read the feed: start by 5:00.
    hour, minute = (int(v) for v in cfg["generation"]["publish_at"].split(":"))
    assert dt.time(hour, minute) <= dt.time(5, 0)


def test_attempts_avoid_the_top_of_the_hour():
    # GitHub drops the most scheduled runs at the top of the hour.
    for day in (dt.date(2026, 7, 15), dt.date(2027, 1, 13)):
        assert all(a.minute not in (0, 5) for a in attempts(day))


def test_manual_runs_are_always_due(cfg):
    assert main.scheduled_run_is_due(cfg, "", dt.datetime(2026, 7, 15, 1, tzinfo=UTC))


def test_workflow_passes_the_cron_can_be_paused_and_deploys_only_a_publication():
    wf = workflow()
    job = wf["jobs"]["episode"]
    assert job["env"]["SCHEDULE"] == "${{ github.event.schedule || (inputs.scheduled && 'external') || '' }}"
    assert wf["jobs"]["shows"]["if"] == "github.event_name != 'schedule' || vars.SCHEDULE_ENABLED == 'true'"
    assert job["needs"] == "shows" and job["env"]["SHOW"] == "${{ matrix.show }}"
    pages = [s for s in job["steps"] if s.get("name") in ("Configure GitHub Pages", "Upload the RSS feed",
                                                            "Deploy the RSS feed")]
    assert len(pages) == 3 and all(s["if"] == "steps.generate.outputs.published == 'true'" for s in pages)
    assert wf["permissions"]["actions"] == "read"  # counts today's failed attempts


def test_an_early_attempt_does_nothing_then_one_publishes_then_the_next_stops(repo, mocks, monkeypatch, cfg):  # noqa: F811
    times = iter([dt.datetime(2027, 1, 13, 3, 52, tzinfo=PARIS), dt.datetime(2027, 1, 13, 4, 7, tzinfo=PARIS),
                  dt.datetime(2027, 1, 13, 4, 22, tzinfo=PARIS)])
    monkeypatch.setattr(main, "current_time", lambda cfg: next(times))
    monkeypatch.setenv("SCHEDULE", crons()[0])
    output = repo / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    main.main()
    assert mocks["generate"] == 0 and mocks.get("voice_checks", 0) == 0 and not output.exists()
    main.main()
    assert mocks["generate"] == 1 and output.read_text() == "published=true\n"
    main.main()
    assert mocks["generate"] == 1 and mocks["upload"] == ["episode-2027-01-13"]


def test_attempts_stop_after_two_failures_each_paid_claude(repo, mocks, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SCHEDULE", crons()[0])
    monkeypatch.setattr(main, "failed_attempts_today", lambda show, today: 2)
    main.main()
    assert mocks["generate"] == 0 and mocks.get("voice_checks", 0) == 0
    monkeypatch.delenv("SCHEDULE")  # a manual run is never capped
    main.main()
    assert mocks["generate"] == 1


def test_failed_attempts_are_counted_per_show_from_its_cost_ledger(tmp_path):
    # Learning (2026-10-22): one scheduled run now serves every show, so GitHub's run status cannot
    # say which show failed; each show's ledger records its own failed, paid attempts.
    import json
    from engine import show as shows
    home = tmp_path / "shows" / "a"
    (home / "data").mkdir(parents=True)
    (home / "show.yaml").write_text("podcast: {title: A}\ngeneration: {timezone: Europe/Paris}\n")
    runs = [{"time": "2026-10-22T02:30:00+00:00", "mode": "publish", "outcome": "failed"},   # 4:30 Paris
            {"time": "2026-10-22T03:00:00+00:00", "mode": "publish", "outcome": "failed"},
            {"time": "2026-10-22T03:30:00+00:00", "mode": "preview", "outcome": "failed"},   # not a publication
            {"time": "2026-10-22T03:40:00+00:00", "mode": "publish", "outcome": "ok"},
            {"time": "2026-10-21T21:59:00+00:00", "mode": "publish", "outcome": "failed"}]  # 23:59 the day before
    (home / "data" / "costs.json").write_text(json.dumps(runs))
    assert main.failed_attempts_today(shows.load("a", tmp_path), dt.date(2026, 10, 22)) == 2


from test_main import mocks, repo  # noqa: E402,F401  (temporary repository fixtures)
