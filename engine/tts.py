"""Speech synthesis with the ElevenLabs API: two voices, text split into chunks."""
from __future__ import annotations

import datetime as dt
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


def _frames(audio: bytes):
    """Yield (frame bytes, sample rate) for each MPEG-1 Layer III frame, skipping an ID3v2 tag."""
    i = 0
    if audio[:3] == b"ID3" and len(audio) >= 10:
        i = 10 + ((audio[6] << 21) | (audio[7] << 14) | (audio[8] << 7) | audio[9])
    while i < len(audio) - 4:
        b1, b2 = audio[i + 1], audio[i + 2]
        bitrate_idx, rate_idx = b2 >> 4, (b2 >> 2) & 0x3
        if audio[i] == 0xFF and (b1 & 0xFE) == 0xFA and 0 < bitrate_idx < 15 and rate_idx != 3:
            rate = _SAMPLE_RATES[rate_idx]
            length = 144 * _BITRATES[bitrate_idx] * 1000 // rate + ((b2 >> 1) & 1)
            yield audio[i:i + length], rate
            i += length
        else:
            i += 1


def _is_header_frame(frame: bytes) -> bool:
    """Xing/Info/VBRI frames describe the file they start (its duration), they carry no sound."""
    return b"Xing" in frame[4:40] or b"Info" in frame[4:40] or frame[36:40] == b"VBRI"


def audio_frames(audio: bytes) -> bytes:
    """Only the sound frames of an MP3: no ID3 tag, no Xing/Info header.

    Every ElevenLabs response starts with an Info header giving the duration of that response
    alone. Concatenated as is, the first one made players and tools read the duration of the
    first chunk for the whole episode (3.6 s instead of 9.7 s on the first real voice sample)."""
    return b"".join(f for f, _ in _frames(audio) if not _is_header_frame(f))


def mp3_duration(audio: bytes) -> float:
    """Duration in seconds, by counting sound frames (1152 samples each)."""
    return sum(1152 / rate for f, rate in _frames(audio) if not _is_header_frame(f))


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


def synthesize(parts: list[tuple[str, str]], tts_cfg: dict, out_path: Path, billed: list | None = None,
               timeline: list | None = None) -> int:
    """parts: (voice role, text) in reading order; roles map to voices in tts_cfg["voices"].
    Returns the characters billed. billed (optional list) receives the count as it grows, so a
    caller still knows what was spent when a request fails half-way. timeline (optional list)
    receives {"text", "start", "end"} for every chunk, in seconds: chapters and transcripts."""
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    params = {"output_format": tts_cfg["output_format"]}
    pause_seconds, pause = tts_cfg.get("pause_seconds", 0), None
    runs = _runs(parts, tts_cfg)
    total = sum(len(text) for _, _, text in runs)
    requests_count, billed_chars, position = 0, 0, 0.0
    with open(out_path, "wb") as f:
        for n, (role, voice, text) in enumerate(runs):
            if n and pause:
                f.write(pause)  # a short breath when the other voice takes over
                position += mp3_duration(pause)
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
                    audio = audio_frames(_post(API.format(voice_id=voice), headers, params, body))
                except RuntimeError as e:
                    # Name the voice: a failure on the second voice used to look like one on the first.
                    raise RuntimeError(f"{e} [request {requests_count + 1}, {role} voice {voice}, "
                                       f"{len(chunk)} characters; {billed_chars} characters already "
                                       f"synthesised in this run]") from None
                if not audio:
                    raise RuntimeError(f"ElevenLabs returned no MP3 audio for request {requests_count + 1} "
                                       f"({role} voice {voice}): check tts.output_format")
                requests_count += 1
                billed_chars += len(chunk)
                if billed is not None:
                    billed[:] = [billed_chars]
                print(f"ElevenLabs request {requests_count}: {role} voice {voice}, {len(chunk)} characters, ok")
                if pause is None:
                    pause = silence_like(audio, pause_seconds) if pause_seconds else b""
                f.write(audio)
                length = mp3_duration(audio)
                if timeline is not None:
                    timeline.append({"text": chunk, "start": round(position, 2), "end": round(position + length, 2)})
                position += length
    print(f"Speech synthesis: {total} characters, {len(runs)} voice turns, {requests_count} request(s)")
    return billed_chars


CHECK_TEXT = "Hi."  # 3 characters per voice: enough to prove the API accepts the voice


