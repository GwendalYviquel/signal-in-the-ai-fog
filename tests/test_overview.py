"""Reports across every show: costs (money only) and usage (listening only), never mixed."""
import datetime as dt
import json

import yaml

from engine import costs, finops, overview

TODAY = dt.date(2026, 10, 22)


def run(day, mode="publish", outcome="ok", usd=1.0, chars=5000):
    return {"time": f"{day}T02:10:00+00:00", "mode": mode, "outcome": outcome, "run_url": "", "note": "",
            "claude": {"usd": usd}, "elevenlabs_characters": chars}


def make_repo(tmp_path, ledgers=None, stats=None, episodes=None):
    shows = {"signal-in-the-ai-fog": {"title": "Signal", "site_path": "", "cadence": "weekdays"},
             "hr-news-fr": {"title": "Signal in the HR Fog", "site_path": "hr-news-fr", "cadence": "weekly:monday"}}
    for slug, p in shows.items():
        home = tmp_path / "shows" / slug
        (home / "data").mkdir(parents=True)
        (home / "show.yaml").write_text(yaml.safe_dump({
            "podcast": {"title": p["title"], "site_path": p["site_path"], "cover_file": "cover.jpg"},
            "generation": {"cadence": p["cadence"]}}))
        if slug in (ledgers or {}):
            (home / "data" / "costs.json").write_text(json.dumps(ledgers[slug]))
            (home / "COSTS.md").write_text("# Costs\n")
        if slug in (stats or {}):
            (home / "data" / "stats.json").write_text(json.dumps({"snapshots": stats[slug]}))
        (home / "data" / "episodes.json").write_text(json.dumps((episodes or {}).get(slug, [])))
    return tmp_path


def test_costs_report_has_money_per_show_the_shared_credits_and_no_usage_table(tmp_path):
    repo = make_repo(tmp_path, ledgers={
        "signal-in-the-ai-fog": [run("2026-10-20"), run("2026-10-21", mode="dry run", usd=0.5, chars=0)],
        "hr-news-fr": [run("2026-10-19", usd=2.0, chars=8000)]},
        stats={"signal-in-the-ai-fog": {"2026-10-22": {"2026-10-20": 10}}})
    text = overview.costs_report(repo, TODAY)
    assert "| [Signal](signal-in-the-ai-fog/COSTS.md) | 2 | 1 | $1.50 | 5,000 |" in text
    assert "| [Signal in the HR Fog](hr-news-fr/COSTS.md) | 1 | 1 | $2.00 | 8,000 |" in text
    assert "**All shows** | **3** | **2** | **$3.50** | **13,000**" in text
    # Projections: 22 weekdays in October 2026 for the daily show, 4 Mondays for the weekly one.
    assert "$22.00 | 110,000 |" in text and "$8.00 | 32,000 |" in text
    assert "one quota shared by every show" in text and "about 142,000 by the end of the month" in text
    # The only figure using downloads: cost per download, every run counted.
    assert "| Signal | 1 | $1.50 | 5,000 | 10 | $0.150 |" in text
    assert "Last 7 days" not in text  # listening figures live in STATS.md


def test_usage_report_has_listening_per_show_and_no_money(tmp_path):
    repo = make_repo(tmp_path, stats={"signal-in-the-ai-fog": {
        "2026-10-10": {"2026-10-09": 4}, "2026-10-20": {"2026-10-09": 6, "2026-10-19": 2},
        "2026-10-22": {"2026-10-09": 7, "2026-10-19": 5}}},
        episodes={"signal-in-the-ai-fog": [{"date": "2026-10-09"}, {"date": "2026-10-19"}]})
    rows = overview.usage(repo, TODAY)
    signal = rows[0]
    assert (signal["downloads"], signal["week"], signal["episodes"]) == (12, 8, 2)  # 12 now, 4 on Oct 10
    assert signal["per_day"][dt.date(2026, 10, 20)] == 4 and signal["per_day"][dt.date(2026, 10, 22)] == 4
    assert signal["per_day"][dt.date(2026, 10, 10)] == 0  # nothing before the first snapshot
    text = overview.usage_report(rows)
    assert "| Signal | 2 | 12 | +8 | 6.0 | 2026-10-22 |" in text and "| Signal in the HR Fog | 0 | 0 | +0 | — | none yet |" in text
    assert "$" not in text and "Spotify for Creators" in text
    svg = overview.usage_svg(rows, "light")
    assert "<title>Usage dashboard</title>" in svg and "Signal in the HR Fog" in svg and "$" not in svg


def test_reports_are_written_in_the_shows_folder(tmp_path):
    repo = make_repo(tmp_path)
    overview.write_costs(repo, TODAY)
    written = overview.write_usage(repo, TODAY)
    assert (repo / "shows" / "COSTS.md").exists()
    assert {p.name for p in written} == {"STATS.md", "usage-dashboard-light.svg", "usage-dashboard-dark.svg"}


def test_every_run_rebuilds_the_report_of_every_show(tmp_path):
    repo = make_repo(tmp_path)
    show = repo / "shows" / "hr-news-fr"
    cfg = {"costs": {"claude_usd_per_mtok": {"input": 2, "output": 10, "cache_write": 2.5, "cache_read": 0.2},
                     "web_search_usd_per_1000": 10}, "generation": {"cadence": "weekly:monday", "model": "m"}}
    costs.record(cfg, "dry run", "ok", elevenlabs_characters=0, ledger=show / "data" / "costs.json",
                 report=show / "COSTS.md", charts=show, now=dt.datetime(2026, 10, 22, 8, tzinfo=dt.timezone.utc))
    assert "Signal in the HR Fog" in (repo / "shows" / "COSTS.md").read_text()


def test_a_weekly_show_projects_over_its_episode_days():
    weekly = {"generation": {"cadence": "weekly:monday"}}
    s = finops.summary([run("2026-10-19")], TODAY, weekly)
    assert s["weekdays"] == 4 and s["projection_usd"] == 4.0  # the Mondays of October 2026
    assert "4 episodes" in finops.render([run("2026-10-19")], TODAY, "light", weekly)
