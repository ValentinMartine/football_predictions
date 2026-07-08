# Prédictions au football

Prédictions pour les cinq grands championnats européens : Premier League, La Liga,
Serie A, Bundesliga et Ligue 1.

## Données

- Source : [football-data.co.uk](https://www.football-data.co.uk/)
- Championnats : E0, SP1, I1, D1, F1
- Saisons : 2015-2016 à 2025-2026
- Contenu exploité : résultats, statistiques de match et cotes bookmakers réelles.
- Données joueurs : Understat et FBref via `soccerdata` pour xG, xA, minutes,
  nationalités et compositions historiques récentes.

## Lancer le pipeline

```bash
pip install -r requirements.txt
python scripts/download_data.py
python scripts/train_and_backtest.py
python scripts/walk_forward_backtest.py
python -m src.export
python scripts/fetch_understat_stats.py
python scripts/add_player_flags.py
python scripts/build_lineups.py
python scripts/build_national_player_form.py
```

Actualisation en une commande :

```bash
python scripts/update_pipeline.py
```

Une GitHub Action exécute aussi ce pipeline chaque matin. Le site récupère
ensuite le JSON publié par ce dépôt via son propre workflow planifié.

## Méthode

- Pipeline chronologique sans fuite de données.
- Baseline Elo clubs avec avantage domicile et marge de victoire.
- Features de forme récente, buts, tirs, tirs cadrés et repos.
- Modèle LightGBM 3 classes : domicile, nul, extérieur.
- Blend LightGBM + Elo réglé sur validation temporelle.
- Backtest de paris sur cotes réelles avec Kelly fractionné, plafonné à 2 % du capital.
- Exports joueurs : classements xG/xA/buts/passes, compositions historiques
  récentes, et agrégat de forme club par nationalité.

## Résultats actuels

Sur le split de test final, le blend bat l'Elo :

| Modèle | Accuracy | Log-loss |
| --- | ---: | ---: |
| Elo | 52,14 % | 0,994 |
| LightGBM | 52,91 % | 0,985 |
| Blend | 53,11 % | 0,980 |

La couche de pari n'est pas résolue. La politique fixe walk-forward
`confiance >= 0,50`, `expected value >= 10 %`, `1,80 <= cote <= 3,00`
est positive en agrégé sur quatre saisons, mais pas sur chaque saison.

| Validation | Paris | ROI | Profit |
| --- | ---: | ---: | ---: |
| Walk-forward, politique fixe | 261 | +4,53 % | +241,02 |
| Politiques choisies sur validation | 501 | -4,57 % | -397,54 |
| Split final, politique fixe | 135 | -4,81 % | -121,36 |

Interprétation : le signal de valeur existe peut-être, mais il est encore
instable. Les politiques optimisées sur validation overfitent nettement.

## Prédictions avant match et après compositions

Le JSON exporté expose deux niveaux :

- `prediction_initiale` : modèle long terme avant match, basé sur Elo, forme,
  repos, tirs et cotes de marché.
- `prediction_apres_compositions` : schéma prêt pour les compositions
  officielles, absents, formations et charge récente de minutes.

La seconde prédiction est volontairement neutre pour l'instant : aucune source
fiable et historisée de compositions officielles n'est encore connectée. Elle
sera activée seulement quand la couverture historique permettra d'entraîner et
de tester le poids réel de ces variables.

Les compositions récentes et performances de joueurs sont néanmoins exportées
pour l'affichage et l'analyse (`data/lineups.json`, `data/understat_stats.json`).
Elles ne sont pas injectées dans le modèle tant qu'elles ne sont pas disponibles
en version pré-match et historisée sans fuite de données.
