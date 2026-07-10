# Prédictions au football - Coupe du Monde 2026

Prédiction rétrospective des matchs de la Coupe du monde 2026 : chaque match déjà joué est prédit avec les seules données antérieures. Le projet compare une baseline Elo à un modèle LightGBM enrichi, puis publie un artefact web `data/predictions.json`.

## Données

- Matchs internationaux : [martj42/international_results](https://github.com/martj42/international_results), `data/results.csv`, 49 500+ matchs masculins de 1872 à 2026.
- Tirs au but : [martj42/international_results](https://github.com/martj42/international_results), `data/shootouts.csv`, vainqueur et premier tireur des séances quand l'information est disponible.
- Classements FIFA historiques : [Dato-Futbol/fifa-ranking](https://github.com/Dato-Futbol/fifa-ranking), `data/fifa_rankings.csv`, snapshots 1992-2024.
- Métadonnées d'équipes Coupe du Monde : [jfjelstul/worldcup](https://github.com/jfjelstul/worldcup), `data/worldcup_teams.csv`, confédération et région des équipes ayant déjà joué une Coupe du Monde.

Les scores de `results.csv` sont les scores avant tirs au but : la prolongation peut être incluse quand elle existe, mais le fichier ne sépare pas le score à 90 minutes du score à 120 minutes. `shootouts.csv` ajoute le vainqueur et le premier tireur de la séance, mais pas le score de la séance. Le site affiche donc le score avant tirs au but et la séance séparément, sans inventer de score à la 90e minute.

## Méthode

1. Elo football chronologique : avantage du terrain, K par tournoi, multiplicateur de marge de victoire.
2. Features sans fuite : Elo pré-match, forme récente multi-fenêtres (5, 10, 20 matchs), buts pour/contre, repos, contexte de tournoi, points et rang FIFA historiques connus avant le match.
3. LightGBM 3 classes pour l'issue domicile/nul/extérieur.
4. Blend ML + Elo, poids réglé sur validation temporelle.
5. Score exact via Poisson dérivé de l'écart Elo, contraint à rester cohérent avec l'issue prédite par le blend.

## Résultats

Grand test tenu à l'écart : 3 694 matchs internationaux depuis 2023.

| Modèle | Issue | Log-loss | Score exact |
|---|---:|---:|---:|
| Baseline Elo | 60,6 % | 0,8754 | 13,2 % |
| Blend ML+Elo | 61,1 % | 0,8568 | 11,5 % |

Vitrine Coupe du monde 2026 : 96 matchs joués.

| Modèle | Issue | Log-loss | Score exact |
|---|---:|---:|---:|
| Baseline Elo | 64,6 % | 0,8637 | 13,5 % |
| Blend ML+Elo | 64,6 % | 0,8175 | 14,6 % |

Dixon-Coles a été testé, mais sous-performe ici sur le football international : il est conservé comme référence expérimentale, pas comme modèle principal.

### Apport du classement FIFA

Les points FIFA ne sont pas un Elo maison, mais le classement masculin FIFA utilise depuis 2018 une formule de type Elo/SUM. Dans ce projet, ils sont utilisés comme features externes datées (`fifa_points_*`, `fifa_rank_*`) connues avant chaque match.

| Features | Issue test | Log-loss test | Issue Coupe du Monde | Log-loss Coupe du Monde |
|---|---:|---:|---:|---:|
| Toutes les features | 61,1 % | 0,8568 | 64,6 % | 0,8175 |
| Sans FIFA | 60,8 % | 0,8601 | 62,5 % | 0,8340 |
| FIFA + contexte seul | 60,6 % | 0,8665 | 65,6 % | 0,8414 |

Conclusion : le rang et les points FIFA apportent un signal utile, surtout en calibration, mais ils ne remplacent pas l'Elo chronologique recalculé sur l'historique complet.

### Ablation des groupes de features

Les features de phase, de lieu 2026, de confédération et de contexte géographique sont calculées comme candidates, mais ne sont pas activées dans le modèle principal : aucune ne donne un gain assez stable sur le grand test tenu à l'écart et sur la log-loss Coupe du Monde.

| Features | Issue test | Log-loss test | Issue Coupe du Monde | Log-loss Coupe du Monde |
|---|---:|---:|---:|---:|
| Actives | 61,1 % | 0,8568 | 64,6 % | 0,8175 |
| Actives + phase Coupe du Monde | 61,2 % | 0,8574 | 64,6 % | 0,8237 |
| Actives + lieu 2026 | 61,0 % | 0,8588 | 64,6 % | 0,8335 |
| Actives + confédération/géographie | 61,0 % | 0,8565 | 65,6 % | 0,8236 |
| Actives + tous candidats | 61,1 % | 0,8571 | 64,6 % | 0,8347 |
| Sans FIFA | 60,8 % | 0,8601 | 62,5 % | 0,8340 |
| Sans forme récente | 60,8 % | 0,8663 | 64,6 % | 0,8253 |
| Sans repos | 61,1 % | 0,8577 | 64,6 % | 0,8220 |
| Sans contexte tournoi | 61,0 % | 0,8602 | 66,7 % | 0,8267 |

### Prototype forme club vers sélection

Un premier proxy agrège les performances en club des joueurs des cinq grands
championnats par nationalité : minutes, buts, xG et xA via Understat, avec
nationalités FBref via `soccerdata`. Ce n'est pas encore une force d'effectif
officielle : il manque les listes de sélection historisées et les absents.

Sur la vitrine Coupe du Monde 2026, le proxy couvre 27 matchs sur 96 et atteint
62,96 % d'accuracy quand il tranche, contre 64,58 % pour le blend principal sur
l'ensemble des matchs. Il reste donc candidat, mais n'est pas activé dans le
modèle principal.

## Usage

```bash
pip install -r requirements.txt
python scripts/download_fifa_rankings.py
python scripts/download_match_data.py
python scripts/download_worldcup_metadata.py
python scripts/train_and_backtest.py
python scripts/compare_fifa_features.py
python scripts/compare_feature_groups.py
python scripts/compare_club_form_proxy.py
python -m src.export
```

## Améliorations restantes

- Mettre à jour les classements FIFA après septembre 2024 si une source historique fiable et reproductible est disponible. La page officielle FIFA expose bien des dates récentes, mais pas un CSV historique complet directement comparable à `data/fifa_rankings.csv`.
- Trouver une source fiable distinguant score à 90 minutes, score à 120 minutes et score de la séance de tirs au but.
- Trouver une source fiable de stades/coordonnées pour remplacer les features candidates de lieu 2026 par de vraies features de déplacement.
- Brancher les listes officielles de sélection et les absences pour remplacer le
  proxy de nationalité par une vraie force d'effectif pré-match.
