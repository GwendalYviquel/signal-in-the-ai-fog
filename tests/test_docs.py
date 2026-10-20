"""README and TESTING.md: images, paths, workflow names and diagrams must match the repository."""
import re

import pytest
import yaml

from conftest import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")
TESTING = (ROOT / "TESTING.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


def mermaid_blocks(text):
    return re.findall(r"```mermaid\n(.*?)```", text, re.S)


def test_images_exist():
    for src in re.findall(r'<img src="([^"]+)"', README):
        assert (ROOT / src).exists(), src


def test_paths_in_the_contents_tree_exist():
    tree = README.split("## Repository contents", 1)[1].split("```")[1]
    paths = [line.split()[0].rstrip(",") for line in tree.strip().splitlines() if line.strip()]
    missing = [p for p in paths for part in p.split(",") if part and not (ROOT / part).exists()]
    assert paths and missing == []


def test_workflow_names_in_run_modes_exist():
    names = {yaml.safe_load(f.read_text(encoding="utf-8"))["name"] for f in WORKFLOWS.glob("*.yml")}
    modes = README.split("### Run modes", 1)[1].split("\n- ")[0]
    for name in set(re.findall(r"\*([A-Z][a-z]+(?: [a-z]+)*)\*", modes)):
        assert name in names, f"README mentions a workflow named {name!r}"


def test_every_diagram_is_a_known_mermaid_type():
    blocks = mermaid_blocks(README) + mermaid_blocks(TESTING)
    assert len(blocks) == 4
    for block in blocks:
        assert block.split()[0] in ("flowchart", "sequenceDiagram")
        lines = [line.strip() for line in block.splitlines()]
        opened = sum(1 for line in lines if re.match(r"(subgraph|loop|alt|opt|par|critical)\b", line))
        assert opened == lines.count("end"), "every subgraph, loop or alt block must be closed by end"


def test_pipeline_diagram_names_the_secrets_actually_used():
    diagram = mermaid_blocks(README)[0]
    shown = set(re.findall(r"\b([A-Z]+(?:_[A-Z]+)+)\b", diagram))
    daily = (WORKFLOWS / "daily-episode.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"secrets\.([A-Z_]+)", daily)) - {"ANTHROPIC_WORKSPACE_ID"}  # optional, not shown
    assert shown == used


def test_episode_diagram_word_counts_match_the_prompt():
    prompt = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
    diagram = mermaid_blocks(README)[1]
    for n in re.findall(r"~(\d+) words", diagram):
        assert f"about {n} words" in prompt, f"diagram says ~{n} words, the prompt does not"


def test_site_screenshot_can_be_regenerated(tmp_path):
    pytest.importorskip("playwright.sync_api")
    import os
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import screenshot_site
    try:
        out = screenshot_site.screenshot(tmp_path / "catalog.png")
    except Exception as e:  # browser not installed
        if os.getenv("REQUIRE_BROWSER") == "1":
            raise
        pytest.skip(f"Chromium not available: {e}")
    from PIL import Image
    with Image.open(out) as img:
        assert img.format == "PNG" and img.size == (1280, 860)
