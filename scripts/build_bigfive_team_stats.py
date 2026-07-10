"""
Statistiques descriptives PAR ÉQUIPE pour les cinq grands championnats,
pour un tableau triable côté site (onglet Big Five / Statistiques).

Même esprit que l'onglet « Autres championnats » mais au niveau équipe :
buts pour/contre par match, % de victoires/nuls/défaites, % +2,5 buts,
tirs, tirs cadrés, corners, cartons et fautes par match, points par match.
Fenêtre récente (depuis 2019), source club-football-match-data (Kaggle).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "european" / "Matches.csv"
OUT = ROOT / "data" / "bigfive_team_stats.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/bigfive_team_stats.json")
SINCE = "2019-01-01"
MIN_MATCHES = 20

DIV = {
    "E0": ("Premier League", "🇬🇧"), "SP1": ("LaLiga", "🇪🇸"), "I1": ("Serie A", "🇮🇹"),
    "D1": ("Bundesliga", "🇩🇪"), "F1": ("Ligue 1", "🇫🇷"),
}


def _pct(mask) -> float:
    return round(100 * float(mask.mean()), 1)


def main() -> int:
    cols = ["Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway", "FTResult",
            "HomeShots", "AwayShots", "HomeTarget", "AwayTarget", "HomeCorners", "AwayCorners",
            "HomeYellow", "AwayYellow", "HomeRed", "AwayRed", "HomeFouls", "AwayFouls"]
    df = pd.read_csv(SRC, usecols=cols)
    df = df[(df["MatchDate"] >= SINCE) & (df["Division"].isin(DIV))].dropna(subset=["FTHome", "FTAway", "FTResult"])

    # Format long : une ligne par (équipe, match), point de vue de l'équipe.
    def side(is_home: bool) -> pd.DataFrame:
        p, o = ("Home", "Away") if is_home else ("Away", "Home")
        res_win = "H" if is_home else "A"
        res_loss = "A" if is_home else "H"
        out = pd.DataFrame({
            "Division": df["Division"],
            "team": df[f"{p}Team"],
            "gf": df[f"FT{p}"], "ga": df[f"FT{o}"],
            "shots": df[f"{p}Shots"], "target": df[f"{p}Target"], "corners": df[f"{p}Corners"],
            "cards": df[f"{p}Yellow"].fillna(0) + df[f"{p}Red"].fillna(0), "fouls": df[f"{p}Fouls"],
            "total": df["FTHome"] + df["FTAway"],
        })
        out["win"] = (df["FTResult"] == res_win).astype(int)
        out["draw"] = (df["FTResult"] == "D").astype(int)
        out["loss"] = (df["FTResult"] == res_loss).astype(int)
        return out

    long = pd.concat([side(True), side(False)], ignore_index=True)

    rows = []
    for team, g in long.groupby("team"):
        n = len(g)
        if n < MIN_MATCHES:
            continue
        div = g["Division"].mode().iloc[0]  # championnat principal de l'équipe
        name, flag = DIV.get(str(div), (str(div), "🏳️"))
        pts = (3 * g["win"].sum() + g["draw"].sum()) / n

        def pm(col):
            return round(float(g[col].mean()), 2) if g[col].notna().any() else None

        rows.append({
            "team": str(team), "league": name, "flag": flag, "matches": int(n),
            "ppm": round(float(pts), 2),
            "gf_pm": round(float(g["gf"].mean()), 2), "ga_pm": round(float(g["ga"].mean()), 2),
            "win_pct": _pct(g["win"] == 1), "draw_pct": _pct(g["draw"] == 1), "loss_pct": _pct(g["loss"] == 1),
            "over25_pct": _pct(g["total"] > 2.5),
            "shots_pm": pm("shots"), "target_pm": pm("target"), "corners_pm": pm("corners"),
            "cards_pm": pm("cards"), "fouls_pm": pm("fouls"),
        })

    rows.sort(key=lambda r: r["ppm"], reverse=True)
    payload = {
        "source": "club-football-match-data (Kaggle), depuis 2019",
        "note": "Statistiques par équipe des cinq grands championnats (par match). Cliquez les en-têtes pour trier.",
        "min_matches": MIN_MATCHES,
        "teams": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} équipes -> {OUT.name}")
    print("meilleur ppm:", rows[0]["team"], rows[0]["ppm"], "| plus de buts:", max(rows, key=lambda r: r['gf_pm'])["team"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
