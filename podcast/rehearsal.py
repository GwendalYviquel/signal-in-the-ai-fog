"""Rehearsal of the publication path, without ElevenLabs and without publishing anything.

Runs what only a real publication would exercise on GitHub: upload of an MP3 as a
release asset with gh, download of that asset from its public URL, and the RSS feed
and catalog built with it. The audio is a few seconds of silence, the feed and catalog
are only validated (never written or deployed), and the release is always deleted.

Usage: python -m podcast.rehearsal (in GitHub Actions, see .github/workflows/rehearsal.yml)
"""
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import yaml
from mutagen.mp3 import MP3

from . import catalog, feed, main, publish, tts

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


def rehearse() -> None:
    cfg = yaml.safe_load((main.ROOT / "config.yaml").read_text(encoding="utf-8"))
    tag = f"rehearsal-{os.getenv('GITHUB_RUN_ID', 'local')}"
    main.BUILD.mkdir(exist_ok=True)
    mp3 = main.BUILD / f"{tag}.mp3"
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
            "audio_url": audio_url, "audio_bytes": mp3.stat().st_size, "duration_seconds": MP3(mp3).info.length,
        }
        episodes = main.load(main.EPISODES) + [episode]
        base_url = cfg["podcast"].get("base_url") or publish.pages_url()
        channel = ET.fromstring(feed.build_feed(cfg, episodes, base_url)).find("channel")
        enclosures = [i.find("enclosure").get("url") for i in channel.findall("item")]
        assert audio_url in enclosures, "the feed does not point to the uploaded audio"
        assert base_url.startswith("https://") and base_url.endswith("/"), f"unexpected site URL {base_url}"
        data = catalog.build_catalog(cfg, episodes, main.load(main.PREVIEWS), main.ROOT / "data",
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
    rehearse()
