"""Repository hygiene: workflows, secrets wiring and confidentiality of the public repo."""
import os
import subprocess

import pytest
import yaml

from conftest import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
GENERATION_ENV = {"ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID", "FORBIDDEN_TERMS", "EDITORIAL_CONTEXT"}


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def step(wf, name):
    steps = next(iter(wf["jobs"].values()))["steps"]
    return next(s for s in steps if s.get("name") == name)


def step_names(wf):
    return [s.get("name") for s in next(iter(wf["jobs"].values()))["steps"]]


@pytest.mark.parametrize("name,step_name", [("daily-episode.yml", "Generate the episode"),
                                            ("preview-episode.yml", "Generate the script")])
def test_generation_steps_receive_every_secret(name, step_name):
    # Regression (2026-10-20): ANTHROPIC_WORKSPACE_ID had to be wired into every workflow that calls Claude.
    env = set(step(workflow(name), step_name)["env"])
    assert GENERATION_ENV <= env


def test_daily_workflow_has_the_publication_secrets():
    env = set(step(workflow("daily-episode.yml"), "Generate the episode")["env"])
    assert {"ELEVENLABS_API_KEY", "GH_TOKEN"} <= env


@pytest.mark.parametrize("name,step_name", [("daily-episode.yml", "Generate the episode"),
                                            ("preview-episode.yml", "Generate the script")])
def test_tests_run_before_any_generation(name, step_name):
    names = step_names(workflow(name))
    assert "Run tests" in names and names.index("Run tests") < names.index(step_name)


def test_preview_workflow_never_touches_audio_or_feed():
    text = (WORKFLOWS / "preview-episode.yml").read_text(encoding="utf-8")
    assert "ELEVENLABS_API_KEY" not in text
    assert 'PREVIEW: "true"' in text


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


@pytest.mark.parametrize("path", ["private/editorial_context.md", ".claude/settings.local.json"])
def test_private_files_are_ignored(path):
    if git("rev-parse").returncode != 0:
        pytest.skip("not a git checkout")
    assert git("check-ignore", "-q", path).returncode == 0


def test_no_forbidden_term_in_tracked_files():
    # The company must never be named in the public repository. Runs when the secret is available (CI).
    terms = [t.strip().lower() for t in os.getenv("FORBIDDEN_TERMS", "").split(",") if t.strip()]
    if not terms:
        pytest.skip("FORBIDDEN_TERMS not set")
    if git("rev-parse").returncode != 0:
        pytest.skip("not a git checkout")
    leaks = []
    for path in git("ls-files").stdout.splitlines():
        try:
            content = (ROOT / path).read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        leaks += [path for term in terms if term in content]
    assert leaks == []


def test_prompt_has_the_length_placeholder():
    assert (ROOT / "prompts" / "system.md").read_text(encoding="utf-8").count("{target_words}") == 1
