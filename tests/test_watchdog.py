"""Morning watchdog: catches a missing episode after 4:05 and starts the catch-up, at most so often.

Learning (2026-10-21): GitHub never started the first scheduled run, and nothing said so before 7:00.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
import yaml

from conftest import ROOT
from engine import watchdog

PARIS = ZoneInfo("Europe/Paris")
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/watchdog.yml").read_text(encoding="utf-8"))
CRONS = [c["cron"] for c in WORKFLOW.get("on", WORKFLOW.get(True))["schedule"]]


def utc(day, cron):
    minute, hour = (int(v) for v in cron.split()[:2])
    return dt.datetime.combine(day, dt.time(hour, minute), dt.timezone.utc)


@pytest.fixture
def gh(monkeypatch):
    """Fake gh: today's daily runs, and the catch-ups started; notifications recorded."""
    state = {"runs": [], "started": 0, "sent": []}
    monkeypatch.setattr(watchdog, "daily_runs_today", lambda today: state["runs"])
    def start(slug=None):
        state["started"] += 1
        state["slug"] = slug
    monkeypatch.setattr(watchdog, "start_catch_up", start)
    monkeypatch.setattr(watchdog.notify, "send", lambda title, message, **kw: state["sent"].append((title, kw)))
    return state


WEDNESDAY = dt.date(2026, 10, 21)  # summer time
FIVE_SUMMER = "11 3 * * 1-5"


def test_every_weekday_of_2026_and_2027_is_checked_at_both_watchdog_times(cfg):
    # Both daylight saving changes included: exactly the two watchdog times each day.
    day = dt.date(2026, 1, 1)
    while day < dt.date(2028, 1, 1):
        if day.weekday() < 5:
            due = sorted(watchdog.cron_local_time(c, utc(day, c), "Europe/Paris") for c in CRONS
                         if watchdog.cron_local_time(c, utc(day, c), "Europe/Paris") in cfg["generation"]["watchdog_at"])
            assert due == ["05:11", "06:41"], day
        day += dt.timedelta(days=1)


def test_the_other_side_of_daylight_saving_does_nothing(cfg, gh):
    assert watchdog.check(cfg, "11 4 * * 1-5", utc(WEDNESDAY, "11 4 * * 1-5"), []) == "not due"
    assert gh["started"] == 0 and gh["sent"] == []


def test_episode_out_means_nothing_to_do(cfg, gh):
    eps = [{"date": "2026-10-21"}]
    assert watchdog.check(cfg, FIVE_SUMMER, utc(WEDNESDAY, FIVE_SUMMER), eps) == "published"
    assert gh["started"] == 0 and gh["sent"] == []


def test_missing_episode_with_no_run_starts_the_catch_up_and_says_why(cfg, gh):
    assert watchdog.check(cfg, FIVE_SUMMER, utc(WEDNESDAY, FIVE_SUMMER), [{"date": "2026-10-20"}]) == "started"
    assert gh["started"] == 1
    [(title, kw)] = gh["sent"]
    assert title == "Episode missing: catch-up started"


def test_a_run_still_going_is_waited_for(cfg, gh):
    gh["runs"] = [{"status": "in_progress", "conclusion": "", "event": "schedule", "url": "https://run"}]
    assert watchdog.check(cfg, FIVE_SUMMER, utc(WEDNESDAY, FIVE_SUMMER), []) == "running"
    assert gh["started"] == 0 and gh["sent"][0][0] == "Episode running late"


def test_one_failed_run_is_retried(cfg, gh):
    gh["runs"] = [{"status": "completed", "conclusion": "failure", "event": "schedule", "url": "https://run"}]
    assert watchdog.check(cfg, FIVE_SUMMER, utc(WEDNESDAY, FIVE_SUMMER), []) == "started"


def test_retries_stop_after_two_failures_each_costs_claude(cfg, gh):
    gh["runs"] = [{"status": "completed", "conclusion": "failure", "event": e, "url": f"https://run/{e}"}
                  for e in ("workflow_dispatch", "schedule")]
    assert watchdog.check(cfg, "41 4 * * 1-5", utc(WEDNESDAY, "41 4 * * 1-5"), []) == "gave up"
    assert gh["started"] == 0
    [(title, kw)] = gh["sent"]
    assert title == "Episode missing, no more retries" and kw["priority"] == 5


