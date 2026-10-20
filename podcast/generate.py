"""Episode script writing with the Claude API and web search.

The model submits the episode through the submit_episode tool (one field per part
of the episode); this module validates it and assembles the spoken script with the
fixed opening, transitions and sign-off, so every episode follows the same structure.
"""
import os
import re
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent

# Word ranges per part: outside them is a warning, not an error (models miscount).
LENGTHS = {
    "story facts": (100, 170), "story read": (80, 150),
    "segment facts": (30, 70), "segment read": (20, 55),
    "number_of_the_day": (15, 50), "what_to_watch": (35, 90), "question": (12, 40),
}
SEGMENTS_MIN, SEGMENTS_MAX = 2, 5
HEADLINE_MAX_WORDS = 8
FIRST_PERSON = re.compile(r"\b(we|We|our|Our|ours|us)\b")  # "US" (country) stays allowed
UNSPEAKABLE = re.compile(r"[*_#`\[\]<>{}]|https?://")


def date_en(d) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def build_user_message(cfg, now, previous_scripts):
    themes = "\n".join(f"- {t['name']}: {t['focus']}" for t in cfg["themes"])
    variant = ""
    if now.weekday() == 0:
        variant = "It is Monday: the What to watch part covers the whole week, and news since Friday is eligible."
    elif now.weekday() == 4:
        variant = "It is Friday: the story of the day is a deeper trend from the week, with more perspective."
    history = "\n\n---\n\n".join(previous_scripts) if previous_scripts else "None."
    return (
        f"Today is {date_en(now)}. Prepare today's episode.\n"
        f"{variant}\n\n"
        f"Segment themes, in order:\n{themes}\n\n"
        f"Previous episodes (for continuity on stories to watch and to avoid repetition):\n{history}"
    )


def words(text: str) -> int:
    return len(text.split())


def clean_for_tts(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"[*_#>`]", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_SOURCE = {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
           "required": ["title", "url"]}
_STORY = {"type": "object", "properties": {
    "theme": {"type": "string"}, "facts": {"type": "string"}, "read": {"type": "string"},
    "sources": {"type": "array", "items": _SOURCE}}, "required": ["theme", "facts", "read", "sources"]}

# The episode is returned through this tool: the API guarantees well-formed JSON input.
SUBMIT_TOOL = {
    "name": "submit_episode",
    "description": "Submit today's episode once the research is done. Call it exactly once per attempt.",
    "input_schema": {"type": "object", "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "headlines": {"type": "array", "items": {"type": "string"}},
        "story_of_the_day": _STORY,
        "segments": {"type": "array", "items": _STORY},
        "number_of_the_day": {"type": "object", "properties": {"text": {"type": "string"}, "source": _SOURCE},
                              "required": ["text", "source"]},
        "what_to_watch": {"type": "string"},
        "question": {"type": "string"},
    }, "required": ["title", "summary", "headlines", "story_of_the_day", "segments",
                    "number_of_the_day", "what_to_watch", "question"]},
}


def _private_context() -> str:
    # Kept out of the public repo: EDITORIAL_CONTEXT secret, or a local gitignored file.
    local = ROOT / "private" / "editorial_context.md"
    text = os.getenv("EDITORIAL_CONTEXT") or (local.read_text(encoding="utf-8") if local.exists() else "")
    return text.strip()


def _forbidden_terms() -> list[str]:
    # Comma-separated, from a secret: the list itself must not appear in the public repo.
    return [t.strip() for t in os.getenv("FORBIDDEN_TERMS", "").split(",") if t.strip()]


def _spoken_parts(ep: dict) -> list[tuple[str, str]]:
    parts = [("headline", h) for h in ep.get("headlines", [])]
    story = ep.get("story_of_the_day", {})
    parts += [("story facts", story.get("facts", "")), ("story read", story.get("read", ""))]
    for s in ep.get("segments", []):
        parts += [("segment facts", s.get("facts", "")), ("segment read", s.get("read", ""))]
    parts += [("number_of_the_day", ep.get("number_of_the_day", {}).get("text", "")),
              ("what_to_watch", ep.get("what_to_watch", "")), ("question", ep.get("question", ""))]
    return parts


