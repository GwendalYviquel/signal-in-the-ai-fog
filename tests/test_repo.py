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


def triggers(wf):
    return wf.get("on", wf.get(True))  # YAML 1.1 reads the "on" key as True


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_every_workflow_parses_and_can_be_started_by_hand(name):
    wf = workflow(name)
    assert "workflow_dispatch" in triggers(wf)


def test_runs_that_write_data_never_overlap():
    # Daily, preview and rehearsal runs commit or create releases: one at a time.
    groups = {workflow(n)["concurrency"]["group"] for n in ("daily-episode.yml", "preview-episode.yml",
                                                            "rehearsal.yml")}
    assert groups == {"daily-episode"}


def test_daily_schedule_is_weekdays_only():
    schedules = triggers(workflow("daily-episode.yml")).get("schedule") or []
    for s in schedules:
        assert s["cron"].split()[4] == "1-5", "episodes are produced Monday to Friday only"


def test_daily_manual_run_defaults_to_dry_run():
    inputs = triggers(workflow("daily-episode.yml"))["workflow_dispatch"]["inputs"]
    assert inputs["dry_run"]["default"] is True and inputs["force"]["default"] is False


def test_daily_publication_steps_are_skipped_in_dry_run():
    steps = next(iter(workflow("daily-episode.yml")["jobs"].values()))["steps"]
    after = steps[[s.get("name") for s in steps].index("Keep today's script") + 1:]
    assert after and all(s.get("if") == "env.DRY_RUN == 'false'" for s in after)


def test_published_data_is_committed_and_deployed():
    for name in ("daily-episode.yml", "preview-episode.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "git add data docs" in text and "actions/deploy-pages" in text


def test_site_is_redeployed_when_docs_change():
    on = triggers(workflow("deploy-site.yml"))
    assert on["push"]["paths"] == ["docs/**"] and on["push"]["branches"] == ["main"]


def test_tests_run_on_every_push():
    on = triggers(workflow("tests.yml"))
    assert on["push"]["branches"] == ["main"] and "pull_request" in on


def test_site_tests_cannot_be_skipped_in_ci():
    text = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
    assert "playwright install" in text and 'REQUIRE_BROWSER: "1"' in text


def test_config_is_ready_to_publish(cfg):
    # main.check_config blocks publication while a TO_FILL placeholder remains.
    import yaml
    text = yaml.safe_dump(cfg)
    assert "TO_FILL" not in text
    assert cfg["podcast"]["owner_email"] and "@" in cfg["podcast"]["owner_email"]


def test_testing_journal_lists_every_test_file_with_its_count():
    # TESTING.md documents the suite and every real run: it must not fall behind the code.
    import re
    journal = (ROOT / "TESTING.md").read_text(encoding="utf-8")
    documented = dict(re.findall(r"^\| `(test_\w+\.py)` \| (\d+) \|", journal, re.M))
    actual = {p.name: str(p.read_text(encoding="utf-8").count("\ndef test_"))
              for p in (ROOT / "tests").glob("test_*.py")}
    assert documented == actual


def test_voice_check_workflow_only_gets_the_elevenlabs_key():
    wf = workflow("check-voices.yml")
    step = next(s for s in wf["jobs"]["voices"]["steps"] if s.get("name") == "Check every voice")
    assert set(step["env"]) == {"ELEVENLABS_API_KEY", "VOICE_IDS"} and step["run"] == "python -m podcast.tts"
    assert triggers(wf)["push"]["paths"] == ["config.yaml"]
