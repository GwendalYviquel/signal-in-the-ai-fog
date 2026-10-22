"""The Cloudflare scheduler (scheduler/): its Node tests, and its link with the daily workflow.

Learning (2026-10-22): GitHub's schedules dropped a whole morning of runs; Cloudflare's Cron
Triggers start the daily workflow on time, and the GitHub attempts stay as a backup.
Needs Node.js; skipped without it, unless REQUIRE_NODE=1 (set in the CI tests workflow).
"""
import os
import re
import shutil
import subprocess

import pytest
import yaml

from conftest import ROOT


def test_worker_node_tests_pass():
    node = shutil.which("node")
    if not node:
        if os.getenv("REQUIRE_NODE") == "1":
            pytest.fail("Node.js is required for the scheduler tests")
        pytest.skip("Node.js not installed")
    out = subprocess.run([node, "--test", "scheduler/worker.test.mjs"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-2000:]


def test_worker_targets_this_repository_and_the_inputs_the_workflow_has():
    toml = (ROOT / "scheduler" / "wrangler.toml").read_text(encoding="utf-8")
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout
    repo = re.search(r'REPOSITORY = "([^"]+)"', toml).group(1)
    if remote:
        assert repo.lower() in remote.lower()
    worker = (ROOT / "scheduler" / "worker.js").read_text(encoding="utf-8")
    for name, wf in (("daily-episode.yml", {"dry_run", "as_scheduled", "scheduled"}),
                     ("watchdog.yml", {"test_notification"})):
        flow = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
        inputs = set(flow.get("on", flow.get(True))["workflow_dispatch"]["inputs"])
        assert wf <= inputs, (name, wf - inputs)
        assert name in worker


def test_the_token_is_never_in_the_repository():
    for path in (ROOT / "scheduler").iterdir():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"github_pat_|ghp_[A-Za-z0-9]{20}", text), path.name
    assert subprocess.run(["git", "check-ignore", "-q", "scheduler/.dev.vars"], cwd=ROOT).returncode == 0
