"""Speech synthesis with the ElevenLabs API: two voices, text split into chunks."""
import os
import time
from pathlib import Path

import requests

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def _split_words(text: str, max_chars: int) -> list[str]:
    parts, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > max_chars:
            parts.append(current)
            current = ""
        current = f"{current} {word}".strip()
    return parts + [current] if current else parts


def split_text(text: str, max_chars: int) -> list[str]:
    pieces = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(para) <= max_chars:
            pieces.append(para)
        else:  # paragraph too long: split by sentence, then by words as a last resort
            for sentence in [s for s in para.replace(". ", ".\n").splitlines() if s.strip()]:
                pieces += _split_words(sentence, max_chars) if len(sentence) > max_chars else [sentence]
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > max_chars:
            chunks.append(current.strip())
            current = ""
        current += piece + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _post(url, headers, params, body, retries=3):
    for attempt in range(retries):
        r = requests.post(url, headers=headers, params=params, json=body, timeout=180)
        if r.status_code == 200:
            return r.content
        if r.status_code in (429, 500, 502, 503) and attempt < retries - 1:
            time.sleep(10 * (attempt + 1))
            continue
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")


# MPEG-1 Layer III frame at 128 kbps, 44.1 kHz, stereo, with an empty payload: silence.
SILENT_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def silence(seconds: float) -> bytes:
    return SILENT_FRAME * round(seconds * 44100 / 1152)


_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]  # MPEG-1 Layer III, kbps
_SAMPLE_RATES = [44100, 48000, 32000]


def silence_like(audio: bytes, seconds: float) -> bytes:
    """Silence in exactly the same MP3 format (channels, bitrate, rate) as the given audio,
    so it can be concatenated without glitches. Empty if the format is not recognised."""
    for i in range(len(audio) - 3):
        b1, b2, b3 = audio[i + 1], audio[i + 2], audio[i + 3]
        if audio[i] != 0xFF or (b1 & 0xFE) != 0xFA:  # sync + MPEG-1 + Layer III
            continue
        bitrate_idx, rate_idx = b2 >> 4, (b2 >> 2) & 0x3
        if not 0 < bitrate_idx < 15 or rate_idx == 3:
            continue
        rate = _SAMPLE_RATES[rate_idx]
        header = bytes([0xFF, b1, b2 & 0xFD, b3])  # same header, padding bit cleared
        frame = header + b"\x00" * (144 * _BITRATES[bitrate_idx] * 1000 // rate - 4)
        return frame * round(seconds * rate / 1152)
    return b""


def voice_for(role: str, tts_cfg: dict) -> str:
    voices = tts_cfg.get("voices") or {}
    return voices.get(role) or voices.get("host") or tts_cfg["voice_id"]


def _runs(parts: list[tuple[str, str]], tts_cfg: dict) -> list[tuple[str, str, str]]:
    """Merge consecutive parts read by the same voice: (role, voice, text)."""
    runs = []
    for role, text in parts:
        voice = voice_for(role, tts_cfg)
        if runs and runs[-1][1] == voice:
            runs[-1] = (runs[-1][0], voice, runs[-1][2] + "\n\n" + text)
        else:
            runs.append((role, voice, text))
    return runs


def synthesize(parts: list[tuple[str, str]], tts_cfg: dict, out_path: Path) -> None:
    """parts: (voice role, text) in reading order; roles map to voices in tts_cfg["voices"]."""
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    params = {"output_format": tts_cfg["output_format"]}
    pause_seconds, pause = tts_cfg.get("pause_seconds", 0), None
    runs = _runs(parts, tts_cfg)
    total = sum(len(text) for _, _, text in runs)
    requests_count, billed = 0, 0
    with open(out_path, "wb") as f:
        for n, (role, voice, text) in enumerate(runs):
            if n and pause:
                f.write(pause)  # a short breath when the other voice takes over
            chunks = split_text(text, tts_cfg["max_chars_per_request"])
            for i, chunk in enumerate(chunks):
                body = {"text": chunk, "model_id": tts_cfg["model_id"]}
                if tts_cfg.get("voice_settings"):
                    body["voice_settings"] = tts_cfg["voice_settings"]
                if tts_cfg.get("use_context"):  # continuity within the same voice only
                    if i > 0:
                        body["previous_text"] = chunks[i - 1][-500:]
                    if i < len(chunks) - 1:
                        body["next_text"] = chunks[i + 1][:500]
                try:
                    audio = _post(API.format(voice_id=voice), headers, params, body)
                except RuntimeError as e:
                    # Name the voice: a failure on the second voice used to look like one on the first.
                    raise RuntimeError(f"{e} [request {requests_count + 1}, {role} voice {voice}, "
                                       f"{len(chunk)} characters; {billed} characters already "
                                       f"synthesised in this run]") from None
                requests_count += 1
                billed += len(chunk)
                print(f"ElevenLabs request {requests_count}: {role} voice {voice}, {len(chunk)} characters, ok")
                if pause is None:
                    pause = silence_like(audio, pause_seconds) if pause_seconds else b""
                f.write(audio)
    print(f"Speech synthesis: {total} characters, {len(runs)} voice turns, {requests_count} request(s)")


CHECK_TEXT = "Hi."  # 3 characters per voice: enough to prove the API accepts the voice


def check_voices(tts_cfg: dict) -> dict[str, str]:
    """Synthesise one word with each configured voice, independently, so that one failure does
    not hide another. Returns {role: "ok" or the error}; raises if any voice fails."""
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    params = {"output_format": tts_cfg["output_format"]}
    voices = tts_cfg.get("voices") or {"host": tts_cfg["voice_id"]}
    results = {}
    for role, voice in voices.items():
        body = {"text": CHECK_TEXT, "model_id": tts_cfg["model_id"]}
        if tts_cfg.get("voice_settings"):
            body["voice_settings"] = tts_cfg["voice_settings"]
        try:
            _post(API.format(voice_id=voice), headers, params, body)
            results[role] = "ok"
        except RuntimeError as e:
            results[role] = str(e)
        print(f"Voice check, {role} voice {voice}: {results[role]}")
    print(f"Voice check cost: {len(CHECK_TEXT) * len(voices)} characters")
    failed = [role for role, r in results.items() if r != "ok"]
    if failed:
        raise RuntimeError(f"Voice check failed for: {', '.join(failed)} (see above)")
    return results


def candidate_voices(tts_cfg: dict, ids: str) -> dict:
    """Config for checking candidate voice IDs (comma-separated) instead of the configured ones."""
    candidates = [v.strip() for v in ids.split(",") if v.strip()]
    return {**tts_cfg, "voices": {f"candidate {i + 1}": v for i, v in enumerate(candidates)}}


if __name__ == "__main__":
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"))
    ids = os.getenv("VOICE_IDS", "").strip()
    check_voices(candidate_voices(cfg["tts"], ids) if ids else cfg["tts"])
