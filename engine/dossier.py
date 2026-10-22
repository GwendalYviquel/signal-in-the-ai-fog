"""Research dossier: the first of two steps when generation.dossier is on.

1. Research (this module): Claude searches the web and submits a dossier, never an episode. Every
   checkable fact comes with the exact words of the page that states it. The code fetches each page
   and keeps a fact only if its quote is there; a fact from a page that cannot be read (paywall, PDF)
   stays, marked unread, and is still checked by the fact-check before the voices.
2. Writing (generate.py): a second conversation, without web search, writes the episode from the
   dossier alone and may cite only its sources.

The dossier is saved as soon as it is verified (data/dossiers/<date>.json): a failed writing step
is rerun from it without paying for the research again.
"""
from __future__ import annotations

import json
import re

from . import costs, factcheck, locale

_FACT = {"type": "object", "properties": {
    "statement": {"type": "string", "description": "One checkable fact: a figure, date, name or status."},
    "quote": {"type": "string", "description": "The exact words of the page that state it, copied verbatim, 5 to 40 words."},
    "url": {"type": "string", "description": "The page the quote comes from."}},
    "required": ["statement", "quote", "url"]}

SUBMIT_DOSSIER = {
    "name": "submit_dossier",
    "description": "Submit the research dossier of today's episode (not the episode itself).",
    "input_schema": {"type": "object", "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"},
            "theme": {"type": "string", "description": "One of the segment themes, or the closest one."},
            "facts": {"type": "array", "items": _FACT},
            "sources": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "url": {"type": "string"}, "primary": {"type": "boolean"}},
                "required": ["title", "url"]}},
            "context": {"type": "string", "description": "What it means in practice, stages still to come, "
                                                         "open questions: material for the analysis."}},
            "required": ["title", "theme", "facts", "sources", "context"]}},
        "agenda": {"type": "array", "items": {"type": "object", "properties": {
            "date": {"type": "string"}, "text": {"type": "string"}}, "required": ["date", "text"]}}},
        "required": ["items"]},
}

RESEARCH = """Step 1 of 2: research only. Do not write the episode now: a second step will write it from your
dossier alone, without web search, so anything missing from the dossier cannot be said.
- Find the news for every segment theme and a candidate for the story, the number and the follow-up:
  6 to 10 items, enough material for about {target_words} spoken words.
- For each item, list its checkable facts one by one (figures, dates, names, statuses, stage of a text). Each
  fact has the exact words of the page that state it (quote, copied verbatim) and that page's URL. The code
  fetches every page and drops a fact whose quote is not on it: never paraphrase in the quote, never quote a
  page you did not read.
- Prefer primary sources (official texts, decisions, official sites) for figures and dates.
- context: what it changes in practice, the next stages and open questions, as material for the analysis.
- agenda: every upcoming date found, as YYYY-MM-DD.
- Write statement, context, title and agenda in {language}, the language of the episode. A quote stays in
  the language of its page, word for word.
Call submit_dossier once with the whole dossier."""

WRITING = """Step 2 of 2: write today's episode from this research dossier only. You have no web search.
- State only facts from the dossier; the analysis may draw on each item's context.
- The sources of each part are the dossier's sources of the items it uses: never another URL.
- Facts marked "unread" could not be checked against their page: use them only if needed.
- Reach about {target_words} words: develop the analysis rather than adding unsourced facts.
- Write the whole episode in {language}, even where the dossier quotes a page in another language.

<dossier>
{dossier}
</dossier>"""


def _normal(text: str) -> str:
    """Lowercase words only: quotes match across punctuation, typographic apostrophes and spacing."""
    return " ".join(re.sub(r"\W+", " ", text.replace("’", "'").lower()).split())


def verify(dossier: dict, max_chars: int, cache: dict, language: str = "") -> dict:
    """Keeps the facts whose quote is on their page; marks those of unreadable pages as unread.
    Adds dossier["checked"] = {"verified", "unread", "dropped"} counts and the dropped facts."""
    counts, dropped = {"verified": 0, "unread": 0, "dropped": 0}, []
    for item in dossier.get("items", []):
        kept = []
        for fact in item.get("facts", []):
            url = str(fact.get("url", ""))
            page = factcheck.fetch(url, cache, max_chars) if url.startswith("http") else None
            if page is None:
                fact["status"] = "unread"
            elif _normal(fact.get("quote", "")) and _normal(fact["quote"]) in _normal(page):
                fact["status"] = "verified"
            else:
                dropped.append({"item": item.get("title", ""), **fact})
                counts["dropped"] += 1
                continue
            counts[fact["status"]] += 1
            kept.append(fact)
        item["facts"] = kept
    dossier["checked"], dossier["dropped"] = counts, dropped
    if language:  # the writing step translates, but a dossier in the wrong language is worth knowing
        off = [i.get("title", "") for i in dossier.get("items", [])
               if locale.detect(" ".join([str(i.get("context", ""))] + [str(f.get("statement", "")) for f in i.get("facts", [])]))
               not in (None, language)]
        if off:
            print(f"Warning: dossier items not in {locale.NAMES[language]}: {', '.join(off)}")
    print(f"Dossier: {len(dossier.get('items', []))} items, {counts['verified']} facts verified on their page, "
          f"{counts['unread']} unread, {counts['dropped']} dropped (quote not on the page)")
    return dossier


def sources(dossier: dict) -> set[str]:
    return {str(s.get("url", "")) for item in dossier.get("items", []) for s in item.get("sources", [])} | {
        str(f.get("url", "")) for item in dossier.get("items", []) for f in item.get("facts", [])}


def research(client, gen: dict, system: str, request: str, usage: dict, cache_control: dict,
             language: str = "English") -> dict:
    """The research conversation: web search, then one submit_dossier call (asked again once)."""
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": gen["web_search_max_uses"]},
             SUBMIT_DOSSIER]
    messages = [{"role": "user", "content": request + "\n\n" + RESEARCH.replace(
        "{target_words}", str(gen["target_words"])).replace("{language}", language)}]
    for attempt in range(2):
        for _ in range(8):  # web search can pause the turn (pause_turn)
            resp = client.messages.create(model=gen["model"], max_tokens=gen["max_tokens"],
                                          cache_control=cache_control, system=system, tools=tools,
                                          messages=messages)
            costs.add_usage(usage, resp)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "pause_turn":
                break
        call = next((b for b in resp.content if b.type == "tool_use" and b.name == SUBMIT_DOSSIER["name"]), None)
        if call is not None and resp.stop_reason != "max_tokens" and call.input.get("items"):
            return json.loads(json.dumps(call.input))  # a plain copy, saved and modified by verify
        feedback = "No complete dossier submitted: call submit_dossier with every item, keeping quotes short."
        if call is None:
            messages.append({"role": "user", "content": feedback})
        else:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call.id, "content": feedback, "is_error": True}]})
    raise SystemExit("No research dossier after two attempts: nothing written.")


def writing_request(dossier: dict, target_words: int, language: str = "English") -> str:
    shown = {"items": dossier.get("items", []), "agenda": dossier.get("agenda", [])}
    return (WRITING.replace("{target_words}", str(target_words)).replace("{language}", language)
            .replace("{dossier}", json.dumps(shown, ensure_ascii=False, indent=1)))
