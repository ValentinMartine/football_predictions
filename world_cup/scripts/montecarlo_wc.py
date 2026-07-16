"""
Monte Carlo de la Coupe du monde 2026 sur l'arbre réel (wc_bracket.json).

Pour chaque stade atteint (32es, 8es, quarts...), on prend les équipes réellement
présentes à ce stade et on simule la suite du tableau (élimination directe) N fois,
via Elo pré-tournoi -> buts attendus (Poisson) ; en cas de nul, la qualification
est tranchée par la probabilité Elo (prolongation / tirs au but). On obtient la
probabilité de titre par équipe et le champion prédit à chaque stade.

S'y ajoutent trois instantanés de phase de poules (avant J1, avant J2, avant J3) :
les journées déjà jouées sont figées à leur résultat réel, les suivantes sont
simulées, puis classement (pts, diff., buts marqués, tirage au sort), qualification
des deux premiers + 8 meilleurs troisièmes, et remplissage du tableau final réel
(les troisièmes qualifiés sont répartis aléatoirement sur les slots de troisièmes,
approximation de la table d'affectation FIFA).

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


# Drapeaux des équipes éliminées en poules (absentes de wc_bracket.json).
FALLBACK_FLAGS = {
    "Jordan": "🇯🇴", "Turkey": "🇹🇷", "Iran": "🇮🇷", "New Zealand": "🇳🇿",
    "Qatar": "🇶🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Haiti": "🇭🇹", "Uruguay": "🇺🇾",
    "Saudi Arabia": "🇸🇦", "Uzbekistan": "🇺🇿", "Panama": "🇵🇦", "Curaçao": "🇨🇼",
    "South Korea": "🇰🇷", "Czech Republic": "🇨🇿", "Iraq": "🇮🇶", "Tunisia": "🇹🇳",
}


def load_groups_and_fixtures():
    """Reconstitue poules et journées depuis results.csv : les 72 premiers matchs
    du Mondial où chaque équipe a joué moins de 3 fois sont la phase de groupes."""
    df = pd.read_csv(RESULTS).dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    wc = df[(df["date"] >= TOURNEY_START)
            & df["tournament"].str.contains("World Cup", case=False, na=False)].sort_values("date")
    played, fixtures = {}, []
    for r in wc.itertuples(index=False):
        h, a = r.home_team, r.away_team
        if played.get(h, 0) < 3 and played.get(a, 0) < 3:
            fixtures.append((h, a, int(r.home_score), int(r.away_score), r.date))
            played[h] = played.get(h, 0) + 1
            played[a] = played.get(a, 0) + 1
    # poules par connexité des confrontations
    adj = {}
    for h, a, *_ in fixtures:
        adj.setdefault(h, set()).add(a)
        adj.setdefault(a, set()).add(h)
    groups, seen = [], set()
    for t in sorted(adj):
        if t in seen:
            continue
        comp, stack = [], [t]
        seen.add(t)
        while stack:
            c = stack.pop()
            comp.append(c)
            for n in adj[c]:
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        groups.append(sorted(comp))
    groups.sort(key=lambda g: g[0])
    # journées : par poule, ordre chronologique, une équipe ne joue qu'une fois par journée
    gidx = {t: i for i, g in enumerate(groups) for t in g}
    fixtures_md = []  # (groupe, home, away, hs, as, journée 1-3)
    for g in range(len(groups)):
        md_played = [set(), set(), set()]
        for h, a, hs, as_, d in [f for f in fixtures if gidx[f[0]] == g]:
            for md in range(3):
                if h not in md_played[md] and a not in md_played[md]:
                    md_played[md].update((h, a))
                    fixtures_md.append((g, h, a, hs, as_, md + 1))
                    break
    assert len(fixtures_md) == 6 * len(groups), "journées de poules incohérentes"
    return groups, fixtures_md


def build_slot_template(bracket_names, groups, fixtures_md):
    """Pour chaque slot du tableau réel (ordre de wc_bracket.json) : (groupe, type)
    avec type 0 = vainqueur de poule, 1 = deuxième, 2 = troisième qualifié."""
    gidx = {t: i for i, g in enumerate(groups) for t in g}
    # classement réel par poule (pts, diff, buts) pour ordonner les qualifiés
    stats = {t: [0, 0, 0] for g in groups for t in g}
    for _, h, a, hs, as_, _ in fixtures_md:
        stats[h][0] += 3 * (hs > as_) + (hs == as_)
        stats[a][0] += 3 * (as_ > hs) + (hs == as_)
        stats[h][1] += hs - as_
        stats[a][1] += as_ - hs
        stats[h][2] += hs
        stats[a][2] += as_
    qualified = set(bracket_names)
    rank_type = {}
    for g, teams in enumerate(groups):
        quals = sorted([t for t in teams if t in qualified],
                       key=lambda t: stats[t], reverse=True)
        for r, t in enumerate(quals):
            rank_type[t] = (g, r)
    template = [rank_type[name] for name in bracket_names]
    n_thirds = sum(1 for _, r in template if r == 2)
    assert n_thirds == 8, f"attendu 8 troisièmes qualifiés, trouvé {n_thirds}"
    return template


def simulate_ko_matrix(ids, ratings_by_id, b, mu):
    """KO vectorisé sur toutes les simulations : ids (S, 32) -> champion (S,)."""
    alive = ids
    while alive.shape[1] > 1:
        a = alive[:, 0::2]
        b_ = alive[:, 1::2]
        ra, rb = ratings_by_id[a], ratings_by_id[b_]
        ed = ra - rb
        lam_a = np.maximum(0.15, (mu + b * ed) / 2)
        lam_b = np.maximum(0.15, (mu - b * ed) / 2)
        ga = RNG.poisson(lam_a)
        gb = RNG.poisson(lam_b)
        a_wins = ga > gb
        tie = ga == gb
        if tie.any():
            p_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
            a_wins = np.where(tie, RNG.random(a.shape) < p_a, a_wins)
        alive = np.where(a_wins, a, b_)
    return alive[:, 0]


def simulate_from_groups(known_md, groups, fixtures_md, template,
                         ratings, initial, b, mu, n_sims):
    """Simule poules + tableau final ; les journées <= known_md gardent leur
    résultat réel. Retourne équipe -> probabilité de titre."""
    all_teams = [t for g in groups for t in g]  # indices : poule g -> 4g..4g+3
    tid = {t: i for i, t in enumerate(all_teams)}
    ratings_by_id = np.array([ratings.get(t, initial) for t in all_teams], dtype=float)
    S, n_groups = n_sims, len(groups)
    pts = np.zeros((S, len(all_teams)))
    gd = np.zeros((S, len(all_teams)))
    gf = np.zeros((S, len(all_teams)))
    for g, h, a, hs, as_, md in fixtures_md:
        i, j = tid[h], tid[a]
        if md <= known_md:
            gh = np.full(S, hs)
            ga = np.full(S, as_)
        else:
            ed = ratings_by_id[i] - ratings_by_id[j]
            gh = RNG.poisson(max(0.15, (mu + b * ed) / 2), S)
            ga = RNG.poisson(max(0.15, (mu - b * ed) / 2), S)
        pts[:, i] += 3 * (gh > ga) + (gh == ga)
        pts[:, j] += 3 * (ga > gh) + (gh == ga)
        gd[:, i] += gh - ga
        gd[:, j] += ga - gh
        gf[:, i] += gh
        gf[:, j] += ga
    # classement par poule (départage : diff, buts, tirage au sort)
    first = np.empty((S, n_groups), dtype=np.int64)
    second = np.empty((S, n_groups), dtype=np.int64)
    third = np.empty((S, n_groups), dtype=np.int64)
    third_score = np.empty((S, n_groups))
    for g in range(n_groups):
        sl = slice(4 * g, 4 * g + 4)
        score = pts[:, sl] * 1e6 + (gd[:, sl] + 200) * 1e3 + gf[:, sl] + RNG.random((S, 4))
        order = np.argsort(-score, axis=1)
        first[:, g] = 4 * g + order[:, 0]
        second[:, g] = 4 * g + order[:, 1]
        third[:, g] = 4 * g + order[:, 2]
        third_score[:, g] = np.take_along_axis(score, order[:, 2:3], axis=1)[:, 0]
    # 8 meilleurs troisièmes, répartis aléatoirement sur les slots de troisièmes
    best_thirds = np.argsort(-third_score, axis=1)[:, :8]
    qual_third_ids = RNG.permuted(np.take_along_axis(third, best_thirds, axis=1), axis=1)
    ids = np.empty((S, len(template)), dtype=np.int64)
    ti = 0
    for k, (g, r) in enumerate(template):
        if r == 0:
            ids[:, k] = first[:, g]
        elif r == 1:
            ids[:, k] = second[:, g]
        else:
            ids[:, k] = qual_third_ids[:, ti]
            ti += 1
    champs = simulate_ko_matrix(ids, ratings_by_id, b, mu)
    counts = np.bincount(champs, minlength=len(all_teams))
    return {all_teams[i]: counts[i] / S for i in range(len(all_teams))}


def main() -> int:
    bracket = json.loads(BRACKET.read_text(encoding="utf-8"))
    flags = dict(FALLBACK_FLAGS)
    flags.update({t["name"]: t.get("flag") for t in bracket["teams"]})
    ratings, initial, b, mu = build_elo_and_fit()

    teams_r32 = [t["name"] for t in bracket["teams"]]                 # 32
    teams_r16 = [n["winner"] for n in bracket["r32"] if n.get("winner")]  # 16
    teams_qf = [n["winner"] for n in bracket["r16"] if n.get("winner")]   # 8
    teams_sf = [n["winner"] for n in bracket.get("qf", []) if n.get("winner")]     # 4
    teams_final = [n["winner"] for n in bracket.get("sf", []) if n.get("winner")]  # 2

    # Clés « *_start » = simulation à partir des équipes réellement qualifiées pour ce stade.
    stage_defs = (
        ("round_of_32_start", teams_r32, 32),
        ("round_of_16_start", teams_r16, 16),
        ("quarter_final_start", teams_qf, 8),
        ("semi_final_start", teams_sf, 4),
        ("final_start", teams_final, 2),
    )
    stages, latest_key = {}, None
    for key, teams, expected in stage_defs:
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
        if len(teams) == expected:  # stade entièrement déterminé -> candidat « dernier stade »
            latest_key = key

    # Instantanés de phase de poules : avant J1 (tout simulé), avant J2, avant J3.
    try:
        groups, fixtures_md = load_groups_and_fixtures()
        template = build_slot_template([t["name"] for t in bracket["teams"]], groups, fixtures_md)
        for key, known_md in (("before_group_j1", 0), ("before_group_j2", 1), ("before_group_j3", 2)):
            prob = simulate_from_groups(known_md, groups, fixtures_md, template,
                                        ratings, initial, b, mu, N_SIMS)
            champ = max(prob.items(), key=lambda kv: kv[1])
            stages[key] = {
                "n_teams": sum(len(g) for g in groups),
                "champion": champ[0], "champion_flag": flags.get(champ[0]),
                "champion_pct": round(100 * champ[1], 1),
                "top": top_list(prob, flags),
            }
    except Exception as exc:  # noqa: BLE001 - best effort : le KO reste publié
        print(f"  instantanés de poules ignorés : {exc}")

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
        "note": ("Simulation Monte Carlo à partir des équipes réellement présentes à chaque "
                 "stade, via l'Elo pré-tournoi et un tirage Poisson des buts (nul en KO "
                 "tranché par la probabilité Elo). Les instantanés avant J1/J2/J3 resimulent "
                 "la phase de poules (journées déjà jouées figées à leur résultat réel), "
                 "qualifient les deux premiers et les 8 meilleurs troisièmes, et répartissent "
                 "les troisièmes aléatoirement sur les slots du tableau réel."),
        "current_stage": bracket.get("stage_reached"),
        "latest_completed_stage_key": latest_key,
        "stages": stages,
        "knockout_accuracy": {"n": ko_n, "correct": ko_ok,
                              "pct": round(100 * ko_ok / ko_n, 1) if ko_n else None},
        "blend": {"b": round(b, 5), "mu": round(mu, 3)},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    cur = stages.get(latest_key) or {}
    print(f"OK -> {OUT.name}")
    print(f"  champion prédit ({latest_key}) : {cur.get('champion')} {cur.get('champion_pct')}%")
    print(f"  justesse KO : {ko_ok}/{ko_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
