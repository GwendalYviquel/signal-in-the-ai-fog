"""README and TESTING.md: images, paths, workflow names and diagrams must match the repository."""
import re
import sys

import pytest
import yaml

from conftest import ROOT, SHOW

sys.path.insert(0, str(ROOT / "tools"))
import make_diagrams  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
TESTING = (ROOT / "TESTING.md").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github" / "workflows"


def test_images_exist():
    for src in re.findall(r'<img src="([^"]+)"', README):
        assert (ROOT / src).exists(), src


def tree_paths(tree: str) -> list[str]:
    """Full paths of an indented tree (├── / │   / └──), one level per 4 characters."""
    stack, paths = [], []
    for line in tree.strip().splitlines()[1:]:  # the first line is "."
        m = re.match(r"^((?:│   |    )*)[├└]── (\S+)", line)
        assert m, f"not a tree line: {line!r}"
        depth = len(m.group(1)) // 4
        stack[depth:] = [m.group(2)]
        paths.append("".join(stack))
    return paths


def test_paths_in_the_contents_tree_exist():
    tree = README.split("## Repository contents", 1)[1].split("```")[1]
    paths = tree_paths(tree)
    assert "engine/main.py" in paths and ".github/workflows/tests.yml" in paths
    assert [p for p in paths if not (ROOT / p).exists()] == []


def test_contents_tree_lists_every_module_and_workflow():
    paths = tree_paths(README.split("## Repository contents", 1)[1].split("```")[1])
    for f in list((ROOT / "engine").glob("*.py")) + list(WORKFLOWS.glob("*.yml")):
        if f.name != "__init__.py":
            assert str(f.relative_to(ROOT)) in paths, f"{f.relative_to(ROOT)} is missing from the README tree"


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
    if "secrets[matrix.context_secret]" in daily:  # each show's private context secret
        used.add("EDITORIAL_CONTEXT")
    assert shown == used


def test_episode_diagram_matches_the_prompt():
    prompt = (ROOT / SHOW / "prompt.md").read_text(encoding="utf-8")
    for part, words in make_diagrams.PROMPT_TARGETS.items():
        assert f"about {words} words" in prompt, f"diagram says {part} ~{words} words, the prompt does not"
    drawn = {(p, w) for p, _, w in make_diagrams.EPISODE}
    t = make_diagrams.PROMPT_TARGETS
    assert {("Story of the day", t["story facts"]), ("The read", t["story read"]),
            ("Facts", t["segment facts"]), ("Read", t["segment read"])} <= drawn
    episode_svg = (ROOT / "assets" / "diagram-episode-light.svg").read_text(encoding="utf-8")
    assert f"facts ~{t['story facts']} · read ~{t['story read']} words" in episode_svg


def test_schedule_diagram_matches_the_workflow_and_the_code(cfg):
    import datetime as dt
    from engine import main
    wf = yaml.safe_load((WORKFLOWS / "daily-episode.yml").read_text(encoding="utf-8"))
    s = make_diagrams.SCHEDULE
    assert [x["cron"] for x in wf.get("on", wf.get(True))["schedule"]] == [s["cron"]]
    assert s["publish_at"] == cfg["generation"]["publish_at"]
    days = {"Summer time": dt.date(2026, 7, 15), "Winter time": dt.date(2027, 1, 13)}
    for label, _, offset in s["rows"]:
        day = days[label]
        drawn = make_diagrams.attempt_times(s["cron"], offset)
        due = []
        for hhmm in drawn:  # the diagram's Paris times are the cron's UTC times at that offset
            h, m = (int(v) for v in hhmm.split(":"))
            utc = dt.datetime(day.year, day.month, day.day, h - offset, m, tzinfo=dt.timezone.utc)
            assert f"{utc.astimezone(main.ZoneInfo('Europe/Paris')):%H:%M}" == hhmm, (label, hhmm)
            if main.scheduled_run_is_due(cfg, s["cron"], utc):
                due.append(hhmm)
        assert due and due[0] == min(a for a in drawn if a >= s["publish_at"]), label


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
            for svg in sorted((ROOT / "assets").glob("*.svg")):  # diagrams and FinOps dashboard
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


def test_test_plan_covers_every_test_file():
    areas = {f for *_, files in make_diagrams.TEST_AREAS for f in files}
    assert areas == set(make_diagrams.test_counts()), "add the new test file to an area of the test plan"
    assert make_diagrams.real_runs() >= 1


def test_pipeline_diagram_shows_the_publication_time(cfg):
    # Learning (2026-10-21): the diagram still said 7:15 a day after the run moved to 4:05.
    shown = cfg["generation"]["publish_at"].lstrip("0")
    for theme in ("light", "dark"):
        assert f"weekdays, {shown}" in (ROOT / "assets" / f"diagram-pipeline-{theme}.svg").read_text(encoding="utf-8")
