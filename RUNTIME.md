# Runtime checklist

For whoever helps run the podcast in production. The code is covered offline (see [TESTING.md](TESTING.md)), but several outside services are only **simulated** there, and some have **never run for real**. This page lists each of them, and the actions that verify them, in order, with their cost.

Updated on 2026-10-21, before the first scheduled episode.

## Where things run

Everything runs in GitHub Actions on the public repository; nothing runs on a server.

| Workflow | When | Paid services |
| --- | --- | --- |
| *Daily episode* | weekdays 4:05 Paris (two crons, summer and winter), or by hand | Claude (Sonnet 5.5 + Haiku 5.5), ElevenLabs |
| *Watchdog* | weekdays 5:00 and 6:30 Paris, or by hand | none (it may start *Daily episode*) |
| *Preview episode* | by hand | Claude only |
| *Add a correction* | by hand | none |
| *Publication rehearsal*, *Check voices* | by hand, or on a change of `config.yaml` | ElevenLabs, a few characters |
| *Check Spotify*, *Stats*, *Deploy site*, *Tests*, *Dependabot merge* | schedules, pushes | none |

Secrets (Settings, Secrets and variables, Actions): `ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` (the key is not scoped to a workspace), `ELEVENLABS_API_KEY`, `FORBIDDEN_TERMS` (names never to publish), `EDITORIAL_CONTEXT` (private audience context), `NTFY_TOPIC` (phone notifications). Variable: `SCHEDULE_ENABLED=true` (set it to `false` to pause every schedule).

Rule learnt on 2026-10-21: GitHub only fires the schedules of a workflow whose last change was committed with an email linked to a GitHub account. This repository commits with the owner's noreply address; a test checks it.

## Connectors: simulated, and verified for real or not

| Connector | Used for | In the offline tests | Verified for real | Still to verify |
| --- | --- | --- | --- | --- |
| Claude Sonnet 5.5, research turn | writing the episode, web search, `submit_episode` tool | fake client (`tests/conftest.py`) that enforces the API's rules | ✅ 2026-10-20 and 21; `web_search_20260209` and `cache_control` accepted by the smoke test on 2026-10-22 | the saving on a whole episode (`cache_read_input_tokens` in `data/costs.json`) |
| Claude Sonnet 5.5, light correction | fixing wording without the research | fake client | 🔸 smoke test ✅ 2026-10-22 (the tool is called unforced); never in an episode yet. It used a forced `tool_choice`, which this model refuses (HTTP 400), fixed on 2026-10-22 | a real correction round in an episode |
| Claude Haiku 5.5, fact-check | checking every claim of the facts against its sources | fake answers (`tests/test_factcheck.py`) | 🔸 smoke test ✅ 2026-10-22 (JSON schema output, spoken dates matched); never on a whole episode | cost (expected about one cent), whether its doubts are fair |
| Source pages, fetched by the code | the fact-check's input | network blocked in every test | 🔸 from a Mac: 28 of 29 readable | from a GitHub runner, sites may block datacenter IPs: count the *unverifiable* parts in the run summary |
| ElevenLabs | the two voices, the voice check | fake HTTP (`tests/test_tts.py`), silence in the rehearsal | ✅ 3 episodes | **chapter times**: estimated inside each audio chunk by characters, to check by ear |
| `gh release` | hosting the MP3 | faked | ✅ | — |
| `gh issue list` | listener suggestions labelled `accepted` | faked | ❌ never ran | that it reads the accepted issues (needs `issues: read`) |
| `gh run list`, `gh workflow run` | the watchdog | faked | 🔸 `run list` ✅ (manual watchdog run); it has never started a catch-up | a real catch-up, ideally never needed |
| GitHub Pages | feed, catalog, pages | files written to a temporary folder | ✅ | — |
| ntfy | phone notifications | fake HTTP | ✅ test notifications from GitHub on 2026-10-21 | the first real "Episode out" |
| Spotify embed page | is the episode live, after how long | a saved copy of the page | ✅ | the delay, measured from the first scheduled episode |
| Spotify and Apple, reading the feed | chapters (description timestamps and `podcast:chapters`), transcript (`podcast:transcript`) | feed validated as XML | ❌ | how each app shows them on the first episode that has them |

## Actions, in order

### 1. API smoke test: a few cents (passed on 2026-10-22, rerun after any change to a request)

Checks on the real API the three request shapes that never ran for real.

```bash
gh workflow run api-smoke.yml
```

It runs on GitHub, where the API key is a secret (it is not on the laptops). Locally, export `ANTHROPIC_API_KEY` and `ANTHROPIC_WORKSPACE_ID` and run `python tools/api_smoke.py`. Expected in the log: three `OK` lines (light correction, fact-check, web search). A `FAIL` with an HTTP code points at the request to fix in `podcast/generate.py` or `podcast/factcheck.py`.

### 2. A preview: about $0.50 to $1 of Claude, no ElevenLabs

```bash
gh workflow run preview-episode.yml
```

In the run summary and log, check:
- *Fact-check: N claims checked, D doubt(s), U part(s) unverifiable*: N should be in the tens, U small; read each doubt;
- the cost line: the Claude cost against $1.02 for the first episode, and `cache_read_input_tokens` above zero in `data/costs.json`;
- on the preview page (catalog site, Preview card, then its page): labels, primary sources, topics, no cited site from `sources.avoid` in `config.yaml`;
- no HTTP 400 anywhere.

### 3. The first scheduled episode (the next weekday, 4:05 Paris)

- A phone notification "Episode out" by about 4:30 (or a watchdog notification at 5:00).
- Listen: do the chapters (description in Spotify, or the episode page) land at the right moments?
- Read: labels, topics and their spelling against the existing topics, a follow-up if any (it must quote a real earlier What to watch).
- *Check Spotify* records the delay in `data/spotify.json`.

### 4. Listener suggestions: free

Open an issue with the *Topic suggestion* form, add the `accepted` label (only a maintainer can), then run a preview: the log must say *Listener suggestions: 1 accepted*. Close the issue afterwards.

### 5. A correction, the first time one is needed: free

```bash
gh workflow run correction.yml -f episode_date=YYYY-MM-DD -f text="The episode of October twentieth said ... In fact, ..."
```

Check the episode page, the corrections page and the feed description, then that the next episode reads it (*Corrections read in this episode: 1* in its log).

### 6. Spotify and Apple

On the first episode with chapters: are they shown, in Spotify (from the description) and in Apple Podcasts (from `podcast:chapters`)? Is the transcript (`podcast:transcript`, WebVTT) picked up?

## Working locally

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest                    # offline, about 20 seconds
.venv/bin/python tools/offline_rehearsal.py   # a whole publication on a copy, free
python -m http.server --directory build/rehearsal/docs
```

`python -m podcast.site` rebuilds the catalog and every page from the committed data; `python tools/make_diagrams.py` rebuilds the diagrams. Tests fail when either is stale.

## Known limits

- If GitHub drops every schedule at once, the watchdog is dropped too: the missing phone notification is then the only sign.
- An accepted suggestion can still be edited by its author afterwards: the prompt treats it as data, never as instructions, and the usual checks apply.
- The fact-check reads at most `factcheck.max_chars_per_source` characters of each page, and skips pages it cannot read (reported as unverifiable); a doubt left after the last attempt is reported, not blocking.
