"""Phone notifications through ntfy: optional, never blocking, the topic never printed."""
import json

import requests

from engine import notify


class Post:
    def __init__(self, status=200, error=None):
        self.calls, self.status, self.error = [], status, error

    def __call__(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        if self.error:
            raise self.error
        return type("R", (), {"status_code": self.status})()


def test_without_the_secret_nothing_is_sent(monkeypatch, capsys):
    post = Post()
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send("Title", "Message") is False and post.calls == []
    assert "NTFY_TOPIC not set" in capsys.readouterr().out


def test_message_is_sent_as_json_and_the_topic_never_printed(monkeypatch, capsys):
    post = Post()
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setenv("NTFY_TOPIC", "secret-topic-123")
    assert notify.send("Épisode « out »", "Body", priority=5, tags=["warning"], click="https://run")
    [call] = post.calls
    assert call["url"] == "https://ntfy.sh/"  # the topic travels in the body, not in a logged URL
    assert call["json"] == {"topic": "secret-topic-123", "title": "Épisode « out »", "message": "Body",
                            "priority": 5, "tags": ["warning"], "click": "https://run"}
    assert "secret-topic-123" not in capsys.readouterr().out


def test_a_failure_of_ntfy_never_breaks_the_run(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setattr(notify.requests, "post", Post(error=requests.ConnectionError("down")))
    assert notify.send("T", "M") is False
    monkeypatch.setattr(notify.requests, "post", Post(status=500))
    assert notify.send("T", "M") is False


def test_daily_run_failure_is_urgent_with_the_run_link(monkeypatch, tmp_path):
    post = Post()
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    notify.daily("failure", "https://github.com/run/1", published=tmp_path / "none.json")
    [call] = post.calls
    assert call["json"]["priority"] == 5 and call["json"]["click"] == "https://github.com/run/1"
    assert call["json"]["title"] == "Episode failed: Signal in the AI Fog"  # which show, now there are several


def test_daily_run_success_names_the_episode(monkeypatch, tmp_path):
    post = Post()
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    published = tmp_path / "published.json"
    published.write_text(json.dumps({"title": "Voxtral 3", "message": "A · B · C", "page_url": "https://p"}))
    notify.daily("success", "https://run", published=published)
    [call] = post.calls
    assert call["json"]["title"] == "Episode out: Voxtral 3" and call["json"]["click"] == "https://p"


def test_daily_run_with_nothing_published_stays_quiet(monkeypatch, tmp_path):
    # Weekend, the other daylight saving cron, an episode already out: no notification.
    post = Post()
    monkeypatch.setattr(notify.requests, "post", post)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    assert notify.daily("success", "https://run", published=tmp_path / "none.json") is False
    assert post.calls == []
