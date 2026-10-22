<p align="center"><img src="../../docs/hr-news-fr/cover.jpg" alt="Signal in the HR Fog cover art" width="200"></p>

# Signal in the HR Fog

**L'actualité RH et paie de la semaine**: a weekly show in French for HR managers and payroll teams.

| | |
| --- | --- |
| Status | live: first episode on October 22, 2026, then every Monday |
| Language | French |
| Cadence | weekly, on Monday at 4:05 Paris time, with the news of the last seven days, weekend included |
| Length | about 10 minutes (`target_words: 1400`) |
| Writing | two steps (`generation.dossier`): a research dossier where every fact is quoted from its page and checked by the code, then the episode written from it alone; fact-check and light corrections on Claude Haiku |
| Voices | Geneviève (host: a French news anchor) and Pierre (analyst: a French editorial narrator), ElevenLabs library voices, chosen on October 22, 2026 from their descriptions and accepted by *Check voices* |
| Site | [catalog](https://gwendalyviquel.github.io/signal-in-the-ai-fog/hr-news-fr/), in `docs/hr-news-fr/` |
| Feed | `docs/hr-news-fr/feed.xml`, on [Spotify](https://open.spotify.com/show/5DMF3STVdMZiNHCCOcV15E) since October 22, 2026 |
| Reports | [COSTS.md](COSTS.md) |

## Editorial line

Labour law, payroll and social news, read for practitioners: what changes, from when, and what to check. Every text is given at its real stage (bill, law, decree, case law), primary sources first (Légifrance, BOSS, URSSAF, Cour de cassation). Never individual legal advice; angles stay generic ("pour un service paie", "pour une entreprise de cinquante salariés"). The full line, in French, is in [prompt.md](prompt.md).

Themes, in segment order (`show.yaml`): Droit du travail, Paie et cotisations, IA et travail, Santé et conditions de travail, Emploi et retraite, Dialogue social, Formation, Europe. An episode has at most five segments, on the themes with news that week.

## Live

First episode published on Thursday, October 22, 2026 (forced, to start the feed); scheduled every Monday since. On [Spotify](https://open.spotify.com/show/5DMF3STVdMZiNHCCOcV15E). A private editorial context can be added at any time in the `EDITORIAL_CONTEXT_HR_NEWS_FR` secret.

Previews so far (October 22, 2026): about $1 to $2 of Claude each, with the two-step writing.
