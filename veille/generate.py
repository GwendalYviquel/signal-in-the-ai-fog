"""Rédaction du script de veille avec l'API Claude et la recherche web."""
import re
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent


def date_en(d) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def build_user_message(cfg, now, previous_scripts):
    themes = "\n".join(f"- {t['name']}: {t['focus']}" for t in cfg["themes"])
    variant = ""
    if now.weekday() == 0:
        variant = "It is Monday: the What to watch segment covers the whole week, and news since Friday is eligible."
    elif now.weekday() == 4:
        variant = "It is Friday: the story of the day is a deeper trend from the week, with more perspective."
    history = "\n\n---\n\n".join(previous_scripts) if previous_scripts else "None."
    return (
        f"Today is {date_en(now)}. Prepare today's episode.\n"
        f"{variant}\n\n"
        f"Segment themes, in order:\n{themes}\n\n"
        f"Previous episodes (for continuity on stories to watch and to avoid repetition):\n{history}"
    )


def _tag(text, name, required=True):
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    if not m:
        if required:
            raise ValueError(f"Balise <{name}> absente de la réponse du modèle")
        return ""
    return m.group(1).strip()


def clean_for_tts(script: str) -> str:
    script = re.sub(r"\[[^\]]*\]", "", script)          # [Intro], [Sujet 1]...
    script = re.sub(r"[*_#>`]", "", script)              # résidus de markdown
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+", " ", script)
    return re.sub(r"\n{3,}", "\n\n", script).strip()


def parse_response(raw: str) -> dict:
    sources = []
    for line in _tag(raw, "sources", required=False).splitlines():
        if "|" in line:
            title, url = line.rsplit("|", 1)
            sources.append({"title": title.strip(" -"), "url": url.strip()})
    return {
        "title": _tag(raw, "title"),
        "summary": _tag(raw, "summary"),
        "script": clean_for_tts(_tag(raw, "script")),
        "sources": sources,
    }


def generate_episode(cfg, now, previous_scripts):
    gen = cfg["generation"]
    system = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
    system = system.replace("{target_words}", str(gen["target_words"]))
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": build_user_message(cfg, now, previous_scripts)}]
    tools = [{"type": "web_search_20250305", "name": "web_search",
              "max_uses": gen["web_search_max_uses"]}]

    text_parts = []
    for _ in range(6):  # la recherche web peut mettre le tour en pause (pause_turn)
        resp = client.messages.create(model=gen["model"], max_tokens=gen["max_tokens"],
                                      system=system, tools=tools, messages=messages)
        text_parts += [b.text for b in resp.content if b.type == "text"]
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return parse_response("".join(text_parts))
