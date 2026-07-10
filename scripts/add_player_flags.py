"""
Ajoute le drapeau de nationalité à chaque joueur des classements (understat_stats.json),
en récupérant la nationalité via FBref (soccerdata) et en la mappant en emoji drapeau.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import soccerdata as sd

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "data" / "understat_stats.json"
LEAGUES = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]

# Nations britanniques : pas d'ISO alpha-2 valide -> emoji « tag sequence » dédié.
SUBDIVISION_FLAGS = {
    "ENG": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",  # Angleterre
    "SCO": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",  # Écosse
    "WAL": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",  # Pays de Galles
}

# Code FIFA/FBref (3 lettres) -> ISO 3166-1 alpha-2 (pour l'emoji drapeau)
FIFA2ISO = {
    "NIR": "GB", "FRA": "FR", "ESP": "ES", "GER": "DE",
    "ITA": "IT", "POR": "PT", "NED": "NL", "BEL": "BE", "BRA": "BR", "ARG": "AR", "URU": "UY",
    "COL": "CO", "CHI": "CL", "ECU": "EC", "PER": "PE", "PAR": "PY", "VEN": "VE", "MEX": "MX",
    "USA": "US", "CAN": "CA", "CRO": "HR", "SRB": "RS", "SUI": "CH", "AUT": "AT", "DEN": "DK",
    "SWE": "SE", "NOR": "NO", "POL": "PL", "UKR": "UA", "CZE": "CZ", "SVK": "SK", "HUN": "HU",
    "TUR": "TR", "GRE": "GR", "RUS": "RU", "IRL": "IE", "ISL": "IS", "FIN": "FI", "ROU": "RO",
    "BUL": "BG", "SVN": "SI", "BIH": "BA", "ALB": "AL", "MKD": "MK", "MNE": "ME", "KVX": "XK",
    "EGY": "EG", "MAR": "MA", "ALG": "DZ", "TUN": "TN", "SEN": "SN", "CIV": "CI", "NGA": "NG",
    "GHA": "GH", "CMR": "CM", "MLI": "ML", "GUI": "GN", "GAB": "GA", "COD": "CD", "COG": "CG",
    "BFA": "BF", "TOG": "TG", "BEN": "BJ", "ZAM": "ZM", "ANG": "AO", "CPV": "CV", "GAM": "GM",
    "JPN": "JP", "KOR": "KR", "AUS": "AU", "IRN": "IR", "KSA": "SA", "QAT": "QA", "UZB": "UZ",
    "CHN": "CN", "JAM": "JM", "CRC": "CR", "HON": "HN", "PAN": "PA", "GEO": "GE", "ARM": "AM",
    "ISR": "IL", "NZL": "NZ", "LUX": "LU", "MDA": "MD", "CYP": "CY", "NCL": "NC",
}


def _iso_to_emoji(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _nation_code(val) -> str | None:
    if not isinstance(val, str) or not val.strip():
        return None
    tokens = [t for t in val.replace("-", " ").split() if t.isalpha()]
    for t in reversed(tokens):
        if len(t) == 3 and t.isupper():
            return t
    return tokens[-1].upper()[:3] if tokens else None


def main() -> None:
    try:
        fb = sd.FBref(leagues=LEAGUES, seasons="2025")
        ps = fb.read_player_season_stats(stat_type="standard").reset_index()
    except Exception as exc:
        _restore_tracked_stats()
        print(f"FBref indisponible, conservation du fichier versionné : {exc}")
        return
    ps.columns = [c[0] if isinstance(c, tuple) else c for c in ps.columns]

    name_to_flag: dict[str, str] = {}
    surname_flag: dict[str, str] = {}
    surname_dupe: set[str] = set()
    for _, r in ps.iterrows():
        code = _nation_code(r.get("nation"))
        flag = SUBDIVISION_FLAGS.get(code) if code else None
        if not flag:
            iso = FIFA2ISO.get(code) if code else None
            if not iso:
                continue
            flag = _iso_to_emoji(iso)
        n = _norm(r["player"])
        name_to_flag[n] = flag
        toks = n.split()
        if toks:
            key = toks[-1]
            if key in surname_flag and surname_flag[key] != flag:
                surname_dupe.add(key)
            surname_flag[key] = flag

    def lookup(name: str) -> str | None:
        n = _norm(name)
        if n in name_to_flag:
            return name_to_flag[n]
        toks = n.split()
        if toks and toks[-1] not in surname_dupe:
            return surname_flag.get(toks[-1])
        return None

    stats = json.loads(STATS.read_text(encoding="utf-8"))
    hit = tot = 0
    for lst in ("top_scorers", "top_assists", "top_xg", "top_xa"):
        for p in stats.get(lst, []):
            tot += 1
            f = lookup(p["player"])
            if f:
                p["flag"] = f
                hit += 1
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"drapeaux ajoutés : {hit}/{tot} entrées joueurs ({len(name_to_flag)} joueurs FBref mappés)")


def _restore_tracked_stats() -> None:
    try:
        content = subprocess.check_output(
            ["git", "show", "HEAD:data/understat_stats.json"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        return
    STATS.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
