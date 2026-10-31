# Ondes

Liste de mes podcasts, du plus récent au plus ancien.

## Comment ça marche
- `feeds.txt` : la liste des flux RSS (un par ligne).
- Une GitHub Action (`.github/workflows/update.yml`) récupère les flux toutes les 2 heures,
  et dès que `feeds.txt` est modifié, puis enregistre le résultat dans `episodes.json`.
- `index.html` affiche les épisodes (GitHub Pages), installable sur Android via Chrome → « Ajouter à l'écran d'accueil ».

## Installation
1. Créer un dépôt `Ondes` et y déposer tous les fichiers (en gardant le dossier `.github/workflows`).
2. Settings → Pages → Source : *Deploy from a branch*, branche `main`, dossier `/ (root)`.
3. Settings → Actions → General → Workflow permissions : cocher *Read and write permissions*.
4. Ajouter ses flux dans `feeds.txt` (directement depuis github.com) : la mise à jour se lance toute seule.
5. Lancer à la main si besoin : onglet Actions → *Mise à jour des podcasts* → *Run workflow*.

## Mise à jour à l'ouverture (recommandé)
1. github.com → Settings → Developer settings → Personal access tokens → *Fine-grained tokens* → *Generate new token*.
2. Repository access : *Only select repositories* → `Ondes`.
3. Permissions : **Actions : Read and write**, **Contents : Read-only**.
4. Dans l'appli, ⚙ → coller le jeton → Enregistrer.

À chaque ouverture, l'appli affiche aussitôt la dernière liste connue, lance la mise à jour,
puis affiche les nouveaux épisodes environ une minute plus tard (au plus une fois toutes les 5 min ;
↻ force une mise à jour).

## Dans l'appli
- Toucher un épisode : sa fiche complète (date, durée, description, liens).
- Filtres par podcast en haut.
- Badge « Nouveau » sur les épisodes sortis depuis la dernière ouverture.