def _has_source(sources) -> bool:
    return any(str(s.get("url", "")).startswith("http") for s in sources or [])


def validate(ep: dict, cfg: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block the episode, warnings are only logged."""
    errors, warnings = [], []
    for key in ("title", "summary", "headlines", "story_of_the_day", "segments",
                "number_of_the_day", "what_to_watch", "question"):
        if not ep.get(key):
            errors.append(f"Missing field: {key}")
    if errors:
        return errors, warnings

    if len(ep["headlines"]) != 3:
        errors.append(f"Expected 3 headlines, got {len(ep['headlines'])}")
    for h in ep["headlines"]:
        if "," in h or words(h) > HEADLINE_MAX_WORDS:
            errors.append(f"Headline must be at most {HEADLINE_MAX_WORDS} words with no comma: {h!r}")

    themes = [t["name"] for t in cfg["themes"]]
    story = ep["story_of_the_day"]
    if story.get("theme") not in themes:
        errors.append(f"Unknown theme for the story of the day: {story.get('theme')!r}")
    if not _has_source(story.get("sources")):
        errors.append("The story of the day has no source")

    segs = ep["segments"]
    if not SEGMENTS_MIN <= len(segs) <= SEGMENTS_MAX:
        errors.append(f"Expected {SEGMENTS_MIN} to {SEGMENTS_MAX} segments, got {len(segs)}")
    order = [themes.index(s["theme"]) for s in segs if s.get("theme") in themes]
    if len(order) != len(segs):
        errors.append(f"Unknown segment theme; use exactly: {', '.join(themes)}")
    elif order != sorted(set(order)):
        errors.append("Segments must follow the theme order given, each theme at most once")
    for s in segs:
        if not (s.get("facts") and s.get("read")):
            errors.append(f"Segment {s.get('theme')!r} needs both facts and read")
        if not _has_source(s.get("sources")):
            errors.append(f"Segment {s.get('theme')!r} has no source")

    forbidden = _forbidden_terms()
    published = [("title", ep["title"]), ("summary", ep["summary"])]
    published += [("source title", s["title"]) for s in collect_sources(ep)]
    for name, text in published:  # shown in the RSS feed, never spoken
        for term in forbidden:
            if term.lower() in text.lower():
                errors.append(f"Forbidden term in {name}")
    for name, text in _spoken_parts(ep):
        if m := UNSPEAKABLE.search(text):
            around = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
            errors.append(f"Markdown, brackets or links in {name} ({m.group(0)!r} in \"...{around}...\"): "
                          "spoken text must not contain * _ # ` [ ] < > { } or URLs")
        if m := FIRST_PERSON.search(text):
            errors.append(f"First person {m.group(0)!r} in {name}")
        for term in forbidden:
            if term.lower() in text.lower():
                errors.append(f"Forbidden term in {name}")
        if name in LENGTHS:
            lo, hi = LENGTHS[name]
            if not lo <= words(text) <= hi:
                warnings.append(f"{name}: {words(text)} words (expected {lo} to {hi})")

    if errors:
        return errors, warnings
    target = cfg["generation"]["target_words"]
    total = words(assemble(ep, cfg, None))
    if not 0.75 * target <= total <= 1.25 * target:
        errors.append(f"Episode is {total} words, target is about {target}")
    return errors, warnings


def assemble(ep: dict, cfg: dict, now) -> str:
    """Spoken script: fixed opening, transitions and sign-off around the model's texts."""
    title = cfg["podcast"]["title"]
    day = f"{now:%A}, {now:%B} {now.day}" if now else "today"
    h = [x.strip().rstrip(".,;:!") for x in ep["headlines"]]
    see_you = "on Monday" if now and now.weekday() == 4 else "tomorrow"
    story = ep["story_of_the_day"]
    parts = [
        f"Good morning, it's {day}. This is {title}, your daily briefing on enterprise AI "
        f"in production, written and read by AI. Today: {h[0]}, {h[1]}, and {h[2]}.",
        "First, the story of the day.",
        story["facts"], story["read"],
    ]
    for s in ep["segments"]:
        parts += [f"Next, {s['theme']}.", s["facts"], s["read"]]
    parts += [
        "The number of the day.", ep["number_of_the_day"]["text"],
        "What to watch.", ep["what_to_watch"],
        "And a question for your team.", ep["question"],
        f"That's it for today. Sources are in the episode description. "
        f"This was {title}. See you {see_you}.",
    ]
    return clean_for_tts("\n\n".join(parts))


def collect_sources(ep: dict) -> list[dict]:
    found = list(ep["story_of_the_day"].get("sources", []))
    for s in ep["segments"]:
        found += s.get("sources", [])
    found.append(ep["number_of_the_day"].get("source") or {})
    seen, unique = set(), []
    for s in found:
        url = str(s.get("url", ""))
        if url.startswith("http") and url not in seen:
            seen.add(url)
            unique.append({"title": s.get("title") or url, "url": url})
    return unique


def _ask(client, gen, system, tools, messages):
    """Run the turn until the model stops; return the submit_episode call, if any."""
    for _ in range(8):  # web search can pause the turn (pause_turn)
        resp = client.messages.create(model=gen["model"], max_tokens=gen["max_tokens"],
                                      system=system, tools=tools, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "pause_turn":
            break
    call = next((b for b in resp.content if b.type == "tool_use" and b.name == SUBMIT_TOOL["name"]), None)
    return call, resp.stop_reason == "max_tokens"


def generate_episode(cfg, now, previous_scripts):
    gen = cfg["generation"]
    system = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
    system = system.replace("{target_words}", str(gen["target_words"]))
    if context := _private_context():
        system += f"\n\n## Private editorial context (never mention or quote)\n{context}\n"
    # Only needed for an API key that is not scoped to a workspace.
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace} if workspace else None)
    messages = [{"role": "user", "content": build_user_message(cfg, now, previous_scripts)}]
    tools = [{"type": "web_search_20250305", "name": "web_search",
              "max_uses": gen["web_search_max_uses"]}, SUBMIT_TOOL]

    attempts = 3  # up to two correction rounds if the episode is invalid
    for attempt in range(attempts):
        call, truncated = _ask(client, gen, system, tools, messages)
        if truncated:
            print(f"Response cut off at max_tokens ({gen['max_tokens']}): consider raising generation.max_tokens")
            errors, warnings = ["Your response was cut off by the output length limit before the episode was "
                                "complete. Submit it again, keeping every text within its target length."], []
        elif call is None:
            errors, warnings = ["No episode submitted: call the submit_episode tool."], []
        else:
            ep = call.input
            try:
                errors, warnings = validate(ep, cfg)
            except (KeyError, TypeError, AttributeError, IndexError) as e:
                errors, warnings = [f"Malformed episode: {e!r}"], []
        for w in warnings:
            print(f"Warning: {w}")
        if not errors:
            break
        print(f"Invalid episode (attempt {attempt + 1}):\n- " + "\n- ".join(errors))
        if attempt == attempts - 1:
            raise SystemExit("The episode is still invalid after the correction rounds: nothing published.")
        feedback = ("The episode does not meet the requirements:\n- " + "\n- ".join(errors)
                    + "\nFix these points and call submit_episode again with the full corrected episode.")
        if call is None:
            messages.append({"role": "user", "content": feedback})
        else:  # every tool call, even a truncated one, must be answered with a tool_result
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call.id, "content": feedback, "is_error": True}]})

    return {
        "title": ep["title"].strip(),
        "summary": ep["summary"].strip(),
        "script": assemble(ep, cfg, now),
        "sources": collect_sources(ep),
        "structured": ep,
    }
