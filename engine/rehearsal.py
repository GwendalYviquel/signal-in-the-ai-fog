"""Rehearsal of the publication path, without ElevenLabs and without publishing anything.

Runs what only a real publication would exercise on GitHub: upload of an MP3 as a
release asset with gh, download of that asset from its public URL, and the RSS feed
and catalog built with it. The audio is a few seconds of silence, or with WITH_VOICE=true
two short sentences read by both ElevenLabs voices (a few cents). The feed and catalog are
only validated (never written or deployed), and the release is always deleted.

Usage: python -m engine.rehearsal (in GitHub Actions, see .github/workflows/rehearsal.yml)
"""
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import yaml
from mutagen.mp3 import MP3

from . import catalog, costs, feed, main, publish, tts
from . import show as shows

def silent_mp3(path: Path, seconds: int = 3) -> None:
    path.write_bytes(tts.silence(seconds))


def check_download(url: str, size: int, tries: int = 6) -> None:
    """The asset must be publicly downloadable, as Spotify will fetch it."""
    for attempt in range(tries):
        r = requests.get(url, timeout=60, allow_redirects=True)
        if r.status_code == 200 and len(r.content) == size:
            return
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Audio not downloadable at {url}: HTTP {r.status_code}, {len(r.content)} bytes")


VOICE_CHECK = [  # about 170 characters in total: a few cents of ElevenLabs credits
    ("host", "This is Signal in the AI Fog. A short check of the host voice."),
    ("analyst", "The read here: the analyst voice takes over after a short pause, as in every episode."),
]


def voice_check(cfg: dict, mp3: Path, billed: list) -> None:
    """Both voices through the real ElevenLabs API, with the episode's settings and pause."""
    tts.synthesize(VOICE_CHECK, cfg["tts"], mp3, billed=billed)
    data = mp3.read_bytes()
    seconds = tts.mp3_duration(data)
    if not seconds or (cfg["tts"].get("pause_seconds") and not tts.silence_like(data[:8192], 0.1)):
        raise RuntimeError("ElevenLabs audio format not recognised: the pause between voices would be missing")
    info = MP3(mp3).info
    print(f"Voice check audio: {seconds:.1f} s, {info.channels} channel(s), {info.bitrate // 1000} kbps, "
          f"{info.sample_rate} Hz (players read {info.length:.1f} s)")
    if abs(info.length - seconds) > 0.5:
        raise RuntimeError(f"Players would read {info.length:.1f} s for {seconds:.1f} s of audio")
    if seconds < 3:
        raise RuntimeError(f"Voice check audio too short ({seconds:.1f} s)")


def rehearse(with_voice: bool = False) -> None:
    show = shows.load()
    cfg = show.cfg
    tag = f"rehearsal-{os.getenv('GITHUB_RUN_ID', 'local')}"
    show.build.mkdir(parents=True, exist_ok=True)
    mp3 = show.build / f"{tag}.mp3"
    billed = [0]
    if with_voice:
        try:
            voice_check(cfg, mp3, billed)
        finally:
            costs.record(cfg, "rehearsal", "ok" if billed[0] == sum(len(t) for _, t in VOICE_CHECK) else "failed",
                         elevenlabs_characters=billed[0], ledger=show.cost_ledger, report=show.cost_report,
                         charts=show.charts,
                         note="voice sample")
    else:
        silent_mp3(mp3)
    now = main.current_time(cfg)
    try:
        audio_url = publish.upload_audio(mp3, tag, "Rehearsal (deleted automatically)",
                                         "Automated publication test, not an episode.")
        print(f"Release asset uploaded: {audio_url}")
        check_download(audio_url, mp3.stat().st_size)
        print("Asset downloadable from its public URL")

        episode = {
            "date": now.date().isoformat(), "title": "Rehearsal", "summary": "Publication test.",
            "headlines": [], "themes": [], "sources": [{"title": "Example", "url": "https://example.com"}],
            "published_at": now.replace(microsecond=0).isoformat(), "guid": f"{publish.repo()}#{tag}",
            "audio_url": audio_url, "audio_bytes": mp3.stat().st_size, "duration_seconds": tts.mp3_duration(mp3.read_bytes()),
        }
        episodes = main.load(show.episodes) + [episode]
        base_url = show.base_url("" if cfg["podcast"].get("base_url") else publish.pages_url())
        channel = ET.fromstring(feed.build_feed(cfg, episodes, base_url)).find("channel")
        enclosures = [i.find("enclosure").get("url") for i in channel.findall("item")]
        assert audio_url in enclosures, "the feed does not point to the uploaded audio"
        assert base_url.startswith("https://") and base_url.endswith("/"), f"unexpected site URL {base_url}"
        data = catalog.build_catalog(cfg, episodes, main.load(show.previews), show.data,
                                     base_url + "feed.xml")
        assert any(e["audio_url"] == audio_url for e in data["episodes"])
        print(f"Feed and catalog valid ({len(enclosures)} episode(s), site {base_url})")
    finally:
        publish.delete_release(tag)
        if publish.release_exists(tag):
            raise RuntimeError(f"Release {tag} could not be deleted: remove it by hand")
        print(f"Release {tag} deleted")
    print("Rehearsal OK: nothing was published or committed.")


if __name__ == "__main__":
    rehearse(with_voice=os.getenv("WITH_VOICE", "false").lower() == "true")
