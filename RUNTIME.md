# Runtime checklist

For whoever helps run the podcast in production. The code is covered offline (see [TESTING.md](TESTING.md)), but several outside services are only **simulated** there, and some have **never run for real**. This page lists each of them, and the actions that verify them, in order, with their cost.

Updated on 2026-10-22: the repository is now an engine running several shows (`shows/<slug>/`); two French weekly shows are in preparation.

## Where things run

Everything runs in GitHub Actions on the public repository; nothing runs on a server.

| Workflow | When | Paid services |
| --- | --- | --- |
| *Daily episode* | started at 4:05 Paris by the Cloudflare scheduler (`scheduler/`), retried at 4:35 and 5:05; GitHub attempts every 15 min as a backup; or by hand | Claude (Sonnet 5.5 + Haiku 5.5), ElevenLabs |
| *Watchdog* | weekdays 5:11 and 6:41 Paris, or by hand | none (it may start *Daily episode*) |
| *Preview episode* | by hand | Claude only |
| *Add a correction* | by hand | none |
| *Publication rehearsal*, *Check voices* | by hand, or on a change of a `show.yaml` | ElevenLabs, a few characters |
| *Check Spotify*, *Stats*, *Deploy site*, *Tests*, *Dependabot merge* | schedules, pushes | none |

**Cloudflare Worker** `signal-in-the-ai-fog-scheduler` (Cloudflare dashboard, Workers): its only secret is `GITHUB_TOKEN`, a fine-grained GitHub token for this repository with *Actions: read and write*. **It expires: renew it before its date** (GitHub, Settings, Developer settings, Fine-grained tokens), then `cd scheduler && npx wrangler secret put GITHUB_TOKEN`. An expired token shows as `GitHub answered 401` in the worker's logs (Cloudflare dashboard, the worker, Logs), and only the GitHub attempts are left. Deploy a change: `cd scheduler && npx wrangler deploy`, from a terminal that has `CLOUDFLARE_API_TOKEN` (a Cloudflare API token, template *Edit Cloudflare Workers*; the browser login failed on this Mac). End-to-end check, free: deploy with `--var "TEST_CRON:M H * * *" --triggers "5,35 2,3 * * 1-5" --triggers "5 4 * * 1-5" --triggers "M H * * *"` for a UTC time **at least 15 minutes ahead** (a new cron takes time to propagate); at that time a test notification arrives; then deploy again without the options.

Secrets (Settings, Secrets and variables, Actions): `ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` (the key is not scoped to a workspace), `ELEVENLABS_API_KEY`, `FORBIDDEN_TERMS` (names never to publish, every show), `EDITORIAL_CONTEXT` (private audience context of the first show; each other show has its own, `EDITORIAL_CONTEXT_<SLUG>`, optional), `NTFY_TOPIC` (phone notifications). Variable: `SCHEDULE_ENABLED=true` (set it to `false` to pause every schedule).

Rule learnt on 2026-10-21: GitHub only fires the schedules of a workflow whose last change was committed with an email linked to a GitHub account. This repository commits with the owner's noreply address; a test checks it.

## Connectors: simulated, and verified for real or not

| Connector | Used for | In the offline tests | Verified for real | Still to verify |
| --- | --- | --- | --- | --- |
| Claude Sonnet 5.5, research turn | writing the episode, web search, `submit_episode` tool | fake client (`tests/conftest.py`) that enforces the API's rules | ✅ 2026-10-20 and 21; `web_search_20260209` and `cache_control` on a forced preview on 2026-10-21: **$0.45 against $1.02**, 205k tokens read from the cache | that the saving holds over several episodes |
| Claude Sonnet 5.5, light correction | fixing wording without the research | fake client | 🔸 smoke test ✅ 2026-10-22 (the tool is called unforced); never in an episode yet. It used a forced `tool_choice`, which this model refuses (HTTP 400), fixed on 2026-10-22 | a real correction round in an episode |
| Claude Haiku 5.5, fact-check | checking every claim of the facts against its sources | fake answers (`tests/test_factcheck.py`) | ✅ smoke test, then a forced preview on 2026-10-21: 36 claims, 8 doubts then 1, under one cent | whether its doubts stay fair (statements of absence are now skipped) |
| Source pages, fetched by the code | the fact-check's input | network blocked in every test | ✅ from a GitHub runner on the forced preview: no part unverifiable | from a GitHub runner, sites may block datacenter IPs: count the *unverifiable* parts in the run summary |
| ElevenLabs, French voices | the two French shows | stand-in voices in the offline rehearsal | ✅ 2026-10-22: four library voices accepted by *Check voices* (12 characters); not heard yet | HR: Geneviève (host), Pierre (analyst); accounting: Anaïs (host), Nicolas (analyst). Chosen from their descriptions; the first episodes are their first real test |
| ElevenLabs | the two voices, the voice check | fake HTTP (`tests/test_tts.py`), silence in the rehearsal | ✅ 3 episodes | **chapter times**: estimated inside each audio chunk by characters, to check by ear |
| `gh release` | hosting the MP3 | faked | ✅ | — |
| `gh issue list` | listener suggestions labelled `accepted` | faked | ❌ never ran | that it reads the accepted issues (needs `issues: read`) |
| `gh run list`, `gh workflow run` | the watchdog | faked | 🔸 `run list` ✅ (manual watchdog run); it has never started a catch-up | a real catch-up, ideally never needed |
| Cloudflare Cron Triggers | start the daily workflow on time | Node tests of the worker (`scheduler/worker.test.mjs`): every weekday of two years, the request, the test cron, failures | ✅ 2026-10-22: a test cron started a workflow through the token, 48 s after its time | a first morning started by it |
| GitHub Pages | feed, catalog, pages | files written to a temporary folder | ✅ | — |
| ntfy | phone notifications | fake HTTP | ✅ test notifications from GitHub on 2026-10-21 | the first real "Episode out" |
| Spotify embed page | is the episode live, after how long | a saved copy of the page | ✅ | the delay, measured from the first scheduled episode |
| Spotify and Apple, reading the feed | chapters (description timestamps and `podcast:chapters`), transcript (`podcast:transcript`) | feed validated as XML | ❌ | how each app shows them on the first episode that has them |

