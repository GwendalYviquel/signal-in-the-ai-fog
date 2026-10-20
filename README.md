# Signal in the AI Fog

A daily AI news podcast in English, fully generated and published automatically.

Every weekday morning, an episode of about six minutes covers enterprise AI in production: models and vendors, European sovereignty, LLMOps and MLOps platforms, quality and evaluation, regulation, retail and agents. The script is written by Claude from a web search, then read by an ElevenLabs voice. Episodes are distributed through an RSS feed that Spotify and other podcast platforms pick up automatically.

## How it works

A GitHub Action runs four steps:

1. **Writing**: the Claude API, with the web search tool, picks five or six news stories from the last 24 to 72 hours and returns them as JSON, one field per part of the episode, following the editorial line in `prompts/system.md`. The three previous scripts are passed in for continuity from one day to the next and to avoid repetition. The code then validates the episode (structure, theme order, sources, no markdown, no first person, no forbidden terms, length), asks for one correction round if needed, and assembles the spoken script with a fixed opening, transitions and sign-off.
2. **Speech synthesis**: two ElevenLabs voices share the episode. The host voice reads the opening, the facts, the transitions and the sign-off; the analyst voice reads every read layer, so the listener hears where analysis begins. A short pause marks each change of voice. Texts are split into chunks, with the neighbouring chunks of the same voice as context to keep the delivery continuous.
3. **Hosting**: the MP3 is published as a GitHub *release* asset (`episode-YYYY-MM-DD`).
4. **Distribution**: `data/episodes.json` is updated, then the `docs/feed.xml` feed and the `docs/catalog.json` catalog are regenerated and deployed to GitHub Pages.

Every episode follows the same format, as a single-voice monologue: opening with the headlines, story of the day, three or four themed segments, number of the day, what to watch, question for your team. Each story has two layers: the facts (what happened and its real status: announced, preview or available) and a short read (what it means for a platform team or a retailer), signposted so the listener hears where analysis begins. On Mondays it covers the news since Friday and the week ahead; on Fridays, the story of the day steps back to look at a trend from the week.

### Run modes

| Mode | Trigger | Effect |
| --- | --- | --- |
| Dry run | Manual run, `dry_run` option (default) | Script only, downloadable from the `episode-script` artifact. No ElevenLabs call, nothing published. |
| Preview | *Preview episode* workflow (manual) | Real script from Claude, published as a **Preview** card on the catalog site (no audio, Spotify link marked as coming soon). No ElevenLabs call, no release, RSS feed untouched, so nothing reaches Spotify. A published episode later replaces its preview. |
| Publish | Manual run without `dry_run`, or schedule | Full episode: audio, release, RSS feed. |
| Rehearsal | *Publication rehearsal* workflow (manual) | Checks the publication path on GitHub without ElevenLabs: a silent MP3 is uploaded as a release, downloaded back from its public URL and checked in the feed and catalog (built, never written or deployed), then the release is deleted. Nothing is published or committed. |
| Force | `force` option | Regenerates today's episode even if it already exists (or on a weekend), replacing the release. |

The schedule (`cron` in UTC in the workflow) aims to have the episode ready before the morning commute, Monday to Friday.

## Repository contents

```
config.yaml                          podcast metadata, models, voice, themes covered
prompts/system.md                    editorial line, episode format, writing rules for the voice
podcast/main.py                      pipeline (entry point: python -m podcast.main)
podcast/generate.py                  script writing with the Claude API and web search
podcast/tts.py                       ElevenLabs speech synthesis
podcast/publish.py                   MP3 upload as a GitHub release (gh CLI)
podcast/feed.py                      RSS feed compatible with Spotify and Apple Podcasts
podcast/catalog.py                   data for the episode catalog site
podcast/rehearsal.py                 publication rehearsal
data/episodes.json                   history of published episodes (source of the RSS feed)
data/scripts/                        archived scripts, one Markdown file per day
data/previews.json, data/previews/   preview episodes (catalog only) and their scripts
docs/                                GitHub Pages site: catalog page, feed.xml, catalog.json, cover.jpg
tools/make_cover.py                  cover art generation
.github/workflows/daily-episode.yml  daily workflow
.github/workflows/deploy-site.yml    site deployment when docs/ changes
.github/workflows/preview-episode.yml  script-only run published to the catalog site
.github/workflows/tests.yml          test suite on every push
.github/workflows/rehearsal.yml      publication rehearsal (silent audio, deleted afterwards)
tests/                               offline test suite (pytest)
```

### Configuration

- `config.yaml` holds everything editorial or tunable: title, description, language, Claude model, target length, ElevenLabs voice and model, and the list of themes with their scope. Themes can be changed at any time; they are used in segment order.
- `prompts/system.md` defines the tone, the audience, the source-checking rules and the expected output format (`<title>`, `<summary>`, `<script>`, `<sources>`).
- The `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` keys are stored as GitHub Actions secrets. No secret is committed.
- The optional `FORBIDDEN_TERMS` secret is a comma-separated list of names that must never be spoken; an episode containing one is rejected.

## Episode catalog

The GitHub Pages home page (`docs/index.html`) lists every episode as a card: cover image, status (Published or Preview), date, duration, title, summary, headlines, themes, audio player (or a placeholder for previews), Spotify link, script and sources. Episodes can be searched (titles, summaries, scripts) and filtered by theme, and each one has its own link (`#YYYY-MM-DD`). Every card and the header have a "Listen on Spotify" button: it opens `podcast.spotify_url` from `config.yaml` once set, and a Spotify search for the podcast until then.

The site is published at https://gwendalyviquel.github.io/signal-in-the-ai-fog/ by `.github/workflows/deploy-site.yml` whenever `docs/` changes, and by the daily workflow after each episode. Hosting is free (GitHub Pages for the site and feed, GitHub releases for the audio).

## Tests

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

The suite runs offline: Claude, ElevenLabs and `gh` are replaced by fakes, and the pipeline runs on a temporary copy of the data. It covers episode validation, the generation loop (tool submission, correction rounds, truncated responses), script assembly, speech chunking and retries, the RSS feed, the catalog, every run mode end to end, and repository hygiene (secrets wired into workflows, private files ignored, no forbidden term in tracked files when `FORBIDDEN_TERMS` is set). Every bug met in a real run gets a regression test.

Tests run on every push (`.github/workflows/tests.yml`) and before every generation in the daily and preview workflows, so a broken commit never produces an episode.

## Costs and safeguards

- An episode is about 6,000 to 7,000 characters, which is as many ElevenLabs credits with a standard model, for 20 to 23 episodes a month.
- ElevenLabs is never called in a dry run.
- An episode that is already published is not regenerated, unless `force` is used.
- No episode is produced on weekends.

## Transparency

The opening of each episode and its description state that the content is written and read by AI, in line with the AI Act's labelling obligations for AI-generated content. Each episode's sources are listed in its description.
