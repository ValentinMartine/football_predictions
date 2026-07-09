"""
Réplique le test du rating glissant par joueur sur plusieurs ligues (PL + La Liga + Serie A
25/26). Elo et notes glissantes calculés PAR LIGUE (les équipes ne jouent qu'entre elles),
puis échantillons regroupés pour un split walk-forward commun (journées <=24 = train).
Compare Elo seul / notes joueurs seules / les deux.
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
FILES = [ROOT / "data" / "pl_player_match.json"] + sorted((ROOT / "data" / "player_match").glob("*.json"))
FORM_N = 5
TRAIN_ROUNDS = 24


def elo_expected(diff):
    return 1 / (1 + 10 ** (-diff / 400))


def process(rows, samples):
    games = {}
    for r in rows:
        g = games.setdefault((r["round"], r["home"], r["away"]),
                             {"round": r["round"], "home": r["home"], "away": r["away"], "winner": r["winner"], "players": []})
        g["players"].append(r)
    games = sorted(games.values(), key=lambda g: (g["round"] or 0))
    elo = defaultdict(lambda: 1500.0)
    hist = defaultdict(lambda: deque(maxlen=FORM_N))

    def team_rating(ps):
        vals = [np.mean(hist[p["player"]]) for p in ps if p.get("rating", 0) > 0 and len(hist[p["player"]]) > 0]
        return float(np.mean(vals)) if vals else None

    for g in games:
        home, away, w = g["home"], g["away"], g["winner"]
        if w not in (1, 2, 3):
            continue
        outcome = 0 if w == 1 else (1 if w == 3 else 2)
        rh = team_rating([p for p in g["players"] if p["team"] == home])
        ra = team_rating([p for p in g["players"] if p["team"] == away])
        elo_diff = elo[home] + 60 - elo[away]
        if rh is not None and ra is not None:
            samples.append((g["round"] or 0, elo_diff, rh - ra, outcome))
        for p in g["players"]:
            if p.get("rating", 0) > 0:
                hist[p["player"]].append(p["rating"])
        sh = 1.0 if w == 1 else (0.5 if w == 3 else 0.0)
        exp = elo_expected(elo[home] + 60 - elo[away])
        elo[home] += 24 * (sh - exp)
        elo[away] += 24 * ((1 - sh) - (1 - exp))


def main() -> int:
    samples = []
    used = 0
    for f in FILES:
        if f.exists():
            process(json.loads(f.read_text(encoding="utf-8")), samples)
            used += 1
    print(f"{used} ligues, {len(samples)} matchs appariés")
    arr = np.array([s[1:] for s in samples], dtype=float)
    rounds = np.array([s[0] for s in samples])
    y = arr[:, 2].astype(int)
    tr, te = rounds <= TRAIN_ROUNDS, rounds > TRAIN_ROUNDS
    print(f"train {tr.sum()} (J<= {TRAIN_ROUNDS}) | test {te.sum()}")

    def ev(cols, name):
        m = LogisticRegression(max_iter=1000).fit(arr[tr][:, cols], y[tr])
        p = m.predict_proba(arr[te][:, cols])
        print(f"  {name:22} acc {accuracy_score(y[te], p.argmax(1)):.3f}  log-loss {log_loss(y[te], p, labels=[0,1,2]):.4f}")

    print("Walk-forward (test = journées 25+, 3 ligues) :")
    ev([0], "Elo d'équipe seul")
    ev([1], "Notes joueurs seules")
    ev([0, 1], "Elo + notes joueurs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