def test_weekend_needs_no_episode(cfg, gh):
    saturday = dt.date(2026, 10, 24)
    assert watchdog.check(cfg, FIVE_SUMMER, utc(saturday, FIVE_SUMMER), []) == "weekend"


def test_winter_time_uses_the_other_crons(cfg, gh):
    winter = dt.date(2026, 11, 4)
    assert watchdog.check(cfg, FIVE_SUMMER, utc(winter, FIVE_SUMMER), []) == "not due"  # 4:11 in Paris
    assert watchdog.check(cfg, "11 4 * * 1-5", utc(winter, "11 4 * * 1-5"), []) == "started"


def test_catch_up_is_a_real_run_with_the_scheduled_news_cutoff(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog, "_gh", lambda *a: calls.append(a) or type("P", (), {"returncode": 0})())
    watchdog.start_catch_up()
    assert calls == [("workflow", "run", "daily-episode.yml", "-f", "dry_run=false", "-f", "as_scheduled=true")]


def test_gh_failure_is_loud(monkeypatch):
    monkeypatch.setattr(watchdog, "_gh", lambda *a: type("P", (), {"returncode": 1, "stderr": "denied"})())
    with pytest.raises(RuntimeError, match="denied"):
        watchdog.start_catch_up()
    with pytest.raises(RuntimeError, match="denied"):
        watchdog.daily_runs_today(WEDNESDAY)


def test_workflow_can_start_runs_and_gets_only_the_notification_secret():
    assert WORKFLOW["permissions"] == {"contents": "read", "actions": "write"}
    step = next(s for s in WORKFLOW["jobs"]["watchdog"]["steps"] if s.get("name") == "Check today's episode")
    assert set(step["env"]) == {"GH_TOKEN", "NTFY_TOPIC", "SCHEDULE", "TEST_NOTIFICATION"} and step["run"] == "python -m engine.watchdog"
    assert "SCHEDULE_ENABLED" in WORKFLOW["jobs"]["watchdog"]["if"]  # paused with the daily schedule


def test_test_notification_only_sends_and_fails_without_the_secret(monkeypatch):
    sent = []
    monkeypatch.setenv("TEST_NOTIFICATION", "true")
    monkeypatch.setattr(watchdog, "check", lambda *a: pytest.fail("no check in test mode"))
    monkeypatch.setattr(watchdog.notify, "send", lambda title, message, **kw: sent.append(title) or True)
    watchdog.main()
    assert sent == ["Test from GitHub"]
    monkeypatch.setattr(watchdog.notify, "send", lambda *a, **kw: False)
    with pytest.raises(SystemExit, match="NTFY_TOPIC"):
        watchdog.main()


def test_with_several_shows_each_is_checked_and_started_by_name(cfg, gh):
    # Learning (2026-10-22): the watchdog serves every show; the catch-up names the show, notifications
    # say which one, and the failed attempts come from that show's own cost ledger.
    weekly = dict(cfg, podcast=dict(cfg["podcast"], title="Le Fil RH"),
                  generation=dict(cfg["generation"], cadence="weekly:monday"))
    assert watchdog.check(weekly, FIVE_SUMMER, utc(WEDNESDAY, FIVE_SUMMER), [], slug="hr") == "not an episode day"
    monday = dt.date(2026, 10, 19)
    assert watchdog.check(weekly, FIVE_SUMMER, utc(monday, FIVE_SUMMER), [], slug="hr", failed_today=0) == "started"
    assert gh["slug"] == "hr" and gh["sent"][-1][0] == "[Le Fil RH] Episode missing: catch-up started"
    assert watchdog.check(weekly, FIVE_SUMMER, utc(monday, FIVE_SUMMER), [], slug="hr", failed_today=2) == "gave up"


def test_the_catch_up_names_the_show(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog, "_gh", lambda *a: calls.append(a) or type("P", (), {"returncode": 0})())
    watchdog.start_catch_up("hr")
    assert calls[0][-2:] == ("-f", "show=hr")