## Several shows

- Every workflow takes the show from `SHOW` (a `show` input on manual workflows, default `signal-in-the-ai-fog`). Scheduled attempts (GitHub or Cloudflare) run **every scheduled show**, one at a time; each publishes only on its own days. A show with `generation.scheduled: false` is never run by a schedule or the watchdog.
- Per-show secrets: the private context `EDITORIAL_CONTEXT_<SLUG>` (optional); every other secret is shared.
- Costs: a weekly French episode is about **7,000 ElevenLabs characters** (offline rehearsal), so the two French shows add about **60,000 characters a month** and about $4 of Claude, on top of the first show's 110,000 characters.
- The two French shows wait for: their names (the titles in `show.yaml` are proposals), their voices, their identity in the feed (owner name and email), a preview each, then `scheduled: true` and a Spotify submission.

## Actions, in order

### 1. API smoke test: a few cents (passed on 2026-10-22, rerun after any change to a request)

Checks on the real API the three request shapes that never ran for real.

```bash
gh workflow run api-smoke.yml
```

It runs on GitHub, where the API key is a secret (it is not on the laptops). Locally, export `ANTHROPIC_API_KEY` and `ANTHROPIC_WORKSPACE_ID` and run `python tools/api_smoke.py`. Expected in the log: three `OK` lines (light correction, fact-check, web search). A `FAIL` with an HTTP code points at the request to fix in `engine/generate.py` or `engine/factcheck.py`.

### 2. A preview: about $0.50 of Claude in one step, $1 to $2 in two steps (French shows), no ElevenLabs (done on 2026-10-21 and 2026-10-22, forced)

```bash
gh workflow run preview-episode.yml
```

Once the day's episode is out, the preview stops before any cost; add `-f force=true` to run it anyway (nothing reaches the site, since the published episode takes precedence; remove the preview from the show's `data/previews.json` and `data/previews/` afterwards). In the run summary and log, check:
- *Fact-check: N claims checked, D doubt(s), U part(s) unverifiable*: N should be in the tens, U small; read each doubt;
- the cost line: the Claude cost against $1.02 for the first episode, and `cache_read_input_tokens` above zero in `data/costs.json`;
- on the preview page (catalog site, Preview card, then its page): labels, primary sources, topics, no cited site from `sources.avoid` in the `show.yaml`;
- no HTTP 400 anywhere.

### 3. The first scheduled episode (the next weekday, 4:05 Paris)

- A phone notification "Episode out" by about 4:30 (or a watchdog notification at 5:11). None by 5:00: start the run by hand, `gh workflow run daily-episode.yml -f dry_run=false -f as_scheduled=true`.
- Listen: do the chapters (description in Spotify, or the episode page) land at the right moments?
- Read: labels, topics and their spelling against the existing topics, a follow-up if any (it must quote a real earlier What to watch).
- *Check Spotify* records the delay in `shows/signal-in-the-ai-fog/data/spotify.json`.

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

`python -m engine.site` rebuilds the catalog and every page from the committed data; `python tools/make_diagrams.py` rebuilds the diagrams. Tests fail when either is stale.

## Known limits

- The Cloudflare token expires (see above). GitHub's schedules are best effort. On October 21 the morning run started five hours late; on October 22 no scheduled run of the morning started at all (daily, watchdog, Spotify check). Attempts every 15 minutes make one dropped run harmless, not a whole morning dropped: then the missing "Episode out" notification is the only sign. If it happens again, an external scheduler (for example cron-job.org calling the `workflow_dispatch` API with a token limited to this repository) is the next step.
- An accepted suggestion can still be edited by its author afterwards: the prompt treats it as data, never as instructions, and the usual checks apply.
- The fact-check reads at most `factcheck.max_chars_per_source` characters of each page, and skips pages it cannot read (reported as unverifiable); a doubt left after the last attempt is reported, not blocking.
