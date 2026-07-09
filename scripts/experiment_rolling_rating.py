"""
Teste l'idée : note glissante PAR JOUEUR (Sofascore), recalculée après chaque journée,
agrégée en note d'équipe avant le match. Comparée à un Elo glissant PAR ÉQUIPE, sur la
même saison (Premier League 25/26), en walk-forward. Aucune fuite : chaque prédiction
n'utilise que les journées précédentes.

On compare la log-loss / exactitude de trois jeux de variables sur les journées de test :
  - elo_diff seul (Elo d'équipe glissant),
  - rating_diff seul (notes joueurs glissantes agrégées),
  - les deux ensemble (le rating ajoute-t-il quelque chose à l'Elo ?).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "pl_player_match.json"
FORM_N = 5        # nombre de matchs pour la note glissante d'un joueur
TRAIN_ROUNDS = 24  # journées 1..24 pour ajuster, 25+ pour tester


def elo_expected(diff: float) -> float:
    return 1 / (1 + 10 ** (-diff / 400))


def main() -> int:
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    # regroupe par match, en gardant l'ordre des journées
    games: dict[tuple, dict] = {}
    for r in rows:
        key = (r["round"], r["home"], r["away"])
        g = games.setdefault(key, {"round": r["round"], "home": r["home"], "away": r["away"],
                                   "winner": r["winner"], "players": []})
        g["players"].append(r)
    games = sorted(games.values(), key=lambda g: (g["round"] or 0))
    print(f"{len(games)} matchs, notes joueurs par match")

    elo: dict[str, float] = defaultdict(lambda: 1500.0)
    hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=FORM_N))
    samples = []  # (round, elo_diff, rating_diff, outcome)

    def team_rating(players_of_team) -> float | None:
        # "a joué" = a une note ; robuste même si les minutes ne sont pas fournies
        vals = [np.mean(hist[p["player"]]) for p in players_of_team
                if p.get("rating", 0) > 0 and len(hist[p["player"]]) > 0]
        return float(np.mean(vals)) if vals else None

    for g in games:
        home, away, w = g["home"], g["away"], g["winner"]
        if w not in (1, 2, 3):
            continue
        outcome = 0 if w == 1 else (1 if w == 3 else 2)  # 0 dom, 1 nul, 2 ext
        hp = [p for p in g["players"] if p["team"] == home]
        ap = [p for p in g["players"] if p["team"] == away]
        rh, ra = team_rating(hp), team_rating(ap)
        elo_diff = elo[home] + 60 - elo[away]  # +60 = avantage domicile
        if rh is not None and ra is not None:
            samples.append((g["round"] or 0, elo_diff, rh - ra, outcome))

        # mise à jour APRÈS le match (pas de fuite)
        for p in g["players"]:
            if p.get("rating", 0) > 0:
                hist[p["player"]].append(p["rating"])
        sh = 1.0 if w == 1 else (0.5 if w == 3 else 0.0)
        exp = elo_expected(elo[home] + 60 - elo[away])
        elo[home] += 24 * (sh - exp)
        elo[away] += 24 * ((1 - sh) - (1 - exp))

    arr = np.array([s[1:] for s in samples], dtype=float)
    rounds = np.array([s[0] for s in samples])
    X_elo, X_rat, y = arr[:, [0]], arr[:, [1]], arr[:, 2].astype(int)
    X_both = arr[:, [0, 1]]
    tr, te = rounds <= TRAIN_ROUNDS, rounds > TRAIN_ROUNDS
    print(f"appariés {len(samples)} | train {tr.sum()} (J<= {TRAIN_ROUNDS}) | test {te.sum()}")

    def evaluate(X, name):
        m = LogisticRegression(max_iter=1000, C=1.0)
        m.fit(X[tr], y[tr])
        p = m.predict_proba(X[te])
        acc = accuracy_score(y[te], p.argmax(1))
        ll = log_loss(y[te], p, labels=[0, 1, 2])
        print(f"  {name:22} acc {acc:.3f}  log-loss {ll:.4f}")
        return acc, ll

    print("Walk-forward (test = journées 25+) :")
    evaluate(X_elo, "Elo d'équipe seul")
    evaluate(X_rat, "Notes joueurs seules")
    evaluate(X_both, "Elo + notes joueurs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
