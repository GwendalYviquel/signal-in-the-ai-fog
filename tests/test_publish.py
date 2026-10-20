"""GitHub release commands (gh is mocked) and rehearsal download checks."""
import datetime as dt
from types import SimpleNamespace

import pytest

from podcast import main, publish, rehearsal


@pytest.fixture
def gh_calls(monkeypatch):
    calls = []

    def run(args, **kw):
        calls.append((args, kw))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(publish.subprocess, "run", run)
    monkeypatch.setenv("GITHUB_REPOSITORY", "GwendalYviquel/signal-in-the-ai-fog")
    return calls


def test_upload_creates_a_non_latest_release_and_returns_the_public_url(gh_calls, tmp_path):
    mp3 = tmp_path / "episode-2026-10-20.mp3"
    mp3.write_bytes(b"x")
    url = publish.upload_audio(mp3, "episode-2026-10-20", "Title", "Notes")
    args, kw = gh_calls[0]
    assert args[:4] == ["gh", "release", "create", "episode-2026-10-20"] and str(mp3) in args
    assert "--latest=false" in args and kw["check"] is True  # a failed upload must stop the run
    assert url == ("https://github.com/GwendalYviquel/signal-in-the-ai-fog/releases/download/"
                   "episode-2026-10-20/episode-2026-10-20.mp3")


def test_delete_removes_the_tag_too(gh_calls):
    publish.delete_release("episode-2026-10-20")
    args, kw = gh_calls[0]
    assert args == ["gh", "release", "delete", "episode-2026-10-20", "--yes", "--cleanup-tag"]
    assert kw["check"] is False  # deleting a release that does not exist is fine


def test_release_exists(monkeypatch):
    monkeypatch.setattr(publish.subprocess, "run", lambda args, **kw: SimpleNamespace(returncode=1))
    assert publish.release_exists("nope") is False


def test_pages_url_uses_a_lowercase_owner(gh_calls):
    assert publish.pages_url() == "https://gwendalyviquel.github.io/signal-in-the-ai-fog/"


@pytest.fixture
def downloads(monkeypatch):
    answers = []

    def get(url, timeout, allow_redirects):
        status, body = answers.pop(0)
        return SimpleNamespace(status_code=status, content=body)
    monkeypatch.setattr(rehearsal.requests, "get", get)
    monkeypatch.setattr(rehearsal.time, "sleep", lambda s: None)
    return answers


def test_download_check_retries_until_the_asset_is_ready(downloads):
    downloads += [(404, b""), (200, b"abc")]
    rehearsal.check_download("https://x/a.mp3", 3)


def test_download_check_fails_on_wrong_size(downloads):
    downloads += [(200, b"ab")] * 3
    with pytest.raises(RuntimeError, match="HTTP 200, 2 bytes"):
        rehearsal.check_download("https://x/a.mp3", 3, tries=3)


def test_current_time_is_paris_time():
    # The cron runs in UTC: the episode date must be the Paris date.
    now = main.current_time({"generation": {"timezone": "Europe/Paris"}})
    assert now.utcoffset() in (dt.timedelta(hours=1), dt.timedelta(hours=2))
