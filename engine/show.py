"""A show: its configuration and where its files live. Every module of the engine works on one.

shows/<slug>/
  show.yaml        podcast, generation, voices, themes, sources, costs
  prompt.md        the editorial line given to Claude
  data/            episodes.json, scripts/, previews.json, previews/, dossiers/, costs.json, stats.json, spotify.json
  COSTS.md, STATS.md, finops-dashboard-{light,dark}.svg
docs/<site_path>/  the show's site and feed on GitHub Pages ("" keeps a show at the root)
private/<slug>/editorial_context.md   private audience context, never committed (or a secret)

The show is chosen with the SHOW environment variable (workflows) or by name; the first show,
signal-in-the-ai-fog, is the default so that existing commands keep working.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT = "signal-in-the-ai-fog"


@dataclass(frozen=True)
class Show:
    slug: str
    repo: Path
    cfg: dict

    @property
    def home(self) -> Path:
        return self.repo / "shows" / self.slug

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def episodes(self) -> Path:
        return self.data / "episodes.json"

    @property
    def scripts(self) -> Path:
        return self.data / "scripts"

    @property
    def previews(self) -> Path:
        return self.data / "previews.json"

    @property
    def preview_scripts(self) -> Path:
        return self.data / "previews"

    @property
    def prompt(self) -> Path:
        return self.home / "prompt.md"

    @property
    def site_path(self) -> str:
        """The show's folder in the site, "" for a show at the root (its URLs never move)."""
        return str(self.cfg["podcast"].get("site_path", self.slug)).strip("/")

    @property
    def docs(self) -> Path:
        return self.repo / "docs" / self.site_path if self.site_path else self.repo / "docs"

    @property
    def build(self) -> Path:
        return self.repo / "build" / self.slug

    @property
    def cost_ledger(self) -> Path:
        return self.data / "costs.json"

    @property
    def cost_report(self) -> Path:
        return self.home / "COSTS.md"

    @property
    def charts(self) -> Path:
        return self.home  # finops-dashboard-{light,dark}.svg

    @property
    def stats_ledger(self) -> Path:
        return self.data / "stats.json"

    @property
    def stats_report(self) -> Path:
        return self.home / "STATS.md"

    @property
    def spotify_log(self) -> Path:
        return self.data / "spotify.json"

    @property
    def private_context(self) -> Path:
        return self.repo / "private" / self.slug / "editorial_context.md"

    def tag(self, day: str) -> str:
        """Release tag of an episode; also the end of its GUID, which must never change."""
        return f"{self.cfg['podcast'].get('release_prefix', self.slug)}-{day}"

    def base_url(self, pages_url: str) -> str:
        """The show's public URL: podcast.base_url, or its folder on the repository's Pages site."""
        explicit = self.cfg["podcast"].get("base_url")
        if explicit:
            return explicit.rstrip("/") + "/"
        root = pages_url.rstrip("/") + "/"
        return root + (self.site_path + "/" if self.site_path else "")


def slugs(repo: Path | None = None) -> list[str]:
    return sorted(p.parent.name for p in ((repo or REPO) / "shows").glob("*/show.yaml"))


def load(slug: str | None = None, repo: Path | None = None) -> Show:
    """The show named, or the SHOW environment variable, or the default show."""
    repo = repo or REPO
    slug = slug or os.getenv("SHOW", "").strip() or DEFAULT
    path = repo / "shows" / slug / "show.yaml"
    if not path.exists():
        raise SystemExit(f"No show {slug!r}: expected {path}. Shows: {', '.join(slugs(repo)) or 'none'}")
    return Show(slug, repo, yaml.safe_load(path.read_text(encoding="utf-8")))


def context_secret(show: Show) -> str:
    """Name of the GitHub secret holding the show's private editorial context."""
    explicit = show.cfg["podcast"].get("context_secret")
    return explicit or "EDITORIAL_CONTEXT_" + show.slug.upper().replace("-", "_")


def scheduled(show: Show) -> bool:
    """Whether scheduled attempts and the watchdog run this show (generation.scheduled, default true).
    A show still in preparation (voices to choose, first preview to read) stays out of them."""
    return bool(show.cfg.get("generation", {}).get("scheduled", True))


def matrix(which: str, repo: Path | None = None) -> dict:
    """GitHub Actions matrix of the shows to run: "all" (scheduled attempts: the scheduled shows) or one."""
    names = [s for s in slugs(repo) if scheduled(load(s, repo))] if which == "all" else [which or DEFAULT]
    return {"include": [{"show": s, "context_secret": context_secret(load(s, repo))} for s in names]}


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "matrix":
        raise SystemExit("usage: python -m engine.show matrix all|<slug>")
    print("matrix=" + json.dumps(matrix(sys.argv[2])))
