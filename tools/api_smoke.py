"""API smoke test: the request shapes the pipeline sends, each once, on the real API. Costs a few cents.

The offline suite replaces Claude with a fake that follows the documented rules; this checks that the
real API accepts what the code sends, before an episode depends on it:
1. a light correction (Claude Sonnet 5.5, submit_episode without a forced tool_choice, cache_control);
2. a fact-check (Claude Haiku 5.5, JSON schema output, low effort) on a tiny text and source;
3. the research tools (web_search_20260209, one search, cache_control).
Nothing is published and nothing is written, except one line per check on the terminal.

Usage: gh workflow run api-smoke.yml   (on GitHub, with the repository's secrets)
   or: ANTHROPIC_API_KEY=... python tools/api_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

from engine import costs, factcheck, generate  # noqa: E402
from engine import show as shows  # noqa: E402


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY here: run it on GitHub, where the key is a secret: gh workflow run api-smoke.yml")
        return 2
    cfg = shows.load().cfg  # the show in SHOW, or the first one
    gen = cfg["generation"]
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace} if workspace else None)
    failures = 0

    def report(name, ok, detail):
        nonlocal failures
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")

    try:  # 1. light correction shape
        resp = client.messages.create(
            model=gen["model"], max_tokens=2000, cache_control=generate.CACHE, tools=[generate.SUBMIT_TOOL],
            messages=[{"role": "user", "content": "This is an API smoke test. Call the submit_episode tool once "
                       "with placeholder values: one short sentence per text, three headlines, one segment."}])
        called = any(b.type == "tool_use" and b.name == "submit_episode" for b in resp.content)
        report("light correction", called, f"stop_reason={resp.stop_reason}, tool called={called}")
    except anthropic.APIStatusError as e:
        report("light correction", False, f"HTTP {e.status_code}: {e.message}")

    try:  # 2. fact-check shape
        usage = costs.empty_claude_usage(cfg["factcheck"]["model"])
        claims = factcheck._ask(client, cfg["factcheck"]["model"], "Acme launched Widget 2 on October sixth.",
                                [("https://example.com", "On Oct. 6, Acme released Widget 2 to all customers.")], usage)
        report("fact-check", claims is not None, json.dumps(claims)[:200])
    except anthropic.APIStatusError as e:
        report("fact-check", False, f"HTTP {e.status_code}: {e.message}")

    try:  # 3. research tools
        resp = client.messages.create(
            model=gen["model"], max_tokens=2000, cache_control=generate.CACHE,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 1}],
            messages=[{"role": "user", "content": "Search once for the latest Mistral AI announcement and answer in one line."}])
        searches = getattr(getattr(resp.usage, "server_tool_use", None), "web_search_requests", 0)
        report("web search", resp.stop_reason in ("end_turn", "pause_turn"), f"stop_reason={resp.stop_reason}, "
               f"searches={searches}, cache_write={resp.usage.cache_creation_input_tokens}")
    except anthropic.APIStatusError as e:
        report("web search", False, f"HTTP {e.status_code}: {e.message}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
