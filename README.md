# Veille IA en production — podcast automatique

Chaque matin de semaine, une GitHub Action :

1. rédige le script de veille avec l'API Claude (recherche web incluse) ;
2. le fait lire par une voix ElevenLabs ;
3. héberge le MP3 en *release* GitHub ;
4. met à jour le flux RSS publié sur GitHub Pages, que Spotify récupère automatiquement.

```
config.yaml               podcast, modèles, voix, thèmes suivis
prompts/system.md         ligne éditoriale et format récurrent de l'épisode
veille/main.py            orchestration (point d'entrée)
veille/generate.py        script via l'API Claude
veille/tts.py             synthèse vocale ElevenLabs
veille/publish.py         upload du MP3 en release GitHub
veille/feed.py            flux RSS compatible Spotify / Apple Podcasts
data/episodes.json        historique des épisodes publiés
data/scripts/             scripts archivés (servent aussi à la continuité d'un jour à l'autre)
docs/                     site GitHub Pages : feed.xml + cover.jpg
tools/make_cover.py       génère une pochette par défaut
```

## Mise en place

### 1. Créer le dépôt

Le dépôt doit être **public** : GitHub Pages gratuit et les fichiers audio des releases doivent être accessibles à Spotify. Aucun secret ni information personnelle n'est versionné.

```bash
git remote add origin git@github.com:<compte>/<depot>.git
git push -u origin main
```

### 2. Ajouter les secrets

*Settings → Secrets and variables → Actions → New repository secret* :

| Nom | Où le trouver |
| --- | --- |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Keys |

### 3. Compléter `config.yaml`

- `podcast.author`, `podcast.owner_name`, `podcast.owner_email` : Spotify envoie un code de vérification à cette adresse, et elle apparaît dans le flux public. Une adresse dédiée est conseillée.
- `tts.voice_id` : dans ElevenLabs, *Voices*, puis « Copy voice ID » sur la voix choisie.
- `themes` : les rubriques suivies, modifiables à tout moment.
- Pochette : `docs/cover.jpg` est une pochette par défaut ; remplacez-la par un carré de 1400 à 3000 px si vous le souhaitez.

### 4. Activer GitHub Pages

*Settings → Pages → Build and deployment → Source : **GitHub Actions***.

### 5. Tester sans dépenser de crédits ElevenLabs

*Actions → Veille IA quotidienne → Run workflow*, case **dry_run cochée** (valeur par défaut).
Seul l'appel à l'API Claude est consommé. Le script est téléchargeable dans l'artefact `script-du-jour` du run.

### 6. Premier épisode réel

Relancer le workflow avec **dry_run décoché**. Vérifier ensuite :

- le MP3 dans *Releases* ;
- le flux sur `https://<compte>.github.io/<depot>/feed.xml`.

### 7. Soumettre le podcast à Spotify (une seule fois)

Sur creators.spotify.com : avatar → *Add a new show* → *Find an existing show* → coller l'URL du flux, puis valider le code reçu par e-mail. Spotify relit ensuite le flux toutes les quelques heures : chaque nouvel épisode y apparaît automatiquement.

### 8. Activer la planification

Dans `.github/workflows/veille.yml`, décommenter le bloc `schedule`. Les exécutions planifiées publient pour de vrai (pas de dry run).
Le cron est en UTC : `15 5 * * 1-5` donne 7h15 à Paris en été et 6h15 en hiver.

## Coûts et garde-fous

- Un épisode fait environ 6 000 à 7 000 caractères, soit autant de crédits ElevenLabs avec un modèle standard, et 20 à 23 épisodes par mois.
- Le script n'appelle jamais ElevenLabs en dry run et ne régénère pas un épisode déjà publié (sauf `force`).
- Le week-end, aucun épisode n'est produit.

## Transparence

L'ouverture de chaque épisode et sa description indiquent que le contenu est rédigé et lu par une IA, en cohérence avec les obligations de marquage des contenus générés par IA de l'AI Act.
