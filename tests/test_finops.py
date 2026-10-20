"""FinOps dashboard: month figures, daily spend by kind of run, and the committed dashboard."""
import datetime as dt
import json

from conftest import ROOT
from podcast import costs, finops


def run(time, mode, usd=0.0, chars=0, outcome="ok", note=""):
    claude = dict(costs.empty_claude_usage("m"), api_calls=1, usd=usd) if usd else None
    return {"time": time, "mode": mode, "outcome": outcome, "claude": claude,
            "elevenlabs_characters": chars, "note": note, "run_url": ""}


RUNS = [
    run("2026-09-30T08:00:00+00:00", "publish", 2.0, 9_000),            # previous month
    run("2026-10-20T21:48:00+00:00", "publish", 1.02, 4_694),           # 23:48 in Paris
    run("2026-10-20T22:01:00+00:00", "publish", 0.83, 5_357),           # 00:01 in Paris: October 21
    run("2026-10-21T03:00:00+00:00", "preview", 0.40),
    run("2026-10-21T04:00:00+00:00", "voice check", chars=6),
    run("2026-10-21T05:00:00+00:00", "publish", 0.90, outcome="failed"),
    run("2026-10-14T08:58:00+00:00", "preview", note="Claude tokens not recorded"),
]


def test_month_figures_and_projection():
    s = finops.summary(RUNS, dt.date(2026, 10, 21))
    assert s["runs"] == 6 and s["episodes"] == 2 and s["untracked"] == 1
    assert round(s["claude_usd"], 2) == 3.15 and s["chars"] == 10_057
    assert round(s["per_episode_usd"], 3) == 0.925 and s["per_episode_chars"] == 5_025.5
    assert s["weekdays"] == 22  # October 2026
    assert round(s["projection_usd"], 2) == 20.35


def test_daily_spend_by_kind_on_paris_days():
    days = dict(finops.daily(RUNS, dt.date(2026, 10, 21), finops.usd))
    assert len(days) == finops.DAYS
    assert days[dt.date(2026, 10, 20)] == {"Episodes": 1.02, "Script only": 0.0, "Checks": 0.0}
    oct21 = days[dt.date(2026, 10, 21)]
    assert round(oct21["Episodes"], 2) == 1.73 and oct21["Script only"] == 0.40  # failed runs still cost
    chars = dict(finops.daily(RUNS, dt.date(2026, 10, 21), lambda r: r["elevenlabs_characters"]))
    assert chars[dt.date(2026, 10, 21)]["Checks"] == 6


def test_round_axis_maximum():
    assert [finops.nice_max(v) for v in (0, 0.7, 1.73, 4.2, 5_357, 11_000)] == [1.0, 1.0, 2.0, 5.0, 10_000, 20_000]


def test_no_episode_yet():
    svg = finops.render([run("2026-10-21T04:00:00+00:00", "voice check", chars=6)], dt.date(2026, 10, 21), "light")
    assert "no episode yet" in svg and "after a first episode" in svg


def test_each_record_rebuilds_both_dashboards(cfg, tmp_path):
    costs.record(cfg, "voice check", "ok", None, 6, ledger=tmp_path / "costs.json", report=tmp_path / "COSTS.md",
                 now=dt.datetime(2026, 10, 21, 4, tzinfo=dt.timezone.utc), charts=tmp_path / "assets")
    assert sorted(p.name for p in (tmp_path / "assets").iterdir()) == \
        ["finops-dashboard-dark.svg", "finops-dashboard-light.svg"]
    assert 'srcset="assets/finops-dashboard-dark.svg"' in (tmp_path / "COSTS.md").read_text()


def test_committed_dashboard_matches_the_ledger():
    # The workflows commit the dashboard with the ledger: they must never drift apart.
    runs = json.loads((ROOT / "data" / "costs.json").read_text(encoding="utf-8"))
    day = finops.paris_day(runs[-1]["time"])
    for theme in ("light", "dark"):
        committed = (ROOT / "assets" / f"finops-dashboard-{theme}.svg").read_text(encoding="utf-8")
        assert committed == finops.render(runs, day, theme), f"regenerate the {theme} dashboard"
