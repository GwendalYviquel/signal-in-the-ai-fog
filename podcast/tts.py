"""Speech synthesis with the ElevenLabs API (text split into chunks)."""
import os
import time
from pathlib import Path

import requests

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def split_text(text: str, max_chars: int) -> list[str]:
    pieces = []
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(para) <= max_chars:
            pieces.append(para)
        else:  # paragraph too long: split by sentence
            pieces += [s for s in para.replace(". ", ".\n").splitlines() if s.strip()]
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


def synthesize(text: str, tts_cfg: dict, out_path: Path) -> None:
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"}
    url = API.format(voice_id=tts_cfg["voice_id"])
    params = {"output_format": tts_cfg["output_format"]}
    chunks = split_text(text, tts_cfg["max_chars_per_request"])
    print(f"Speech synthesis: {len(text)} characters in {len(chunks)} request(s)")
    with open(out_path, "wb") as f:
        for i, chunk in enumerate(chunks):
            body = {"text": chunk, "model_id": tts_cfg["model_id"]}
            if tts_cfg.get("use_context"):
                if i > 0:
                    body["previous_text"] = chunks[i - 1][-500:]
                if i < len(chunks) - 1:
                    body["next_text"] = chunks[i + 1][:500]
            f.write(_post(url, headers, params, body))