def voice_check_results(tts_cfg: dict) -> dict[str, str]:
    """Synthesise one word with each configured voice, independently, so that one failure does
    not hide another. Returns {role: "ok" or the error}."""
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
    print(f"Voice check cost: {len(CHECK_TEXT) * sum(r == 'ok' for r in results.values())} characters "
          f"(failed requests are not billed)")
    return results


def voice_check_characters(results: dict[str, str]) -> int:
    return len(CHECK_TEXT) * sum(r == "ok" for r in results.values())  # failed requests are not billed


def raise_if_failed(results: dict[str, str]) -> dict[str, str]:
    failed = [role for role, r in results.items() if r != "ok"]
    if failed:
        raise RuntimeError(f"Voice check failed for: {', '.join(failed)} (see above)")
    return results


def check_voices(tts_cfg: dict) -> dict[str, str]:
    """voice_check_results, raising if any voice fails."""
    return raise_if_failed(voice_check_results(tts_cfg))


SUBSCRIPTION = "https://api.elevenlabs.io/v1/user/subscription"
CHARS_PER_WORD = 6.5  # spoken English or French, spaces included: a first episode's estimate
MARGIN = 1.15         # an episode runs a little longer than the previous ones


def read_credits() -> dict | None:
    """The account's character credits ({used, limit, left, reset, can_extend}), shared by every show,
    or None when they cannot be read (network, or a key without the user_read permission)."""
    try:
        r = requests.get(SUBSCRIPTION, headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=30)
    except requests.RequestException as e:
        print(f"ElevenLabs credits not read ({type(e).__name__}): the run goes on")
        return None
    if r.status_code != 200:
        print(f"ElevenLabs credits not read (HTTP {r.status_code}: {r.text[:200]}): the run goes on. "
              "Give the API key the user_read permission to check them before each run.")
        return None
    data = r.json()
    used, limit = int(data.get("character_count") or 0), int(data.get("character_limit") or 0)
    reset = data.get("next_character_count_reset_unix")
    return {"used": used, "limit": limit, "left": max(0, limit - used),
            "reset": dt.datetime.fromtimestamp(reset, dt.timezone.utc).date().isoformat() if reset else "",
            "can_extend": bool(data.get("can_extend_character_limit") and data.get("allowed_to_extend_character_limit"))}


def characters_needed(runs: list[dict], target_words: int) -> int:
    """Characters an episode of this show needs: its published episodes' average, or an estimate
    from its target length before the first one, with a margin either way."""
    published = [r["elevenlabs_characters"] for r in runs
                 if r.get("mode") == "publish" and r.get("outcome") == "ok" and r.get("elevenlabs_characters")]
    base = sum(published) / len(published) if published else target_words * CHARS_PER_WORD
    return round(base * MARGIN)


def check_credits(credits: dict | None, needed: int) -> str:
    """"" when the episode can be voiced (or the credits are unknown), else why it cannot."""
    if credits is None or credits["left"] >= needed:
        return ""
    if credits["can_extend"]:
        print(f"ElevenLabs: {credits['left']:,} characters left, {needed:,} needed: the plan's usage-based "
              "billing covers the rest, at extra cost")
        return ""
    reset = f", renewed on {credits['reset']}" if credits["reset"] else ""
    return (f"ElevenLabs credits too low: {credits['left']:,} characters left of {credits['limit']:,}{reset}, "
            f"about {needed:,} needed for this episode. Nothing was paid: top up or upgrade the ElevenLabs "
            "plan, then run the catch-up.")


def candidate_voices(tts_cfg: dict, ids: str) -> dict:
    """Config for checking candidate voice IDs (comma-separated) instead of the configured ones."""
    candidates = [v.strip() for v in ids.split(",") if v.strip()]
    return {**tts_cfg, "voices": {f"candidate {i + 1}": v for i, v in enumerate(candidates)}}


if __name__ == "__main__":
    from . import costs, show as shows
    cfg = shows.load().cfg
    ids = os.getenv("VOICE_IDS", "").strip()
    tts_cfg = candidate_voices(cfg["tts"], ids) if ids else cfg["tts"]
    results = voice_check_results(tts_cfg)
    # The credits too: a free way to check the key's user_read permission and refresh COSTS.md.
    credits = read_credits()
    if credits:
        print(f"ElevenLabs credits: {credits['left']:,} characters left of {credits['limit']:,}"
              + (f", renewed on {credits['reset']}" if credits["reset"] else ""))
    costs.record(cfg, "voice check", "ok" if all(r == "ok" for r in results.values()) else "failed",
                 elevenlabs_characters=voice_check_characters(results), credits=credits,
                 note=("candidates: " + ids) if ids else "configured voices")
    raise_if_failed(results)
