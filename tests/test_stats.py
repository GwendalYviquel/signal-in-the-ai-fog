"""Download stats: counts from GitHub releases, daily snapshots, STATS.md and the catalog."""
import datetime as dt
import json
from types import SimpleNamespace

import yaml

from conftest import ROOT
from podcast import catalog, stats

RELEASES = [
    {"tag_name": "episode-2026-10-20", "assets": [{"name": "episode-2026-10-20.mp3", "download_count": 12}]},
    {"tag_name": "episode-2026-10-19", "assets": [{"name": "episode-2026-10-19.mp3", "download_count": 7},
                                                  {"name": "notes.txt", "download_count": 99}]},
    {"tag_name": "rehearsal-123", "assets": [{"name": "rehearsal-123.mp3", "download_count": 1}]},
]


def test_only_episode_mp3s_are_counted():
    assert stats.download_counts(RELEASES) == {"2026-10-20": 12, "2026-10-19": 7}


def test_releases_are_read_one_object_per_line(monkeypatch):
    out = "\n".join(json.dumps(r) for r in RELEASES) + "\n"
    calls = []
    monkeypatch.setattr(stats.subprocess, "run",
                        lambda args, **kw: calls.append(args) or SimpleNamespace(stdout=out))
    assert stats.fetch_releases("owner/podcast") == RELEASES
    assert "--paginate" in calls[0] and "--jq" in calls[0]


def test_one_snapshot_per_day(tmp_path):
    path = tmp_path / "stats.json"
    stats.record({"2026-10-20": 3}, dt.date(2026, 10, 21), path)
    stats.record({"2026-10-20": 5}, dt.date(2026, 10, 21), path)  # same day: replaced
    stats.record({"2026-10-20": 9, "2026-10-21": 2}, dt.date(2026, 10, 22), path)
    data = json.loads(path.read_text())
    assert data["snapshots"] == {"2026-10-21": {"2026-10-20": 5}, "2026-10-22": {"2026-10-20": 9, "2026-10-21": 2}}
    assert stats.latest(data) == {"2026-10-20": 9, "2026-10-21": 2}


def test_report_totals_and_last_seven_days():
    data = {"snapshots": {"2026-10-14": {"2026-10-13": 10}, "2026-10-21": {"2026-10-13": 25, "2026-10-20": 4}}}
    episodes = [{"date": "2026-10-20", "title": "Mistral Large 4 awaits its licence"}]
    text = stats.build_report(data, episodes, dt.date(2026, 10, 21))
    assert "**29 downloads** in total, for 2 episodes" in text
    assert "| 2026-10-20 | Mistral Large 4 awaits its licence | 4 | +4 |" in text
    assert "| 2026-10-13 |  | 25 | +15 |" in text
    assert "| 2026-10 | 2 | 29 |" in text
    assert "Spotify plays are in Spotify for Creators" in text


def test_catalog_shows_downloads_of_published_episodes_only(cfg, tmp_path):
    (tmp_path / "stats.json").write_text(json.dumps({"snapshots": {"2026-10-21": {"2026-10-20": 12}}}))
    published = [{"date": "2026-10-20", "title": "t", "summary": "s"}]
    previews = [{"date": "2026-10-21", "title": "p", "summary": "s"}]
    items = catalog.build_catalog(cfg, published, previews, tmp_path, "feed")["episodes"]
    assert [(e["date"], e["downloads"]) for e in items] == [("2026-10-21", None), ("2026-10-20", 12)]


def test_catalog_without_stats_yet(cfg, tmp_path):
    items = catalog.build_catalog(cfg, [{"date": "2026-10-20", "title": "t", "summary": "s"}], [], tmp_path, "f")
    assert items["episodes"][0]["downloads"] is None


def test_stats_workflow_runs_daily_and_redeploys_the_site():
    wf = yaml.safe_load((ROOT / ".github/workflows/stats.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert on["schedule"][0]["cron"].split()[2:] == ["*", "*", "*"]
    steps = wf["jobs"]["stats"]["steps"]
    assert any(s.get("uses", "").startswith("actions/deploy-pages") for s in steps)
    commit = next(s for s in steps if s.get("name") == "Commit the stats")
    assert "git pull --rebase origin main" in commit["run"] and "docs/catalog.json" in commit["run"]
    assert wf["concurrency"]["group"] == "daily-episode"
