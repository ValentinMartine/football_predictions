# football_predictions : repères projet

Prédiction des cinq grands championnats européens (E0, SP1, I1, D1, F1), saisons 2015-2016 à 2025-2026.
Les règles de travail générales sont dans `~/.claude/CLAUDE.md`.

## Stack
Python, LightGBM, Elo maison. Pas de framework web : le dépôt produit des JSON consommés par
`valentinmartine` (site perso).

## Chemins clés
- `src/elo.py` : baseline Elo clubs (avantage domicile, marge de victoire).
- `src/pipeline.py` : construction des features, chronologique.
- `src/modeling.py` : LightGBM 3 classes (domicile / nul / extérieur) et blend avec l'Elo.
- `src/calibration.py`, `src/poisson.py`, `src/walk_forward.py`, `src/backtesting.py` : calibration,
  score exact, validation glissante, backtest de mise.
- `src/export.py` : génération des JSON publiés.
- `scripts/` : un script par étape ; `scripts/update_pipeline.py` enchaîne tout.
- `automation/daily_update.py` (+ `.bat`/`.vbs`) : mise à jour quotidienne via le Planificateur Windows.
- `data/` : données téléchargées et artefacts JSON versionnés.

## Règles non négociables
- **Aucune fuite de données.** Toute feature doit n'utiliser que de l'information disponible **avant**
  le match. C'est la règle qui prime sur toute amélioration de score.
- **Split temporel**, jamais aléatoire. Le test final reste tenu à l'écart.
- Une idée se juge sur le **test hors échantillon**, pas sur la validation : les politiques de pari
  optimisées sur validation surapprennent nettement (constaté : ROI positif en walk-forward,
  négatif sur le split final).
- Kelly fractionné plafonné à 2 % du capital, garde-fous conservés.

## État
Blend > LightGBM > Elo en log-loss (0,980 / 0,985 / 0,994 sur le split de test final).
La couche de pari **n'est pas résolue** : ne pas présenter le projet comme rentable.

## Sous-projet `world_cup/`
La Coupe du Monde vit **dans ce dépôt**, sous `world_cup/`, avec son propre `src/`, ses données et son
workflow `.github/workflows/regenerate-worldcup.yml` (toutes les 2 heures pendant le tournoi).
L'ancien dépôt séparé est **archivé sur GitHub depuis le 09/09/2026** sous
`ValentinMartine/worldcup-2026-predictions` : il était nommé `claude-memory`, ce qui n'a jamais
correspondu à son contenu, et son workflow poussait encore des données toutes les 2 heures alors
que le site ne les lit pas. Il est en lecture seule : **plus rien à y reporter**, `world_cup/` est
la seule version. Le clone local en double a été déplacé dans `Perso/_archives/`.

Sa suite de tests se lance **depuis son dossier** : `cd world_cup && python -m pytest`. La racine du
dépôt ignore `world_cup/` à la collecte, sinon les deux paquets `src/` entrent en collision.

## Automatisation, doublon volontaire
Le pipeline tourne à deux endroits, et c'est **voulu** : `automation/daily_update.py` par le Planificateur
Windows quand le PC est allumé (il fait plus : Sofascore, dont les IP de CI sont bloquées, et la copie
vers le site), et `.github/workflows/update-predictions.yml` chaque matin à 6h20 en relais quand le PC
est éteint. Ne pas « corriger » cette redondance, elle est documentée dans le docstring de `daily_update.py`.

## Tests
`python -m pytest tests/` depuis la racine. `tests/test_elo.py` verrouille les invariants de la baseline :
symétrie et monotonie des probabilités, conservation de la somme des Elo, croissance du multiplicateur de
marge, et surtout **absence de fuite temporelle** (l'Elo pré-match ne change pas si des matchs postérieurs
sont ajoutés).

## Chantier à venir
Archiver chaque semaine les sorties de `scripts/fetch_market_data.py` (valeurs Transfermarkt, salaires
Capology) dans un historique **daté** dès la reprise de saison, pour en faire des features sans fuite.
Les valeurs actuelles vivent dans `data/team_market.json`, sous la clé `teams`. Ne pas recopier
le nombre de clubs ici : il suit les mises à jour du fichier.
