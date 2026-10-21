<p align="center">
  <img src="docs/cover.jpg" alt="Signal in the AI Fog cover art" width="220">
</p>

# Signal in the AI Fog

A daily AI news podcast in English, fully generated and published automatically.

Every weekday morning, an episode of about six minutes covers enterprise AI in production: models and vendors, European sovereignty, LLMOps and MLOps platforms, quality and evaluation, regulation, retail and agents. The script is written by Claude from a web search, then read by two ElevenLabs voices. Episodes are distributed through an RSS feed that Spotify and other podcast platforms pick up automatically, and listed on a [catalog site](https://gwendalyviquel.github.io/signal-in-the-ai-fog/).

<p align="center">
  <a href="https://gwendalyviquel.github.io/signal-in-the-ai-fog/">
    <img src="assets/catalog.png" alt="The episode catalog site" width="760">
  </a>
</p>

## How it works

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/diagram-pipeline-dark.svg">
    <img src="assets/diagram-pipeline-light.svg" alt="Pipeline: checks, writing, audio, distribution, with the secrets each stage uses" width="100%">
  </picture>
</p>

A GitHub Action runs four steps:

1. **Writing**: the Claude API, with the web search tool, picks five or six news stories from the last 24 to 72 hours and submits the episode through a `submit_episode` tool, one field per part, following the editorial line in `prompts/system.md`. The request also carries the three previous scripts (continuity, no repetition), the open items of the last What to watch (for a follow-up), the topics already used (so their spelling stays the same) and the listener suggestions the owner accepted. Everything Claude reads, web pages and suggestions alike, is data, never instructions. The code validates the episode (structure, theme order, sources, reliability labels, topics, no markdown, no first person, no forbidden terms, length) and assembles the spoken script with a fixed opening, transitions and sign-off.
2. **Speech synthesis**: two ElevenLabs voices share the episode. The host voice reads the opening, the facts, the transitions and the sign-off; the analyst voice reads every read layer, so the listener hears where analysis begins. A short pause marks each change of voice. Texts are split into chunks, with the neighbouring chunks of the same voice as context to keep the delivery continuous. The start and end of every chunk are recorded, which places the chapters and the timed transcript.
3. **Hosting**: the MP3 is published as a GitHub *release* asset (`episode-YYYY-MM-DD`).
4. **Distribution**: `data/episodes.json` is updated, then the `docs/feed.xml` feed (with chapters and transcript), the `docs/catalog.json` catalog, the episode and topic pages are regenerated and deployed to GitHub Pages. A phone notification says the episode is out, or that the run failed.

### Episode format

Every episode follows the same structure. Each story has two layers: the facts (what happened and its real status: announced, preview or available), read by the host, and a short read (what it means for a platform team or a retailer), read by the analyst and signposted so the listener hears where analysis begins.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/diagram-episode-dark.svg">
    <img src="assets/diagram-episode-light.svg" alt="Episode timeline: host voice for facts, analyst voice for every read, a pause at each change of voice" width="100%">
  </picture>
</p>

On Mondays the episode covers the news since Friday and the week ahead; on Fridays the story of the day steps back to look at a trend from the week.

- **Follow-up** (optional): when an item from a previous What to watch moved forward (a vote happened, a model shipped), about 40 words on what was expected and what happened, with its source, before the number of the day. Never invented: no follow-up when nothing moved.
- **Reliability label** for every story, shown on its page: *confirmed* (the company, authority or a primary source), *reported* (credible press, the facts say who reports it) or *unconfirmed* (a rumour or a single weak source, said plainly, and rare).
- **Topics**: one to three per story, the canonical names of the companies, products, laws or subjects ("Mistral", "EU AI Act"). Each topic has its own page on the site.

### Generation and corrections

The episode is submitted through a tool, so the JSON is always well formed. A wording problem is fixed in a light conversation (the episode and its errors only, much cheaper than replaying the research); anything that needs new content goes back to the research conversation, so a source is never invented.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/diagram-generation-dark.svg">
    <img src="assets/diagram-generation-light.svg" alt="Generation loop: research, submit_episode, validation, light correction or back to research, at most 3 attempts" width="100%">
  </picture>
</p>

### Run modes

Each mode runs part of the pipeline, from a one-word voice check to a full episode.

| Mode | Trigger | Claude | ElevenLabs | Release | RSS feed | Catalog site |
| --- | --- | :---: | :---: | :---: | :---: | :---: |
| Voice check | *Check voices* (manual, and on every change of `config.yaml`) | — | 🔸 one word per voice | — | — | — |
| Dry run | *Daily episode*, `dry_run` (default for manual runs) | ✅ | — | — | — | — |
| Preview | *Preview episode* (manual) | ✅ | — | — | — | 🔸 Preview card |
| Rehearsal | *Publication rehearsal* (manual) | — | 🔸 silence, or two sentences with `with_voice` | 🔸 test, deleted | 🔸 checked, not written | 🔸 checked, not written |
| Publish | *Daily episode* without `dry_run`, or the schedule | ✅ | ✅ | ✅ | ✅ | ✅ |
| Watchdog | *Watchdog*, 5:00 and 6:30 Paris (and by hand) | only through the catch-up it starts | — | — | — | — |
| Offline rehearsal | `python tools/offline_rehearsal.py` (local) | 🔸 fixture | 🔸 silence | — | 🔸 on a copy | 🔸 on a copy |

- **Voice check**: each configured voice reads `Hi.` (3 characters), independently, to prove the API accepts it; candidate voice IDs can be checked without changing the config. It also runs before every real publication, before Claude is called.
- **Dry run**: the script is downloadable from the `episode-script` artifact.
- **Preview**: the real script is published as a **Preview** card on the catalog site, with an audio placeholder. The RSS feed is never touched, so nothing reaches Spotify; a published episode later replaces its preview.
- **Rehearsal**: an MP3 is uploaded as a release, downloaded back from its public URL and checked in the feed and catalog, then the release is deleted. Nothing is published or committed. With `with_voice`, both voices read two short sentences (147 characters) and the sample is kept as an artifact.
- **Catch-up** (`episode_date` option of *Daily episode*): generates a past weekday's episode with that day's news cutoff (4:05 Paris) and only the scripts aired before it; it takes its date in the feed and its description says it is a catch-up. An episode or a release that already exists for that date stops the run before any cost, and stories shared with neighbouring episodes are reported.
- **Force** (`force` option): regenerates today's episode even if it already exists (or on a weekend), replacing the release.
- **Watchdog**: if today's episode is not out at 5:00, it starts the daily run as scheduled (real publication, news cutoff at 4:05) and notifies the phone; at 6:30 it checks again. It waits for a run still going, and stops retrying after two failed runs in a day, since each one pays Claude.
- **Offline rehearsal**: a whole publication on a copy of the repository, free: the real pipeline with Claude answering a fixture (the real script of October 21, with labels, topics and an invented follow-up), ElevenLabs returning silence as long as the text, and no `gh`. It prints the chapters and writes a complete site to `build/rehearsal/docs`, to look at before a change reaches a real episode. A test runs it on every push.

### Schedule

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/diagram-schedule-dark.svg">
    <img src="assets/diagram-schedule-light.svg" alt="Schedule: the run at 4:05 Paris time, about 2 h 40 of margin for Spotify, the 7:00 listen; in summer the 2:05 UTC cron publishes, in winter the 3:05 UTC one" width="100%">
  </picture>
</p>

The daily run starts at **4:05 Paris time, every weekday, public holidays included** (`generation.publish_at`). The episode is online about 15 minutes later, which leaves Spotify close to three hours to pick up the feed before a 7:00 listen. GitHub cron runs in UTC, so the workflow has two cron lines, one for summer time and one for winter time; each run reads the cron line that triggered it (not the clock, so a late start is still recognised) and only the one landing on 4:05 in Paris goes on. Scheduled runs only start once the `SCHEDULE_ENABLED` repository variable is `true`:

```
gh variable set SCHEDULE_ENABLED --body true    # --body false to pause
```

A *Watchdog* workflow checks at **5:00 and 6:30 Paris time** that today's episode is out, and starts the catch-up if not (see Run modes). It is a separate workflow with its own schedule, so one dropped or failed daily run is caught before 7:00. If GitHub drops every schedule at once, as it did on October 21 when no commit was linked to a GitHub account, only the phone notification of a missing episode is missing too: check that it arrives each morning.

**Phone notifications** use [ntfy](https://ntfy.sh): install the ntfy app, subscribe to a hard-to-guess topic name, and store that name as the `NTFY_TOPIC` secret. The daily run notifies when an episode is out (with its page) or when it fails, and the watchdog when it starts a catch-up, waits for a late run or gives up. Without the secret, nothing is sent and nothing fails. To check the secret, run *Watchdog* by hand with `test_notification`: it only sends a test.

A *Check Spotify* workflow runs every 15 minutes on weekday mornings (and by hand): it reads Spotify's public embed page of the show, compares its latest episode with ours, and records in `data/spotify.json` when each episode was first seen live and how many minutes after publication, to confirm the margin before 7:00.

## Repository contents

```
.
├── config.yaml                     podcast, models, voices, themes, schedule, prices
├── prompts/
│   └── system.md                   editorial line, episode format, writing rules for the voice
├── podcast/                        the pipeline: python -m podcast.main
│   ├── main.py                     run modes, guards, catch-ups
│   ├── generate.py                 script writing with Claude and web search, validation
│   ├── context.py                  open items, known topics, accepted listener suggestions
│   ├── tts.py                      ElevenLabs speech, two voices, voice check, chunk timings
│   ├── chapters.py                 chapters and timed transcript (WebVTT)
│   ├── publish.py                  MP3 as a GitHub release (gh CLI)
│   ├── feed.py                     RSS feed for Spotify and Apple Podcasts
│   ├── catalog.py                  data of the catalog site
│   ├── site.py                     episode and topic pages, sitemap
│   ├── notify.py                   phone notifications (ntfy)
│   ├── watchdog.py                 morning check, catch-up if the episode is missing
│   ├── costs.py                    cost tracking: Claude tokens, ElevenLabs characters
│   ├── finops.py                   FinOps dashboard, rebuilt after every run
│   ├── stats.py                    download counts of the episodes
│   ├── spotify.py                  is the latest episode live on Spotify
│   ├── rehearsal.py                publication rehearsal
│   └── drawing.py                  drawing helpers shared by the diagrams and the dashboard
├── data/
│   ├── episodes.json               published episodes, source of the feed
│   ├── scripts/                    one script per published episode, and its structured version (JSON)
│   ├── previews.json               preview episodes (catalog only); scripts in data/previews/
│   ├── costs.json                  what every run consumed
│   └── stats.json                  one snapshot of download counts a day
├── docs/                           GitHub Pages: catalog page, feed.xml, catalog.json, cover.jpg
│   ├── episodes/                   one page per episode, with its transcript (.vtt) and chapters (.json)
│   └── topics/                     one page per topic, and the list of topics
├── assets/                         images and diagrams of the README, light and dark
├── tools/
│   ├── make_cover.py               cover art
│   ├── make_diagrams.py            diagrams of the README
│   ├── offline_rehearsal.py        a whole publication on a copy, at no cost
│   └── screenshot_site.py          screenshot of the catalog site
├── tests/                          offline test suite (pytest); fixtures/ holds a real episode
├── .github/ISSUE_TEMPLATE/         feedback and topic suggestion forms
├── .github/workflows/
│   ├── daily-episode.yml           the daily episode: schedule, dry run, catch-up
│   ├── preview-episode.yml         script only, published to the catalog
│   ├── check-voices.yml            one word per ElevenLabs voice
│   ├── rehearsal.yml               publication rehearsal, release deleted afterwards
│   ├── check-spotify.yml           episode live on Spotify, and after how long
│   ├── stats.yml                   daily download counts
│   ├── watchdog.yml                5:00 and 6:30 check, catch-up if the episode is missing
│   ├── deploy-site.yml             site deployment when docs/ changes
│   ├── dependabot-merge.yml        Dependabot security updates merged once tested
│   └── tests.yml                   test suite on every push
├── COSTS.md                        costs report
├── STATS.md                        downloads report
└── TESTING.md                      test suite and journal of real runs
```

### Configuration

- `config.yaml` holds everything editorial or tunable: title, description, language, Claude model, target length, ElevenLabs voice and model, and the list of themes with their scope. Themes can be changed at any time; they are used in segment order.
- `prompts/system.md` defines the tone, the audience, the source-checking rules, the reliability labels, topics and follow-ups, and the fields of the `submit_episode` tool.
- The `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` keys are stored as GitHub Actions secrets. No secret is committed.
- The optional `FORBIDDEN_TERMS` secret is a comma-separated list of names that must never be spoken or published (topics included); an episode containing one is rejected.
- The optional `NTFY_TOPIC` secret is the ntfy topic of the phone notifications.

## Episode catalog

The GitHub Pages home page (`docs/index.html`) lists every episode as a card: cover image, status (Published or Preview), date, duration, title, summary, headlines, themes, audio player (or a placeholder for previews), Spotify link, script and sources. Episodes can be searched (titles, summaries, scripts) and filtered by theme, and each one has its own link (`#YYYY-MM-DD`). Every card and the header have a "Listen on Spotify" button: it opens `podcast.spotify_url` from `config.yaml` once set, and a Spotify search for the podcast until then.

Each episode also has **its own page** (`docs/episodes/YYYY-MM-DD.html`), linked from its card and from its description in podcast apps: summary, player, chapters that jump the player to that moment, then every story with its reliability label, its facts and its read, its topics and its sources, the follow-up, the number of the day, What to watch and the question. Episodes from before October 22 show their script instead. Pages carry a canonical link, Open Graph tags and schema.org `PodcastEpisode` data, and `docs/sitemap.xml` lists them all, so search engines can index every episode.

**Topic pages** (`docs/topics/`) gather everything said about a company, product, law or subject, as a timeline, newest first, with the label of each story; `docs/topics/index.html` lists every topic by number of mentions. The topics of the first three episodes were tagged by hand.

Pages are generated by `podcast/site.py` after every preview and publication; `python -m podcast.site` rebuilds the catalog and every page from the committed data. Every text is escaped, since titles, topics and sources come from the web.

The site is published at https://gwendalyviquel.github.io/signal-in-the-ai-fog/ by `.github/workflows/deploy-site.yml` whenever `docs/` changes, and by the daily workflow after each episode. Hosting is free (GitHub Pages for the site and feed, GitHub releases for the audio).

## Listener feedback

Every episode page has two buttons that open a GitHub issue form: **Give feedback** (the episode date filled in, useful or not, what worked) and **Suggest a topic**. A free GitHub account is needed, and the forms say plainly that issues are public.

Suggestions reach Claude only once the owner adds the **accepted** label, which only a maintainer can do: the daily run then passes the open, accepted suggestions to Claude (at most ten, 300 characters each) as data, to cover when there is real news about them. Close a suggestion to stop it. An accepted issue can still be edited by its author afterwards, so the prompt treats it, like every web page, as data and never as instructions, and the usual checks (forbidden terms, sources, format) still apply to the episode.

## Tests

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/diagram-testplan-dark.svg">
    <img src="assets/diagram-testplan-light.svg" alt="Test plan: every area of the offline suite with its test files, the mutation checks and the real runs" width="100%">
  </picture>
</p>

```
pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium   # for the catalog site tests
python -m pytest
python tools/offline_rehearsal.py       # a whole publication on a copy, free; site in build/rehearsal/docs
```

The suite runs offline: Claude, ElevenLabs and `gh` are replaced by fakes, and the pipeline runs on a temporary copy of the data. It covers episode validation, the generation loop (tool submission, correction rounds, truncated responses), script assembly, speech chunking and retries, the RSS feed, the catalog, every run mode end to end, the cover art (platform specs, every word drawn, even without the DejaVu font), the catalog page in a headless browser (cards, Spotify button, search, filters, stats, deep links, HTML injection, mobile layout), the consistency between the prompt and the checks (an episode written exactly to the prompt must pass), the workflows (triggers, concurrency, dry-run guards), the chapters and timed transcript, the episode and topic pages (escaping, labels, feedback links, sitemap, stale pages), the watchdog and the notifications, the offline rehearsal end to end, and repository hygiene (secrets wired into workflows, private files ignored, no forbidden term in tracked files when `FORBIDDEN_TERMS` is set, scheduled workflows last changed by a commit linked to a GitHub account). Every bug met in a real run gets a regression test.

[TESTING.md](TESTING.md) details the suite and keeps a journal of every real run, successful or not, with what each one taught us.

Tests run on every push (`.github/workflows/tests.yml`) and before every generation in the daily and preview workflows, so a broken commit never produces an episode.

## FinOps

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/finops-dashboard-dark.svg">
    <img src="assets/finops-dashboard-light.svg" alt="FinOps dashboard: Claude and ElevenLabs this month, cost per published episode, month projection, and spend per day over 30 days" width="100%">
  </picture>
</p>

Every run records what it consumed, failed runs and dry runs included: Claude tokens and web searches, with a dollar estimate from the prices in `config.yaml`, and ElevenLabs characters (its credits). The dashboard above and [COSTS.md](COSTS.md) are rebuilt and committed after each run, and each run's GitHub summary shows its own cost.

- **One episode** costs about **$1 of Claude** (mostly the web search results it reads) and **5,000 ElevenLabs credits**; a month of weekdays, about **$20 and 110,000 credits**.
- **Before paying for anything**, the voice check (3 characters per voice) and the duplicate guards stop a run that would fail; wording corrections go to a light conversation without the research.
- **Never paid twice**: an episode already published is skipped, an orphan release stops the run, and nothing is published on weekends.
- **Free**: hosting (GitHub Pages and releases), the Spotify check, the download stats and the CI.
- **Audience**: downloads of each episode in [STATS.md](STATS.md) and on the catalog site; Spotify plays in Spotify for Creators.

## Transparency

The opening of each episode and its description state that the content is written and read by AI, in line with the AI Act's labelling obligations for AI-generated content. Each episode's sources are listed in its description.
