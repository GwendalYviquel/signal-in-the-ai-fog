"""README and TESTING.md: images, paths, workflow names and diagrams must match the repository."""
import re
import sys

import pytest
import yaml

from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import make_diagrams  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
TESTING = (ROOT / "TESTING.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


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


def test_images_exist_in_both_themes():
    # Every diagram is shown through <picture>: a dark version for GitHub's dark theme.
    for src in re.findall(r'srcset="([^"]+)"', README + TESTING):
        assert (ROOT / src).exists(), src
    for src in re.findall(r'<img src="([^"]+)"', TESTING):
        assert (ROOT / src).exists(), src


def test_committed_diagrams_match_the_generator(tmp_path):
    # Edit tools/make_diagrams.py, then run it: the committed SVGs must never be stale.
    make_diagrams.main(tmp_path)
    for fresh in tmp_path.glob("diagram-*.svg"):
        committed = ROOT / "assets" / fresh.name
        assert committed.exists() and committed.read_text() == fresh.read_text(), f"{fresh.name} is stale"


def test_pipeline_diagram_names_the_secrets_actually_used():
    shown = {s for secrets in make_diagrams.SECRETS.values() for s in secrets}
    daily = (WORKFLOWS / "daily-episode.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"secrets\.([A-Z_]+)", daily)) - {"ANTHROPIC_WORKSPACE_ID"}  # optional, not shown
    assert shown == used


def test_episode_diagram_matches_the_prompt():
    prompt = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
    for part, words in make_diagrams.PROMPT_TARGETS.items():
        assert f"about {words} words" in prompt, f"diagram says {part} ~{words} words, the prompt does not"
    drawn = {(p, w) for p, _, w in make_diagrams.EPISODE}
    t = make_diagrams.PROMPT_TARGETS
    assert {("Story of the day", t["story facts"]), ("The read", t["story read"]),
            ("Facts", t["segment facts"]), ("Read", t["segment read"])} <= drawn
    episode_svg = (ROOT / "assets" / "diagram-episode-light.svg").read_text(encoding="utf-8")
    assert f"facts ~{t['story facts']} · read ~{t['story read']} words" in episode_svg


FIT = """() => {
  const svg = document.querySelector('svg');
  const [vx, vy, vw, vh] = svg.getAttribute('viewBox').split(' ').map(Number);
  const problems = [];
  for (const g of svg.querySelectorAll('g.box')) {
    const f = g.querySelector('rect.frame').getBBox();
    for (const t of g.querySelectorAll('text')) {
      const b = t.getBBox();
      if (b.x < f.x + 2 || b.x + b.width > f.x + f.width - 2 || b.y < f.y - 1 || b.y + b.height > f.y + f.height + 1)
        problems.push('text overflows its box: ' + t.textContent);
    }
  }
  for (const el of svg.querySelectorAll('rect, text, path')) {
    if (el.closest('defs')) continue;
    const b = el.getBBox();
    if (b.x < vx - 0.5 || b.y < vy - 0.5 || b.x + b.width > vx + vw + 0.5 || b.y + b.height > vy + vh + 0.5)
      problems.push(el.tagName + ' leaves the drawing ' + (el.textContent || ''));
  }
  return problems;
}"""


def test_every_text_fits_its_box_and_nothing_leaves_the_drawing():
    # Measured in a real browser: diagrams must stay readable and inside the README column.
    sync_api = pytest.importorskip("playwright.sync_api")
    import os
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            problems = {}
            for svg in sorted((ROOT / "assets").glob("diagram-*.svg")):
                page.set_content(svg.read_text(encoding="utf-8"))
                found = page.evaluate(FIT)
                if found:
                    problems[svg.name] = found
            browser.close()
    except Exception as e:
        if isinstance(e, AssertionError) or os.getenv("REQUIRE_BROWSER") == "1":
            raise
        pytest.skip(f"Chromium not available: {e}")
    assert problems == {}


def test_diagrams_are_sized_for_the_readme_column():
    for svg in (ROOT / "assets").glob("diagram-*.svg"):
        head = svg.read_text(encoding="utf-8")[:300]
        assert f'viewBox="0 0 {make_diagrams.W} ' in head and 'role="img"' in head


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
