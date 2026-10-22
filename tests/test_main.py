"""The whole pipeline in each mode, on a temporary copy of the data (Claude, ElevenLabs and gh mocked)."""
import json
import shutil
import xml.etree.ElementTree as ET

import pytest
import yaml

from conftest import ROOT, SATURDAY, SHOW, TUESDAY, make_episode
from engine import context, generate, main, publish, tts

# 60 MPEG-1 Layer III frames (128 kbps, 44.1 kHz): about 1.6 s of valid MP3 for mutagen.
FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413
FAKE_MP3 = FRAME * 60


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A temporary repository with the first show and a publishable config; the engine works in it."""
    from engine import show as shows
    cfg = yaml.safe_load((ROOT / SHOW / "show.yaml").read_text(encoding="utf-8"))
    cfg["podcast"].update(author="Test Author", owner_name="Test Owner")
    cfg["tts"]["voices"] = {"host": "hostVoice", "analyst": "analystVoice"}
    home = tmp_path / SHOW
    (home / "data").mkdir(parents=True)
    (home / "show.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    shutil.copy(ROOT / SHOW / "prompt.md", home / "prompt.md")
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "cover.jpg", tmp_path / "docs" / "cover.jpg")
    monkeypatch.setattr(shows, "REPO", tmp_path)
    monkeypatch.delenv("SHOW", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(main, "failed_attempts_today", lambda show, today: 0)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    for var in ("DRY_RUN", "PREVIEW", "FORCE", "SCHEDULE", "AS_SCHEDULED", "EPISODE_DATE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main, "current_time", lambda cfg: TUESDAY)
    return tmp_path


def test_the_test_repository_redirects_every_path_of_the_pipeline(repo):
    # Regression (2026-10-21): main.DOCS was added without being redirected here, and a test run
    # wrote its fake episode into the real docs/feed.xml. Since the engine (2026-10-22), every path
    # comes from the show, and no module keeps a path of its own into the repository.
    import importlib
    import pkgutil
    from pathlib import Path
    import engine
    from engine import show as shows
    assert shows.load().repo == repo
    for info in pkgutil.iter_modules(engine.__path__):
        module = importlib.import_module(f"engine.{info.name}")
        real = [name for name, value in vars(module).items() if isinstance(value, Path) and name not in ("ROOT", "REPO", "LOCALES", "TEMPLATE")
                and ROOT in (value, *value.parents)]
        assert real == [], f"engine.{info.name} keeps paths into the real repository: {real}"


@pytest.fixture
def mocks(monkeypatch):
    """Fake generation, speech and GitHub release; records what was called."""
    calls = {"generate": 0, "tts": 0, "upload": [], "delete": []}

    def fake_generate(cfg, now, previous, usage=None, request=None, show=None, dossier_path=None):
        calls["generate"] += 1
        calls["previous"] = previous
        calls["request"] = request
        calls["editorial_now"] = now
        if usage is not None:  # as if two API calls were made
            usage.update(api_calls=2, input_tokens=50_000, output_tokens=4_000, web_search_requests=12)
        ep = make_episode()
        return {"title": ep["title"], "summary": ep["summary"], "script": generate.assemble(ep, cfg, now),
                "parts": generate.assemble_parts(ep, cfg, now), "sources": generate.collect_sources(ep),
                "structured": ep}

    def fake_tts(parts, cfg, out, billed=None, timeline=None):
        calls["tts"] += 1
        calls["voices"] = {role for role, _ in parts}
        out.write_bytes(FAKE_MP3)
        position = 0.0
        for _, text in parts:  # one chunk per part, 15 characters a second
            if timeline is not None:
                timeline.append({"text": text, "start": position, "end": position + len(text) / 15})
            position += len(text) / 15
        chars = sum(len(text) for _, text in parts)
        if billed is not None:
            billed[:] = [chars]
        return chars

    monkeypatch.setattr(generate, "generate_episode", fake_generate)
    monkeypatch.setattr(tts, "synthesize", fake_tts)
    def fake_voice_check(cfg):
        calls["voice_checks"] = calls.get("voice_checks", 0) + 1
        return {"host": "ok", "analyst": "ok"}
    monkeypatch.setattr(tts, "voice_check_results", fake_voice_check)
    # The account's credits, read before anything is paid; calls["credits"] overrides them.
    monkeypatch.setattr(tts, "read_credits", lambda: calls.get("credits", {
        "used": 0, "limit": 100_000, "left": 100_000, "reset": "2026-11-01", "can_extend": False}))
    monkeypatch.setattr(main.notify, "send", lambda title, message, **kw: calls.setdefault("alerts", []).append(title))
    monkeypatch.setattr(context, "accepted_suggestions", lambda: calls.get("suggestions", []))  # never gh
    monkeypatch.setattr(publish, "repo", lambda: "owner/podcast")
    monkeypatch.setattr(publish, "upload_audio",
                        lambda mp3, tag, title, notes: calls["upload"].append(tag) or f"https://x/{tag}/{mp3.name}")
    monkeypatch.setattr(publish, "delete_release", lambda tag: calls["delete"].append(tag))
    monkeypatch.setattr(publish, "release_exists", lambda tag: tag in calls.get("existing_releases", ()))
    return calls


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_dry_run_publishes_nothing(repo, mocks, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    main.main()
    assert mocks["generate"] == 1 and mocks["tts"] == 0 and mocks["upload"] == []
    assert (repo / "build/signal-in-the-ai-fog/2026-10-20.md").exists()
    assert not (repo / SHOW / "data/episodes.json").exists() and not (repo / "docs/feed.xml").exists()


def test_preview_goes_to_the_catalog_only(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    assert mocks["tts"] == 0 and mocks["upload"] == []
    assert not (repo / "docs/feed.xml").exists(), "a preview must never reach the RSS feed"
    assert not (repo / SHOW / "data/episodes.json").exists()
    assert [p["date"] for p in read(repo / SHOW / "data/previews.json")] == ["2026-10-20"]
    cat = read(repo / "docs/catalog.json")
    assert [(e["status"], e["audio_url"]) for e in cat["episodes"]] == [("preview", "")]
    assert cat["episodes"][0]["transcript"].startswith("Good morning")


def test_preview_does_not_need_the_publication_fields(repo, mocks, monkeypatch):
    cfg = yaml.safe_load((repo / SHOW / "show.yaml").read_text())
    cfg["tts"]["voices"]["analyst"] = "TO_FILL"
    (repo / SHOW / "show.yaml").write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    assert (repo / SHOW / "data/previews.json").exists()


def test_existing_preview_is_not_regenerated_without_force(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    main.main()
    assert mocks["generate"] == 1
    monkeypatch.setenv("FORCE", "true")
    main.main()
    assert mocks["generate"] == 2
    assert len(read(repo / SHOW / "data/previews.json")) == 1


def test_publish_after_preview(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    monkeypatch.setenv("PREVIEW", "false")
    main.main()

    assert mocks["tts"] == 1 and mocks["upload"] == ["episode-2026-10-20"]
    assert mocks["voices"] == {"host", "analyst"}
    [ep] = read(repo / SHOW / "data/episodes.json")
    assert ep["guid"] == "owner/podcast#episode-2026-10-20"
    assert ep["audio_url"].endswith("episode-2026-10-20.mp3")
    assert ep["audio_bytes"] == len(FAKE_MP3) and 1 < ep["duration_seconds"] < 3
    assert ep["headlines"] and ep["themes"][0] == "Sovereignty and Europe"
    assert read(repo / SHOW / "data/previews.json") == []
    assert not (repo / SHOW / "data/previews/2026-10-20.md").exists()
    assert (repo / SHOW / "data/scripts/2026-10-20.md").exists()

    items = ET.fromstring((repo / "docs/feed.xml").read_text()).findall("channel/item")
    assert len(items) == 1
    cat = read(repo / "docs/catalog.json")
    assert [(e["status"], e["date"]) for e in cat["episodes"]] == [("published", "2026-10-20")]


def test_failed_speech_keeps_the_preview(repo, mocks, monkeypatch):
    # The preview script used to be deleted before speech synthesis: a failure lost it.
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    monkeypatch.setenv("PREVIEW", "false")

    def failing_tts(text, cfg, out, billed=None, timeline=None):
        raise RuntimeError("ElevenLabs 500")
    monkeypatch.setattr(tts, "synthesize", failing_tts)
    with pytest.raises(RuntimeError):
        main.main()
    assert (repo / SHOW / "data/previews/2026-10-20.md").exists()
    assert len(read(repo / SHOW / "data/previews.json")) == 1
    # Nor is the script archived as aired: tomorrow's episode would think it was broadcast.
    assert not (repo / SHOW / "data/scripts/2026-10-20.md").exists()
    assert mocks["upload"] == [] and not (repo / "docs/feed.xml").exists()


def test_publish_requires_the_publication_fields(repo, mocks):
    cfg = yaml.safe_load((repo / SHOW / "show.yaml").read_text())
    cfg["tts"]["voices"]["analyst"] = "TO_FILL"
    (repo / SHOW / "show.yaml").write_text(yaml.safe_dump(cfg))
    with pytest.raises(SystemExit, match="tts.voices.analyst"):
        main.main()
    assert mocks["generate"] == 0


def test_already_published_day_is_skipped(repo, mocks):
    main.main()
    main.main()
    assert mocks["generate"] == 1 and mocks["upload"] == ["episode-2026-10-20"]


def test_force_replaces_the_release(repo, mocks, monkeypatch):
    main.main()
    monkeypatch.setenv("FORCE", "true")
    main.main()
    assert mocks["delete"] == ["episode-2026-10-20"]
    assert len(read(repo / SHOW / "data/episodes.json")) == 1


def test_weekend_is_skipped(repo, mocks, monkeypatch):
    monkeypatch.setattr(main, "current_time", lambda cfg: SATURDAY)
    main.main()
    assert mocks["generate"] == 0


def test_previous_published_scripts_feed_continuity(repo, mocks):
    scripts = repo / SHOW / "data/scripts"
    scripts.mkdir(parents=True)
    for day in ("2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"):
        (scripts / f"{day}.md").write_text(f"script {day}")
    main.main()
    assert mocks["previous"] == ["script 2026-10-15", "script 2026-10-16", "script 2026-10-19"]


def test_voices_are_checked_before_paying_for_the_script(repo, mocks, monkeypatch):
    monkeypatch.setattr(tts, "voice_check_results", lambda cfg: {"host": "ok", "analyst": "ElevenLabs 402"})
    with pytest.raises(RuntimeError, match="analyst"):
        main.main()
    assert mocks["generate"] == 0, "Claude must not be called when a voice is unusable"


def test_no_voice_check_in_dry_run_or_preview(repo, mocks, monkeypatch):
    for mode in ("DRY_RUN", "PREVIEW"):
        monkeypatch.setenv(mode, "true")
        monkeypatch.setenv("FORCE", "true")
        main.main()
        monkeypatch.delenv(mode)
    assert mocks.get("voice_checks", 0) == 0
    monkeypatch.delenv("FORCE")
    main.main()
    assert mocks["voice_checks"] == 1


def test_publication_writes_chapters_transcript_pages_and_the_notification(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    assert (repo / SHOW / "data/previews/2026-10-20.json").exists()  # a preview page shows the stories too
    assert (repo / "docs/episodes/2026-10-20.html").exists()
    monkeypatch.setenv("PREVIEW", "false")
    main.main()

    [ep] = read(repo / SHOW / "data/episodes.json")
    assert ep["topics"] == ["Microsoft", "Sovereign cloud", "Topic 0", "Topic 1", "Topic 2", "Topic 3"]
    assert [c["title"] for c in ep["chapters"]][:2] == ["Opening", "Story of the day: Microsoft's sovereign cloud goes local"]
    assert (repo / "docs/episodes/2026-10-20.vtt").read_text().startswith("WEBVTT")
    assert read(repo / "docs/episodes/2026-10-20.chapters.json")["chapters"][0] == {"startTime": 0.0, "title": "Opening"}
    assert read(repo / SHOW / "data/scripts/2026-10-20.json")["story_of_the_day"]["label"] == "confirmed"
    assert not (repo / SHOW / "data/previews/2026-10-20.json").exists()  # replaced by the published episode
    page = (repo / "docs/episodes/2026-10-20.html").read_text()
    assert ">Chapters</h2>" in page and 'class="label confirmed"' in page
    assert (repo / "docs/topics/microsoft.html").exists() and (repo / "docs/sitemap.xml").exists()
    note = read(repo / "build/signal-in-the-ai-fog/published.json")
    assert note["page_url"] == "https://owner.github.io/podcast/episodes/2026-10-20.html"


def test_request_carries_open_items_known_topics_and_suggestions(repo, mocks, monkeypatch):
    (repo / SHOW / "data/scripts").mkdir(parents=True)
    (repo / SHOW / "data/scripts/2026-10-19.md").write_text(
        "## Script\n\nWhat to watch.\n\nThe vote on Thursday.\n\nAnd a question for your team.\n\nQ?\n\n## Sources\n")
    (repo / SHOW / "data/episodes.json").write_text(json.dumps([{"date": "2026-10-19", "topics": ["EU AI Act"]}]))
    mocks["suggestions"] = ["#3 Model Context Protocol: worth a look"]
    monkeypatch.setenv("DRY_RUN", "true")
    main.main()
    assert mocks["request"] == {"open_items": [("2026-10-19", "The vote on Thursday.")], "topics": ["EU AI Act"],
                                "suggestions": ["#3 Model Context Protocol: worth a look"]}


def test_the_next_episode_reads_pending_corrections_and_marks_them_aired(repo, mocks, monkeypatch):
    from engine import corrections
    eps = [{"date": "2026-10-19", "title": "Monday", "summary": "S", "topics": [], "sources": [],
            "guid": "g", "published_at": "2026-10-19T04:05:00+02:00", "audio_url": "https://a", "audio_bytes": 1,
            "duration_seconds": 1}]
    text = "The episode of October nineteenth gave a two-week discount. Mistral set it at one week."
    corrections.add(eps, "2026-10-19", text, TUESDAY.date())
    (repo / SHOW / "data/episodes.json").write_text(json.dumps(eps))
    main.main()
    episodes = read(repo / SHOW / "data/episodes.json")
    assert episodes[0]["corrections"][0]["aired_in"] == "2026-10-20"
    assert f"A correction.\n\n{text}" in (repo / SHOW / "data/scripts/2026-10-20.md").read_text()
    assert "Correction" in [c["title"] for c in episodes[1]["chapters"]]
    assert read(repo / SHOW / "data/scripts/2026-10-20.json")["corrections"][0]["text"] == text
    page = (repo / "docs/episodes/2026-10-19.html").read_text()
    assert 'class="correction"' in page and 'href="2026-10-20.html"' in page
    assert text in (repo / "docs/corrections.html").read_text()


def test_a_catch_up_never_reads_corrections(repo, mocks, monkeypatch):
    from engine import corrections
    eps = [{"date": "2026-10-15", "title": "T", "summary": "S", "topics": [], "sources": [], "guid": "g",
            "published_at": "2026-10-15T04:05:00+02:00", "audio_url": "https://a", "audio_bytes": 1, "duration_seconds": 1}]
    corrections.add(eps, "2026-10-15", "The episode of October fifteenth said one week. It was in fact two weeks.",
                    TUESDAY.date())
    (repo / SHOW / "data/episodes.json").write_text(json.dumps(eps))
    monkeypatch.setenv("EPISODE_DATE", "2026-10-16")
    main.main()
    assert read(repo / SHOW / "data/episodes.json")[0]["corrections"][0]["aired_in"] is None


def test_a_dry_run_never_tells_the_workflow_it_published(repo, mocks, monkeypatch):
    output = repo / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("DRY_RUN", "true")
    main.main()
    assert mocks["generate"] == 1 and not output.exists()


def test_too_few_elevenlabs_credits_stop_the_run_before_paying_anything(repo, mocks):
    # The credits are one quota for every show: read before the voice check and Claude, an episode
    # they cannot voice stops the run for free, with an alert, and counts as a failed attempt.
    mocks["credits"] = {"used": 98_000, "limit": 100_000, "left": 2_000, "reset": "2026-11-01", "can_extend": False}
    with pytest.raises(SystemExit, match="ElevenLabs credits too low: 2,000 characters left of 100,000"):
        main.main()
    assert mocks["generate"] == 0 and "voice_checks" not in mocks and mocks["tts"] == 0
    assert mocks["alerts"] == ["ElevenLabs credits too low: Signal in the AI Fog"]
    run = read(repo / SHOW / "data" / "costs.json")[-1]
    assert (run["mode"], run["outcome"], run["claude"]) == ("publish", "failed", None)
    assert run["note"].startswith("ElevenLabs credits too low")
    assert run["elevenlabs_credits"] == {"left": 2_000, "limit": 100_000, "reset": "2026-11-01"}


def test_enough_or_unreadable_credits_let_the_run_go_on(repo, mocks):
    mocks["credits"] = None  # a key without the user_read permission: never blocks
    main.main()
    assert mocks["generate"] == 1 and "alerts" not in mocks
