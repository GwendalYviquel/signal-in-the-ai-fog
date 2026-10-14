# Signal in the AI Fog

Podcast quotidien de veille IA, en anglais, entièrement généré et publié de façon automatique.

Chaque matin de semaine, un épisode d'environ six minutes fait le point sur l'IA d'entreprise en production : modèles et fournisseurs, souveraineté européenne, plateformes LLMOps et MLOps, qualité et évaluation, réglementation, retail et agents. Le script est rédigé par Claude à partir d'une recherche web, puis lu par une voix ElevenLabs. L'épisode est diffusé via un flux RSS que Spotify et les autres plateformes de podcast récupèrent automatiquement.

## Fonctionnement

Une GitHub Action enchaîne quatre étapes :

1. **Rédaction** : l'API Claude, avec l'outil de recherche web, sélectionne cinq ou six actualités des dernières 24 à 72 heures et rédige le script selon la ligne éditoriale de `prompts/system.md`. Les trois derniers scripts lui sont fournis pour assurer la continuité d'un jour à l'autre et éviter les redites.
2. **Synthèse vocale** : le texte est découpé en morceaux et envoyé à ElevenLabs, avec le contexte des morceaux voisins pour garder une diction continue.
3. **Hébergement** : le MP3 est publié comme fichier d'une *release* GitHub (`episode-AAAA-MM-JJ`).
4. **Diffusion** : `data/episodes.json` est mis à jour, le flux `docs/feed.xml` est régénéré et déployé sur GitHub Pages.

Le format de chaque épisode est fixe : ouverture avec les titres, sujet du jour, rubriques thématiques, chiffre du jour, points à surveiller, question de la semaine. Le lundi couvre l'actualité depuis le vendredi et la semaine à venir ; le vendredi, le sujet du jour prend du recul sur une tendance de la semaine.

### Modes d'exécution

| Mode | Déclenchement | Effet |
| --- | --- | --- |
| Dry run | Lancement manuel, option `dry_run` (par défaut) | Script uniquement, téléchargeable dans l'artefact `script-du-jour`. Aucun appel ElevenLabs, aucune publication. |
| Publication | Lancement manuel sans `dry_run`, ou planification | Épisode complet : audio, release, flux RSS. |
| Force | Option `force` | Régénère l'épisode du jour même s'il existe déjà (ou le week-end), en remplaçant la release. |

La planification (`cron` en UTC dans le workflow) vise un épisode disponible avant le trajet du matin, du lundi au vendredi.

## Contenu du dépôt

```
config.yaml                  métadonnées du podcast, modèles, voix, thèmes suivis
prompts/system.md            ligne éditoriale, format de l'épisode, règles d'écriture pour la voix
veille/main.py               orchestration (point d'entrée : python -m veille.main)
veille/generate.py           rédaction du script via l'API Claude et la recherche web
veille/tts.py                synthèse vocale ElevenLabs
veille/publish.py            upload du MP3 en release GitHub (CLI gh)
veille/feed.py               flux RSS compatible Spotify et Apple Podcasts
data/episodes.json           historique des épisodes publiés (source du flux RSS)
data/scripts/                scripts archivés, un fichier Markdown par jour
docs/                        site GitHub Pages : feed.xml et cover.jpg
tools/make_cover.py          génération de la pochette
.github/workflows/veille.yml workflow quotidien
```

### Configuration

- `config.yaml` porte tout ce qui est éditorial ou paramétrable : titre, description, langue, modèle Claude, longueur cible, voix et modèle ElevenLabs, liste des thèmes et leur périmètre. Les thèmes peuvent être modifiés à tout moment, ils sont repris dans l'ordre des rubriques.
- `prompts/system.md` définit le ton, l'audience, les règles de vérification des sources et le format de sortie attendu (`<title>`, `<summary>`, `<script>`, `<sources>`).
- Les clés `ANTHROPIC_API_KEY` et `ELEVENLABS_API_KEY` sont stockées en secrets GitHub Actions. Aucun secret n'est versionné.

## Coûts et garde-fous

- Un épisode représente environ 6 000 à 7 000 caractères, soit autant de crédits ElevenLabs avec un modèle standard, pour 20 à 23 épisodes par mois.
- ElevenLabs n'est jamais appelé en dry run.
- Un épisode déjà publié n'est pas régénéré, sauf avec `force`.
- Aucun épisode n'est produit le week-end.

## Transparence

L'ouverture de chaque épisode et sa description indiquent que le contenu est rédigé et lu par une IA, en cohérence avec les obligations de marquage des contenus générés par IA de l'AI Act. Les sources de chaque épisode sont listées dans sa description.
