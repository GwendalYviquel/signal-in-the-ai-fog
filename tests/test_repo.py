"""Repository hygiene: workflows, secrets wiring and confidentiality of the public repo."""
import os
import subprocess

import pytest
import yaml

from conftest import ROOT, SHOW

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
    assert (ROOT / SHOW / "prompt.md").read_text(encoding="utf-8").count("{target_words}") == 1


def triggers(wf):
    return wf.get("on", wf.get(True))  # YAML 1.1 reads the "on" key as True


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_every_workflow_parses_and_can_be_started_by_hand(name):
    wf = workflow(name)
    if name == "dependabot-merge.yml":
        # Only meaningful for a tested Dependabot pull request: nothing to start by hand.
        assert "workflow_dispatch" not in triggers(wf)
        return
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


def test_daily_publication_steps_run_only_after_a_publication():
    # Dry runs, early attempts and attempts finding the episode out publish nothing: no deployment.
    steps = next(iter(workflow("daily-episode.yml")["jobs"].values()))["steps"]
    publication = [s for s in steps if "pages" in s.get("uses", "") or s.get("name") == "Deploy the RSS feed"]
    assert len(publication) == 3
    assert all(s.get("if") == "steps.generate.outputs.published == 'true'" for s in publication)


@pytest.mark.parametrize("name", ["daily-episode.yml", "preview-episode.yml", "rehearsal.yml", "check-voices.yml"])
def test_costs_are_committed_after_every_run_even_failed(name):
    # Learning (2026-10-20): costs must be tracked for every run, dry runs and failures included.
    steps = next(iter(workflow(name)["jobs"].values()))["steps"]
    commit = next(s for s in steps if s.get("name", "").startswith("Commit"))
    assert commit["if"].startswith("always()")
    # The whole shows/ folder, or exactly each show's ledger, report and dashboard.
    assert "git add shows docs" in commit["run"] or all(
        part in commit["run"] for part in ("shows/*/data/costs.json", "shows/*/COSTS.md", "shows/*/finops-dashboard-*.svg"))
    assert "git pull --rebase origin main" in commit["run"]


def test_published_data_is_committed_and_deployed():
    for name in ("daily-episode.yml", "preview-episode.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "git add shows docs" in text and "actions/deploy-pages" in text


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
    assert set(step["env"]) == {"ELEVENLABS_API_KEY", "VOICE_IDS"} and step["run"] == "python -m engine.tts"
    assert triggers(wf)["push"]["paths"] == ["shows/*/show.yaml"]


def test_spotify_show_url_is_a_show_link(cfg):
    import re
    url = cfg["podcast"]["spotify_url"]
    assert url == "" or re.fullmatch(r"https://open\.spotify\.com/show/[A-Za-z0-9]{22}", url)
    catalog = __import__("json").loads((ROOT / "docs" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["podcast"]["spotify_url"] == url, "regenerate docs/catalog.json after changing spotify_url"


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml") if "schedule:" in p.read_text()))
def test_schedules_are_owned_by_a_github_account(name):
    # Regression (2026-10-21): no scheduled run ever fired, the first real morning had no episode.
    # Every commit used veille@example.invalid, an email linked to no GitHub account, and GitHub
    # does not fire a schedule whose last change was made by such a commit.
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
    if shallow != "false":
        pytest.skip("needs the full git history (CI checks out a single commit)")
    path = f".github/workflows/{name}"
    if git("status", "--porcelain", "--", path).stdout.strip():  # changed: the next commit decides
        email = git("config", "user.email").stdout.strip()
    else:
        email = subprocess.run(["git", "log", "-1", "--format=%ae", "--", path],
                               cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    assert email.endswith("@users.noreply.github.com"), f"last change of {name} authored by {email}"


def test_dependabot_pull_requests_are_merged_only_once_tested():
    # Learning (2026-10-21): Dependabot updates merge on their own, so the guards must hold.
    wf = workflow("dependabot-merge.yml")
    assert triggers(wf) == {"workflow_run": {"workflows": ["Tests"], "types": ["completed"]}}
    job = wf["jobs"]["merge"]
    for guard in ("workflow_run.event == 'pull_request'", "workflow_run.conclusion == 'success'",
                  "workflow_run.actor.login == 'dependabot[bot]'",
                  "workflow_run.head_repository.full_name == github.repository"):
        assert guard in job["if"]
    # Write access: never check out or run the code of the pull request, merge the exact tested commit.
    assert all("uses" not in s for s in job["steps"])
    run = job["steps"][0]["run"]
    assert '--match-head-commit "$SHA"' in run and "--author app/dependabot" in run


def test_daily_run_notifies_the_phone_after_every_real_run():
    wf = workflow("daily-episode.yml")
    notify_step = step(wf, "Notify the phone")
    assert notify_step["if"] == "always() && env.DRY_RUN == 'false'"  # failures too, never dry runs
    assert set(notify_step["env"]) == {"NTFY_TOPIC"} and "python -m engine.notify daily" in notify_step["run"]
    assert step_names(wf)[-1] == "Notify the phone"


@pytest.mark.parametrize("name,step_name", [("daily-episode.yml", "Generate the episode"),
                                            ("preview-episode.yml", "Generate the script")])
def test_generation_can_read_the_accepted_suggestions(name, step_name):
    wf = workflow(name)
    assert wf["permissions"]["issues"] == "read"
    assert step(wf, step_name)["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_issue_forms_match_the_site_links_and_the_suggestion_labels():
    from engine import context
    forms = ROOT / ".github" / "ISSUE_TEMPLATE"
    feedback = yaml.safe_load((forms / "episode-feedback.yml").read_text(encoding="utf-8"))
    suggestion = yaml.safe_load((forms / "topic-suggestion.yml").read_text(encoding="utf-8"))
    assert "episode" in [f.get("id") for f in feedback["body"]]  # the episode page pre-fills it by this id
    assert suggestion["labels"] == [context.SUGGESTION_LABELS[0]]  # "accepted" is added by the owner only
    for form in (feedback, suggestion):
        assert "public" in form["body"][0]["attributes"]["value"]
    config = yaml.safe_load((forms / "config.yml").read_text(encoding="utf-8"))
    assert config["blank_issues_enabled"] is False


def test_local_preview_config_is_not_committed():
    assert git("check-ignore", "-q", ".claude/launch.json").returncode == 0


def test_api_smoke_test_gets_only_the_claude_secrets():
    wf = workflow("api-smoke.yml")
    step_ = step(wf, "Call the real API")
    assert set(step_["env"]) == {"ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"}
    assert step_["run"] == "python tools/api_smoke.py" and wf["permissions"] == {"contents": "read"}
