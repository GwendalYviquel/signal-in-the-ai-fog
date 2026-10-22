"""Shows (engine/show.py): where each show's files live, and which shows a workflow runs.

Learning (2026-10-22): the repository became an engine for several shows. The first show must keep
its feed URL, releases and GUIDs, a new show gets its own folder everywhere, and a scheduled run
serves every show while a manual run serves the one named.
"""
import pytest
import yaml

from conftest import ROOT
from engine import show as shows

WORKFLOWS = ROOT / ".github" / "workflows"


def make(tmp_path, slug, **podcast):
    home = tmp_path / "shows" / slug
    (home / "data").mkdir(parents=True)
    (home / "show.yaml").write_text(yaml.safe_dump({"podcast": {"title": slug, **podcast}}))
    return shows.load(slug, tmp_path)


def test_the_first_show_keeps_its_urls_releases_and_guids():
    first = shows.load(shows.DEFAULT)
    assert first.docs == ROOT / "docs" and first.site_path == ""
    assert first.tag("2026-10-22") == "episode-2026-10-22"
    assert first.base_url("https://owner.github.io/repo/") == "https://owner.github.io/repo/"
    assert shows.context_secret(first) == "EDITORIAL_CONTEXT"


def test_a_new_show_gets_its_own_folder_releases_and_secret(tmp_path):
    hr = make(tmp_path, "hr-news-fr")
    assert hr.docs == tmp_path / "docs" / "hr-news-fr" and hr.home == tmp_path / "shows" / "hr-news-fr"
    assert hr.tag("2026-10-26") == "hr-news-fr-2026-10-26"  # never collides with another show's release
    assert hr.base_url("https://owner.github.io/repo") == "https://owner.github.io/repo/hr-news-fr/"
    assert shows.context_secret(hr) == "EDITORIAL_CONTEXT_HR_NEWS_FR"
    assert hr.build == tmp_path / "build" / "hr-news-fr" and hr.prompt == hr.home / "prompt.md"
    assert hr.private_context == tmp_path / "private" / "hr-news-fr" / "editorial_context.md"


def test_the_show_comes_from_the_environment_then_the_default(tmp_path, monkeypatch):
    make(tmp_path, shows.DEFAULT)
    make(tmp_path, "b")
    monkeypatch.delenv("SHOW", raising=False)
    assert shows.load(repo=tmp_path).slug == shows.DEFAULT
    monkeypatch.setenv("SHOW", "b")
    assert shows.load(repo=tmp_path).slug == "b"
    with pytest.raises(SystemExit, match="No show 'c'.*Shows: b, signal-in-the-ai-fog"):
        shows.load("c", tmp_path)


def test_scheduled_runs_serve_every_show_and_manual_runs_the_one_named(tmp_path):
    make(tmp_path, "a", context_secret="CONTEXT_A")
    make(tmp_path, "b")
    assert shows.matrix("all", tmp_path) == {"include": [{"show": "a", "context_secret": "CONTEXT_A"},
                                                          {"show": "b", "context_secret": "EDITORIAL_CONTEXT_B"}]}
    assert shows.matrix("b", tmp_path) == {"include": [{"show": "b", "context_secret": "EDITORIAL_CONTEXT_B"}]}


def test_the_daily_workflow_runs_every_show_when_scheduled_one_at_a_time():
    wf = yaml.safe_load((WORKFLOWS / "daily-episode.yml").read_text(encoding="utf-8"))
    which = next(s for s in wf["jobs"]["shows"]["steps"] if s.get("id") == "list")
    assert which["env"]["WHICH"] == "${{ (github.event_name == 'schedule' || inputs.scheduled) && 'all' || inputs.show }}"
    episode = wf["jobs"]["episode"]
    assert episode["strategy"]["max-parallel"] == 1 and episode["strategy"]["fail-fast"] is False
    generate = next(s for s in episode["steps"] if s.get("name") == "Generate the episode")
    assert generate["env"]["EDITORIAL_CONTEXT"] == "${{ secrets[matrix.context_secret] }}"


@pytest.mark.parametrize("name", ["preview-episode.yml", "correction.yml", "rehearsal.yml", "check-voices.yml"])
def test_manual_workflows_name_their_show(name):
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert on["workflow_dispatch"]["inputs"]["show"]["default"] == shows.DEFAULT
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    assert "SHOW: ${{ matrix.show }}" in text or "SHOW: ${{ inputs.show || 'signal-in-the-ai-fog' }}" in text
