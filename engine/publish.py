"""MP3 hosting as a GitHub release asset (via the gh CLI)."""
import os
import subprocess
from pathlib import Path


def repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]  # "owner/repo", set by GitHub Actions


def pages_url() -> str:
    owner, name = repo().split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def delete_release(tag: str) -> None:
    subprocess.run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], check=False)


def upload_audio(mp3: Path, tag: str, title: str, notes: str) -> str:
    subprocess.run(["gh", "release", "create", tag, str(mp3), "--title", title,
                    "--notes", notes, "--latest=false"], check=True)
    return f"https://github.com/{repo()}/releases/download/{tag}/{mp3.name}"


def release_exists(tag: str) -> bool:
    return subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
