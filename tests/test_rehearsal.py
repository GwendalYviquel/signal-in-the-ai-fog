"""Publication rehearsal: real release path checked, nothing left behind."""
import pytest
from mutagen.mp3 import MP3

from conftest import ROOT
from engine import publish, rehearsal

from test_main import repo  # noqa: F401  (temporary repository fixture)


def test_silent_mp3_is_valid(tmp_path):
    path = tmp_path / "silence.mp3"
    rehearsal.silent_mp3(path, seconds=3)
    assert 2.5 < MP3(path).info.length < 3.5


@pytest.fixture
def gh(monkeypatch):
    state = {"releases": set(), "uploaded": [], "fail_download": False}

    def upload(mp3, tag, title, notes):
        state["releases"].add(tag)
        state["uploaded"].append(mp3.stat().st_size)
        return f"https://github.com/owner/podcast/releases/download/{tag}/{mp3.name}"

    def download(url, size, tries=6):
        if state["fail_download"]:
            raise RuntimeError("Audio not downloadable")
        assert size == state["uploaded"][-1]

    monkeypatch.setattr(publish, "upload_audio", upload)
    monkeypatch.setattr(publish, "delete_release", lambda tag: state["releases"].discard(tag))
    monkeypatch.setattr(publish, "release_exists", lambda tag: tag in state["releases"])
    monkeypatch.setattr(publish, "repo", lambda: "owner/podcast")
    monkeypatch.setattr(rehearsal, "check_download", download)
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    return state


def snapshot(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if "build" not in p.parts)


def test_rehearsal_writes_nothing_and_cleans_up(repo, gh, capsys):  # noqa: F811
    before = snapshot(repo)
    rehearsal.rehearse()
    assert gh["releases"] == set()
    assert snapshot(repo) == before, "a rehearsal must not write data or docs"
    assert "Rehearsal OK" in capsys.readouterr().out


def test_release_is_deleted_even_when_a_check_fails(repo, gh):  # noqa: F811
    gh["fail_download"] = True
    with pytest.raises(RuntimeError, match="not downloadable"):
        rehearsal.rehearse()
    assert gh["releases"] == set()


def test_undeletable_release_is_reported(repo, gh, monkeypatch):  # noqa: F811
    monkeypatch.setattr(publish, "delete_release", lambda tag: None)
    with pytest.raises(RuntimeError, match="remove it by hand"):
        rehearsal.rehearse()


def test_rehearsal_workflow_never_publishes():
    text = (ROOT / ".github/workflows/rehearsal.yml").read_text(encoding="utf-8")
    for forbidden in ("ANTHROPIC_API_KEY", "deploy-pages", "pages: write", "git add shows docs"):
        assert forbidden not in text
    assert "git add shows/*/data/costs.json shows/*/COSTS.md" in text  # it only commits its own cost


def test_elevenlabs_key_only_reaches_the_voice_check():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/rehearsal.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert on["workflow_dispatch"]["inputs"]["with_voice"]["default"] is False
    step = next(s for s in wf["jobs"]["rehearsal"]["steps"] if s.get("name") == "Rehearse the publication")
    assert step["env"]["ELEVENLABS_API_KEY"].startswith("${{ inputs.with_voice &&")


def test_voice_check_uses_both_voices_and_the_real_audio(repo, gh, monkeypatch, capsys):  # noqa: F811
    seen = {}

    def fake_tts(parts, cfg, out, billed=None):
        seen["roles"] = [role for role, _ in parts]
        seen["chars"] = sum(len(text) for _, text in parts)
        billed[:] = [seen["chars"]]
        out.write_bytes(rehearsal.tts.silence_like(b"\xff\xfb\x90\xc4", 4))  # mono, like ElevenLabs
    monkeypatch.setattr(rehearsal.tts, "synthesize", fake_tts)
    rehearsal.rehearse(with_voice=True)
    assert seen["roles"] == ["host", "analyst"] and seen["chars"] < 250
    assert "1 channel(s)" in capsys.readouterr().out
    assert gh["releases"] == set()


def test_voice_check_fails_on_unrecognised_audio(repo, gh, monkeypatch):  # noqa: F811
    # Without a recognised MP3 frame the pause between voices would silently disappear.
    monkeypatch.setattr(rehearsal.tts, "synthesize", lambda parts, cfg, out, billed=None: out.write_bytes(b"\x00" * 5000))
    monkeypatch.setattr(rehearsal, "MP3", lambda path: type("I", (), {"info": type("N", (), {
        "length": 4.0, "channels": 1, "bitrate": 128000, "sample_rate": 44100})})())
    with pytest.raises(RuntimeError, match="format not recognised"):
        rehearsal.rehearse(with_voice=True)
    assert gh["releases"] == set()


def test_without_voice_elevenlabs_is_never_called(repo, gh, monkeypatch):  # noqa: F811
    monkeypatch.setattr(rehearsal.tts, "synthesize", lambda *a: pytest.fail("ElevenLabs called"))
    rehearsal.rehearse()
