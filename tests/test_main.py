"""The whole pipeline in each mode, on a temporary copy of the data (Claude, ElevenLabs and gh mocked)."""
import json
import shutil
import xml.etree.ElementTree as ET

import pytest
import yaml

from conftest import ROOT, SATURDAY, TUESDAY, make_episode
from podcast import generate, main, publish, tts

# 60 MPEG-1 Layer III frames (128 kbps, 44.1 kHz): about 1.6 s of valid MP3 for mutagen.
FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413
FAKE_MP3 = FRAME * 60


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A temporary repository layout with a publishable config, wired into podcast.main."""
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["podcast"].update(author="Test Author", owner_name="Test Owner")
    cfg["tts"]["voices"] = {"host": "hostVoice", "analyst": "analystVoice"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "cover.jpg", tmp_path / "docs" / "cover.jpg")
    (tmp_path / "data").mkdir()
    for name, path in {"ROOT": tmp_path, "EPISODES": tmp_path / "data/episodes.json",
                       "SCRIPTS": tmp_path / "data/scripts", "PREVIEWS": tmp_path / "data/previews.json",
                       "PREVIEW_SCRIPTS": tmp_path / "data/previews", "BUILD": tmp_path / "build",
                       "COST_LEDGER": tmp_path / "data/costs.json", "COST_REPORT": tmp_path / "COSTS.md"}.items():
        monkeypatch.setattr(main, name, path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    for var in ("DRY_RUN", "PREVIEW", "FORCE", "SCHEDULE", "AS_SCHEDULED", "EPISODE_DATE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(main, "current_time", lambda cfg: TUESDAY)
    return tmp_path


@pytest.fixture
def mocks(monkeypatch):
    """Fake generation, speech and GitHub release; records what was called."""
    calls = {"generate": 0, "tts": 0, "upload": [], "delete": []}

    def fake_generate(cfg, now, previous, usage=None):
        calls["generate"] += 1
        calls["previous"] = previous
        calls["editorial_now"] = now
        if usage is not None:  # as if two API calls were made
            usage.update(api_calls=2, input_tokens=50_000, output_tokens=4_000, web_search_requests=12)
        ep = make_episode()
        return {"title": ep["title"], "summary": ep["summary"], "script": generate.assemble(ep, cfg, now),
                "parts": generate.assemble_parts(ep, cfg, now), "sources": generate.collect_sources(ep),
                "structured": ep}

    def fake_tts(parts, cfg, out, billed=None):
        calls["tts"] += 1
        calls["voices"] = {role for role, _ in parts}
        out.write_bytes(FAKE_MP3)
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
    assert (repo / "build/2026-10-20.md").exists()
    assert not (repo / "data/episodes.json").exists() and not (repo / "docs/feed.xml").exists()


def test_preview_goes_to_the_catalog_only(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    assert mocks["tts"] == 0 and mocks["upload"] == []
    assert not (repo / "docs/feed.xml").exists(), "a preview must never reach the RSS feed"
    assert not (repo / "data/episodes.json").exists()
    assert [p["date"] for p in read(repo / "data/previews.json")] == ["2026-10-20"]
    cat = read(repo / "docs/catalog.json")
    assert [(e["status"], e["audio_url"]) for e in cat["episodes"]] == [("preview", "")]
    assert cat["episodes"][0]["transcript"].startswith("Good morning")


def test_preview_does_not_need_the_publication_fields(repo, mocks, monkeypatch):
    cfg = yaml.safe_load((repo / "config.yaml").read_text())
    cfg["tts"]["voices"]["analyst"] = "TO_FILL"
    (repo / "config.yaml").write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    assert (repo / "data/previews.json").exists()


def test_existing_preview_is_not_regenerated_without_force(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    main.main()
    assert mocks["generate"] == 1
    monkeypatch.setenv("FORCE", "true")
    main.main()
    assert mocks["generate"] == 2
    assert len(read(repo / "data/previews.json")) == 1


def test_publish_after_preview(repo, mocks, monkeypatch):
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    monkeypatch.setenv("PREVIEW", "false")
    main.main()

    assert mocks["tts"] == 1 and mocks["upload"] == ["episode-2026-10-20"]
    assert mocks["voices"] == {"host", "analyst"}
    [ep] = read(repo / "data/episodes.json")
    assert ep["guid"] == "owner/podcast#episode-2026-10-20"
    assert ep["audio_url"].endswith("episode-2026-10-20.mp3")
    assert ep["audio_bytes"] == len(FAKE_MP3) and 1 < ep["duration_seconds"] < 3
    assert ep["headlines"] and ep["themes"][0] == "Sovereignty and Europe"
    assert read(repo / "data/previews.json") == []
    assert not (repo / "data/previews/2026-10-20.md").exists()
    assert (repo / "data/scripts/2026-10-20.md").exists()

    items = ET.fromstring((repo / "docs/feed.xml").read_text()).findall("channel/item")
    assert len(items) == 1
    cat = read(repo / "docs/catalog.json")
    assert [(e["status"], e["date"]) for e in cat["episodes"]] == [("published", "2026-10-20")]


def test_failed_speech_keeps_the_preview(repo, mocks, monkeypatch):
    # The preview script used to be deleted before speech synthesis: a failure lost it.
    monkeypatch.setenv("PREVIEW", "true")
    main.main()
    monkeypatch.setenv("PREVIEW", "false")

    def failing_tts(text, cfg, out, billed=None):
        raise RuntimeError("ElevenLabs 500")
    monkeypatch.setattr(tts, "synthesize", failing_tts)
    with pytest.raises(RuntimeError):
        main.main()
    assert (repo / "data/previews/2026-10-20.md").exists()
    assert len(read(repo / "data/previews.json")) == 1
    # Nor is the script archived as aired: tomorrow's episode would think it was broadcast.
    assert not (repo / "data/scripts/2026-10-20.md").exists()
    assert mocks["upload"] == [] and not (repo / "docs/feed.xml").exists()


def test_publish_requires_the_publication_fields(repo, mocks):
    cfg = yaml.safe_load((repo / "config.yaml").read_text())
    cfg["tts"]["voices"]["analyst"] = "TO_FILL"
    (repo / "config.yaml").write_text(yaml.safe_dump(cfg))
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
    assert len(read(repo / "data/episodes.json")) == 1


def test_weekend_is_skipped(repo, mocks, monkeypatch):
    monkeypatch.setattr(main, "current_time", lambda cfg: SATURDAY)
    main.main()
    assert mocks["generate"] == 0


def test_previous_published_scripts_feed_continuity(repo, mocks):
    scripts = repo / "data/scripts"
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
