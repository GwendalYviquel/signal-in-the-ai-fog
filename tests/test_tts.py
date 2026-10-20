"""ElevenLabs synthesis: chunking, request shape and retries (HTTP is mocked)."""
from types import SimpleNamespace

import pytest

from podcast import tts

CFG = {"voices": {"host": "hostVoice", "analyst": "analystVoice"}, "model_id": "eleven_multilingual_v2",
       "output_format": "mp3_44100_128", "max_chars_per_request": 200, "use_context": True}
# One mono MPEG-1 Layer III frame (128 kbps, 44.1 kHz), as ElevenLabs returns.
MONO_FRAME = b"\xff\xfb\x90\xc4" + b"\x01" * 413


def test_chunks_respect_the_limit_and_keep_all_text():
    text = "\n\n".join(f"Paragraph {i}. " + "Some words here. " * 8 for i in range(6))
    chunks = tts.split_text(text, 200)
    assert all(0 < len(c) <= 200 for c in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(text.split())


def test_sentence_longer_than_the_limit_is_split_by_words():
    # A single sentence above max_chars used to be sent whole, and rejected by ElevenLabs.
    sentence = " ".join(["word"] * 120)  # about 600 characters, no period
    chunks = tts.split_text(sentence, 200)
    assert all(len(c) <= 200 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 120


def test_short_text_is_one_chunk():
    assert tts.split_text("Hello there.", 200) == ["Hello there."]


@pytest.fixture
def posts(monkeypatch):
    sent, statuses = [], []

    def fake_post(url, headers, params, json, timeout):
        sent.append(SimpleNamespace(url=url, headers=headers, params=params, body=json))
        status = statuses.pop(0) if statuses else 200
        return SimpleNamespace(status_code=status, content=MONO_FRAME, text="error detail")

    monkeypatch.setattr(tts.requests, "post", fake_post)
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    return sent, statuses


def test_requests_carry_voice_model_format_and_context(posts, tmp_path):
    sent, _ = posts
    text = "\n\n".join(["First paragraph. " * 8, "Second paragraph. " * 8, "Third paragraph. " * 8])
    out = tmp_path / "ep.mp3"
    tts.synthesize([("host", text)], CFG, out)
    assert len(sent) == 3
    assert sent[0].url == "https://api.elevenlabs.io/v1/text-to-speech/hostVoice"
    assert sent[0].params == {"output_format": "mp3_44100_128"}
    assert sent[0].headers["xi-api-key"] == "test-key"
    assert sent[0].body["model_id"] == "eleven_multilingual_v2"
    assert "previous_text" not in sent[0].body and "next_text" in sent[0].body
    assert "previous_text" in sent[2].body and "next_text" not in sent[2].body
    assert out.read_bytes() == MONO_FRAME * 3


def test_retries_on_rate_limit_then_succeeds(posts, tmp_path):
    sent, statuses = posts
    statuses += [429, 503]
    tts.synthesize([("host", "Short text.")], CFG, tmp_path / "ep.mp3")
    assert len(sent) == 3


def test_auth_error_fails_immediately(posts, tmp_path):
    sent, statuses = posts
    statuses += [401]
    with pytest.raises(RuntimeError, match="ElevenLabs 401"):
        tts.synthesize([("host", "Short text.")], CFG, tmp_path / "ep.mp3")
    assert len(sent) == 1


def test_voice_settings_are_sent_with_every_request(posts, tmp_path):
    sent, _ = posts
    settings = {"stability": 0.55, "similarity_boost": 0.75, "style": 0.1, "use_speaker_boost": True, "speed": 1.0}
    text = "\n\n".join(["First paragraph. " * 8, "Second paragraph. " * 8])
    tts.synthesize([("host", text)], CFG | {"voice_settings": settings}, tmp_path / "ep.mp3")
    assert len(sent) == 2 and all(s.body["voice_settings"] == settings for s in sent)


def test_voice_settings_in_config_are_within_elevenlabs_ranges(cfg):
    vs = cfg["tts"]["voice_settings"]
    assert all(0 <= vs[k] <= 1 for k in ("stability", "similarity_boost", "style"))
    assert 0.7 <= vs["speed"] <= 1.2


def test_config_has_two_distinct_voices(cfg):
    voices = cfg["tts"]["voices"]
    assert set(voices) == {"host", "analyst"}
    assert "TO_FILL" not in voices.values() and voices["host"] != voices["analyst"]


def test_each_part_is_read_by_its_voice(posts, tmp_path):
    sent, _ = posts
    parts = [("host", "Opening."), ("host", "Facts one."), ("analyst", "Read one."),
             ("host", "Facts two."), ("analyst", "Read two."), ("host", "Sign-off.")]
    tts.synthesize(parts, CFG, tmp_path / "ep.mp3")
    assert [(s.url.rsplit("/", 1)[1], s.body["text"]) for s in sent] == [
        ("hostVoice", "Opening.\n\nFacts one."), ("analystVoice", "Read one."),
        ("hostVoice", "Facts two."), ("analystVoice", "Read two."), ("hostVoice", "Sign-off.")]


def test_context_never_crosses_voices(posts, tmp_path):
    sent, _ = posts
    tts.synthesize([("host", "Facts. " * 40), ("analyst", "Read. " * 10)], CFG, tmp_path / "ep.mp3")
    analyst = [s for s in sent if s.url.endswith("analystVoice")]
    assert analyst and all("previous_text" not in s.body and "next_text" not in s.body for s in analyst)
    host = [s for s in sent if s.url.endswith("hostVoice")]
    assert len(host) > 1 and "next_text" not in host[-1].body  # last host chunk: no context from the analyst


def test_pause_between_voice_turns_matches_the_audio_format(posts, tmp_path):
    out = tmp_path / "ep.mp3"
    tts.synthesize([("host", "A."), ("analyst", "B."), ("host", "C.")], CFG | {"pause_seconds": 0.6}, out)
    pause = tts.silence_like(MONO_FRAME, 0.6)
    assert pause[:4] == b"\xff\xfb\x90\xc4"  # mono, like the voice audio
    assert out.read_bytes() == MONO_FRAME + pause + MONO_FRAME + pause + MONO_FRAME


def test_no_pause_when_disabled(posts, tmp_path):
    out = tmp_path / "ep.mp3"
    tts.synthesize([("host", "A."), ("analyst", "B.")], CFG | {"pause_seconds": 0}, out)
    assert out.read_bytes() == MONO_FRAME * 2


def test_silence_like_keeps_the_frame_format():
    padded_stereo = b"\xff\xfb\x92\x00" + b"\x01" * 414  # padding bit set
    frames = tts.silence_like(b"ID3" + padded_stereo, 1.0)
    assert frames[:4] == b"\xff\xfb\x90\x00"  # padding cleared, stereo kept
    assert len(frames) == 417 * 38 and set(frames[4:417]) == {0}
    assert tts.silence_like(b"not audio", 1.0) == b""


def test_single_voice_config_still_works(posts, tmp_path):
    sent, _ = posts
    cfg = {k: v for k, v in CFG.items() if k != "voices"} | {"voice_id": "onlyVoice"}
    tts.synthesize([("host", "A."), ("analyst", "B.")], cfg, tmp_path / "ep.mp3")
    assert {s.url.rsplit("/", 1)[1] for s in sent} == {"onlyVoice"}
