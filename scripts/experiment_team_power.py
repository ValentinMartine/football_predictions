"""
Expérience : la puissance d'équipe /110 de la SAISON PRÉCÉDENTE aide-t-elle la prédiction ?

Feature sans fuite : pour chaque match, on ajoute (puissance_domicile - puissance_extérieur)
mesurée la saison d'avant (connue avant le match). On entraîne le modèle AVEC et SANS cette
feature et on compare log-loss / exactitude sur validation et test. On rapporte aussi la
couverture (part des matchs réellement appariés aux notes Sofascore).
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, log_loss

from src.modeling import temporal_split
from src.pipeline import FEATURE_COLS, build_features

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "team_power_history.json"
BIG5 = {"E0", "SP1", "I1", "D1", "F1"}

# Alias football-data (normalisé) -> jeton distinctif présent dans le nom Sofascore normalisé.
ALIAS = {
    "man city": "manchester city", "man united": "manchester united",
    "ath madrid": "atletico madrid", "ath bilbao": "athletic",
    "sociedad": "real sociedad", "espanol": "espanyol", "betis": "real betis",
    "wolves": "wolverhampton", "nott'm forest": "nottingham", "newcastle": "newcastle",
    "paris sg": "paris saint germain", "bayern munich": "bayern", "dortmund": "dortmund",
    "leverkusen": "leverkusen", "m'gladbach": "gladbach", "ein frankfurt": "eintracht frankfurt",
    "inter": "inter", "ac milan": "milan", "roma": "roma", "napoli": "napoli",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def prev_fd_season(season: str) -> str:
    y = int(season[:2])
    return f"{y - 1:02d}/{y:02d}"


# Jetons trop communs : ne pas apparier deux clubs sur ces seuls mots.
STOP = {"united", "city", "real", "athletic", "sporting", "calcio", "club", "olympique",
        "football", "deportivo", "racing", "union"}


def _tokens(name: str) -> set[str]:
    return {t for t in name.split() if len(t) >= 4 and t not in STOP}


def make_matcher(season_map: dict[str, float]):
    keys = list(season_map.keys())
    key_tokens = {k: _tokens(k) for k in keys}

    def match(team: str) -> float | None:
        n = ALIAS.get(norm(team), norm(team))
        if n in season_map:
            return season_map[n]
        for k in keys:  # sous-chaîne dans un sens ou l'autre
            if n in k or k in n:
                return season_map[k]
        nt = _tokens(n)  # jeton distinctif commun (hors mots trop fréquents)
        for k in keys:
            if nt & key_tokens[k]:
                return season_map[k]
        return None
    return match


def main() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    df = build_features()
    df = df[df["league"].isin(BIG5)].reset_index(drop=True)

    matchers = {s: make_matcher(m) for s, m in history.items()}
    diffs, covered = [], 0
    for r in df.itertuples(index=False):
        ps = prev_fd_season(r.season)
        m = matchers.get(ps)
        if m is None:
            diffs.append(0.0)
            continue
        ph, pa = m(r.home_team), m(r.away_team)
        if ph is None or pa is None:
            diffs.append(0.0)
        else:
            diffs.append(ph - pa)
            covered += 1
    df["prev_power_diff"] = diffs
    print(f"couverture (matchs appariés à la puissance N-1) : {covered}/{len(df)} ({100*covered/len(df):.0f}%)")

    train, val, test = temporal_split(df)

    def fit_eval(cols):
        model = LGBMClassifier(objective="multiclass", num_class=3, n_estimators=500,
                               learning_rate=0.025, max_depth=5, num_leaves=31, subsample=0.85,
                               colsample_bytree=0.85, min_child_samples=35, random_state=42, verbose=-1)
        model.fit(train[cols], train["outcome"])
        out = {}
        for name, d in [("val", val), ("test", test)]:
            p = model.predict_proba(d[cols])
            out[name] = (round(accuracy_score(d["outcome"], p.argmax(1)), 4),
                         round(log_loss(d["outcome"], p, labels=[0, 1, 2]), 4))
        return out

    base = fit_eval(FEATURE_COLS)
    withp = fit_eval(FEATURE_COLS + ["prev_power_diff"])
    print(f"{'':14}{'val acc':>10}{'val ll':>10}{'test acc':>10}{'test ll':>10}")
    print(f"{'sans /110':14}{base['val'][0]:>10}{base['val'][1]:>10}{base['test'][0]:>10}{base['test'][1]:>10}")
    print(f"{'avec /110':14}{withp['val'][0]:>10}{withp['val'][1]:>10}{withp['test'][0]:>10}{withp['test'][1]:>10}")
    d_acc = (withp["test"][0] - base["test"][0]) * 100
    d_ll = withp["test"][1] - base["test"][1]
    print(f"delta test : accuracy {d_acc:+.2f} pt, log-loss {d_ll:+.4f} (négatif = mieux)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
