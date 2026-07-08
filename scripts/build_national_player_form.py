from __future__ import annotations

import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

from scripts.add_player_flags import FIFA2ISO, _nation_code

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "national_player_form.json"
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]
SEASON = "2025"
MINUTES_MIN = 300

FIFA_TO_TEAM = {
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "BRA": "Brazil",
    "CAN": "Canada",
    "CIV": "Côte d'Ivoire",
    "COL": "Colombia",
    "CRO": "Croatia",
    "DEN": "Denmark",
    "ECU": "Ecuador",
    "ENG": "England",
    "ESP": "Spain",
    "FRA": "France",
    "GER": "Germany",
    "GHA": "Ghana",
    "IRN": "IR Iran",
    "ITA": "Italy",
    "JPN": "Japan",
    "KOR": "Korea Republic",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "NED": "Netherlands",
    "NGA": "Nigeria",
    "POL": "Poland",
    "POR": "Portugal",
    "SEN": "Senegal",
    "SRB": "Serbia",
    "SUI": "Switzerland",
    "TUN": "Tunisia",
    "URU": "Uruguay",
    "USA": "USA",
    "WAL": "Wales",
}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(value.lower().split())


def _iso_to_emoji(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(char) - ord("A")) for char in iso)


def _fbref_nations() -> tuple[dict[str, str], dict[str, str], set[str]]:
    fb = sd.FBref(leagues=LEAGUES, seasons=SEASON)
    fbref = fb.read_player_season_stats(stat_type="standard").reset_index()
    fbref.columns = [col[0] if isinstance(col, tuple) else col for col in fbref.columns]

    exact: dict[str, str] = {}
    surname: dict[str, str] = {}
    surname_dupes: set[str] = set()
    for row in fbref.itertuples(index=False):
        code = _nation_code(getattr(row, "nation", None))
        if not code:
            continue
        name = _norm(getattr(row, "player"))
        exact[name] = code
        parts = name.split()
        if not parts:
            continue
        key = parts[-1]
        if key in surname and surname[key] != code:
            surname_dupes.add(key)
        surname[key] = code
    return exact, surname, surname_dupes


def _lookup_nation(player: str, exact: dict[str, str], surname: dict[str, str], dupes: set[str]) -> str | None:
    name = _norm(player)
    if name in exact:
        return exact[name]
    parts = name.split()
    if parts and parts[-1] not in dupes:
        return surname.get(parts[-1])
    return None


def main() -> None:
    exact, surname, dupes = _fbref_nations()
    understat = sd.Understat(leagues=LEAGUES, seasons=SEASON)
    players = understat.read_player_season_stats().reset_index()
    players = players[players["minutes"] >= MINUTES_MIN].copy()
    players["fifa_code"] = players["player"].map(lambda name: _lookup_nation(name, exact, surname, dupes))
    players = players.dropna(subset=["fifa_code"]).copy()

    rows = []
    for code, group in players.groupby("fifa_code"):
        top = group.sort_values(["xg", "minutes"], ascending=False).head(12)
        iso = FIFA2ISO.get(code)
        rows.append({
            "fifa_code": code,
            "team": FIFA_TO_TEAM.get(code),
            "flag": _iso_to_emoji(iso) if iso else None,
            "players": int(len(group)),
            "minutes": int(group["minutes"].sum()),
            "goals": int(group["goals"].sum()),
            "assists": int(group["assists"].sum()),
            "xg": round(float(group["xg"].sum()), 2),
            "xa": round(float(group["xa"].sum()), 2),
            "xg_xa": round(float(group["xg"].sum() + group["xa"].sum()), 2),
            "top_players": [
                {
                    "player": str(row.player),
                    "team": str(row.team),
                    "minutes": int(row.minutes),
                    "goals": int(row.goals),
                    "assists": int(row.assists),
                    "xg": round(float(row.xg), 2),
                    "xa": round(float(row.xa), 2),
                }
                for row in top.itertuples(index=False)
            ],
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Understat player season stats + FBref nationalities via soccerdata",
        "season": "2025-2026",
        "coverage": "Players in Big Five leagues with at least 300 minutes.",
        "limitations": (
            "This is a national-player-pool proxy, not an official national-team roster. "
            "It must be joined to official squad lists before it is used as a prediction feature."
        ),
        "n_players_matched": int(len(players)),
        "countries": sorted(rows, key=lambda row: row["xg_xa"], reverse=True),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"écrit {OUT} ({len(players)} joueurs, {len(rows)} pays)")


if __name__ == "__main__":
    main()
