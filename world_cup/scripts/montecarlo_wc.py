"""
Monte Carlo de la Coupe du monde 2026 sur l'arbre réel (wc_bracket.json).

Pour chaque stade atteint (32es, 8es, quarts), on prend les équipes réellement
présentes à ce stade et on simule la suite du tableau (élimination directe) N fois,
via Elo pré-tournoi -> buts attendus (Poisson) ; en cas de nul, la qualification
est tranchée par la probabilité Elo (prolongation / tirs au but). On obtient la
probabilité de titre par équipe et le champion prédit à chaque stade.

On ajoute la justesse rétrospective du modèle en phase à élimination directe
(part des matchs où le favori du modèle s'est qualifié), lue dans predictions.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.football_elo import FootballElo, expected_score
from src.poisson import elo_lambdas

RESULTS = ROOT / "data" / "results.csv"
BRACKET = ROOT / "data" / "wc_bracket.json"
PREDS = ROOT / "data" / "predictions.json"
OUT = ROOT / "data" / "wc_montecarlo.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/wc_montecarlo.json")

TOURNEY_START = pd.Timestamp("2026-06-11")
FIT_END = pd.Timestamp("2026-01-01")
N_SIMS = 20000
RNG = np.random.default_rng(42)


def build_elo_and_fit():
    """Rejoue l'historique : Elo pré-tournoi par équipe + (b, mu) pour Elo->Poisson."""
    df = pd.read_csv(RESULTS).dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    elo = FootballElo()
    eds, gds, tots = [], [], []
    for r in df.itertuples(index=False):
        neutral = bool(r.neutral)
        _, _, ed = elo.pre_match(r.home_team, r.away_team, neutral)
        if r.date < FIT_END:
            eds.append(ed)
            gds.append(r.home_score - r.away_score)
            tots.append(r.home_score + r.away_score)
        if r.date < TOURNEY_START:
            elo.update(r.home_team, r.away_team, r.home_score, r.away_score, r.tournament, neutral)
    eds, gds = np.array(eds), np.array(gds)
    b = float((eds * gds).sum() / (eds * eds).sum())
    mu = float(np.mean(tots))
    return dict(elo.ratings), elo.initial, b, mu


def simulate(teams, ratings, initial, b, mu, n_sims):
    """Simule le tableau à élimination directe (teams en ordre de bracket) n_sims fois.
    Retourne un dict équipe -> probabilité de titre."""
    rating = np.array([ratings.get(t, initial) for t in teams], dtype=float)
    m = len(teams)
    wins = np.zeros(m, dtype=np.int64)
    idx0 = np.arange(m)
    for _ in range(n_sims):
        alive = idx0.copy()
        while len(alive) > 1:
            a = alive[0::2]
            b_ = alive[1::2]
            ra, rb = rating[a], rating[b_]
            ed = ra - rb  # neutre : pas d'avantage du terrain
            lam_a = np.maximum(0.15, (mu + b * ed) / 2)
            lam_b = np.maximum(0.15, (mu - b * ed) / 2)
            ga = RNG.poisson(lam_a)
            gb = RNG.poisson(lam_b)
            a_wins = ga > gb
            tie = ga == gb
            if tie.any():
                p_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))  # proba Elo (prolong./TAB)
                a_wins = np.where(tie, RNG.random(len(a)) < p_a, a_wins)
            alive = np.where(a_wins, a, b_)
        wins[alive[0]] += 1
    return {teams[i]: wins[i] / n_sims for i in range(m)}


def top_list(prob, flags, k=8):
    rows = sorted(prob.items(), key=lambda kv: kv[1], reverse=True)
    return [{"team": t, "flag": flags.get(t), "pct": round(100 * p, 1)} for t, p in rows[:k] if p > 0]


def main() -> int:
    bracket = json.loads(BRACKET.read_text(encoding="utf-8"))
    flags = {t["name"]: t.get("flag") for t in bracket["teams"]}
    ratings, initial, b, mu = build_elo_and_fit()

    teams_r32 = [t["name"] for t in bracket["teams"]]                 # 32
    teams_r16 = [n["winner"] for n in bracket["r32"] if n.get("winner")]  # 16
    teams_qf = [n["winner"] for n in bracket["r16"] if n.get("winner")]   # 8

    stages = {}
    for key, teams in (("round_of_32", teams_r32), ("round_of_16", teams_r16), ("quarter_final", teams_qf)):
        if len(teams) < 2:
            continue
        prob = simulate(teams, ratings, initial, b, mu, N_SIMS)
        champ = max(prob.items(), key=lambda kv: kv[1])
        stages[key] = {
            "n_teams": len(teams),
            "champion": champ[0], "champion_flag": flags.get(champ[0]),
            "champion_pct": round(100 * champ[1], 1),
            "top": top_list(prob, flags),
        }

    # Justesse rétrospective en KO : part des matchs où le favori du modèle s'est qualifié.
    ko_n = ko_ok = 0
    if PREDS.exists():
        preds = json.loads(PREDS.read_text(encoding="utf-8"))
        for mm in preds.get("wc_matches", []):
            if mm.get("is_knockout") and mm.get("actual_decisive_winner"):
                ko_n += 1
                if mm.get("decisive_correct"):
                    ko_ok += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_sims": N_SIMS,
        "elo_asof": TOURNEY_START.strftime("%Y-%m-%d"),
        "note": ("Simulation Monte Carlo du tableau final à partir des équipes réellement "
                 "présentes à chaque stade, via l'Elo pré-tournoi et un tirage Poisson des "
                 "buts (nul en KO tranché par la probabilité Elo). La simulation part des "
                 "32es (1er tour à élimination directe) : la phase de groupes n'est pas resimulée."),
        "current_stage": bracket.get("stage_reached"),
        "stages": stages,
        "knockout_accuracy": {"n": ko_n, "correct": ko_ok,
                              "pct": round(100 * ko_ok / ko_n, 1) if ko_n else None},
        "blend": {"b": round(b, 5), "mu": round(mu, 3)},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    cur = stages.get("quarter_final") or {}
    print(f"OK -> {OUT.name}")
    print(f"  champion prédit (quarts) : {cur.get('champion')} {cur.get('champion_pct')}%")
    print(f"  justesse KO : {ko_ok}/{ko_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
