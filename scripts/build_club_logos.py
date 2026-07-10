"""Complète data/club_logos.json (nom d'équipe -> URL de logo) via l'API gratuite
de TheSportsDB, la même source que les logos déjà présents (r2.thesportsdb.com).

Rassemble tous les noms d'équipes affichés sur le site (team_power, standings,
bigfive_team_stats, other_leagues) et ne requête que ceux sans logo. Les noms sont
normalisés / désabrégés (carte ALIASES + expansions) pour améliorer la correspondance,
et un logo n'est retenu que si la correspondance de nom est suffisamment fiable.

Idempotent : relançable, il ne réinterroge pas les équipes déjà résolues.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOGOS = DATA / "club_logos.json"
REPORT = DATA / "club_logos_unmatched.json"
API = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
SLEEP = 1.6  # respect du rate limit de la clé gratuite (espacement large = moins de faux négatifs)

# Noms abrégés/source -> requête plus proche du nom officiel pour TheSportsDB.
ALIASES = {
    "Atlanta Utd": "Atlanta United", "New York City": "New York City FC",
    "Newells Old Boys": "Newell's Old Boys", "Velez Sarsfield": "Velez Sarsfield",
    "Estudiantes L.P.": "Estudiantes de La Plata", "Argentinos Jrs": "Argentinos Juniors",
    "Arsenal Sarandi": "Arsenal de Sarandi", "Central Cordoba": "Central Cordoba de Santiago",
    "Nottm Forest": "Nottingham Forest", "West Brom": "West Bromwich Albion",
    "MGladbach": "Borussia Monchengladbach", "Sheffield United": "Sheffield United",
    "Fortuna Dusseldorf": "Fortuna Dusseldorf", "Greuther Furth": "Greuther Furth",
    "Paris SG": "Paris Saint-Germain", "Man United": "Manchester United",
    "Man City": "Manchester City", "Wolves": "Wolverhampton Wanderers",
    "Spurs": "Tottenham Hotspur", "Inter": "Inter Milan", "Betis": "Real Betis",
    "Sociedad": "Real Sociedad", "Ath Bilbao": "Athletic Bilbao", "Ath Madrid": "Atletico Madrid",
    "Vallecano": "Rayo Vallecano", "La Coruna": "Deportivo La Coruna",
}

# Expansions d'abréviations courantes (mot entier).
EXPAND = {
    r"\bUtd\b": "United", r"\bJrs\b": "Juniors", r"\bDep\b": "Deportivo",
    r"\bAtl\b": "Atletico", r"\bSp\b": "Sporting", r"\bCA\b": "Club Atletico",
}


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def norm(s: str) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def query_name(name: str) -> str:
    if name in ALIASES:
        return ALIASES[name]
    q = name
    for pat, rep in EXPAND.items():
        q = re.sub(pat, rep, q)
    return re.sub(r"\s+L\.?P\.?$", "", q).strip()


def tokens(s: str) -> set:
    return set(norm(s).split())


def match_score(query: str, team: dict) -> float:
    nq = norm(query)
    cand = [team.get("strTeam", ""), team.get("strTeamAlternate", "") or ""]
    best = 0.0
    for c in cand:
        nc = norm(c)
        if not nc:
            continue
        if nc == nq:
            return 1.0
        tq, tc = tokens(query), tokens(c)
        if tq and tc:
            jac = len(tq & tc) / len(tq | tc)
            if nq in nc or nc in nq:
                jac = max(jac, 0.7)
            best = max(best, jac)
    return best


def _fetch(q: str, session: requests.Session) -> list:
    """Requête l'API avec un retry sur réponse vide (rate limit transitoire)."""
    for attempt in range(2):
        try:
            r = session.get(API, params={"t": q}, timeout=25)
            data = r.json() if r.status_code == 200 else {}
        except Exception:
            data = {}
        teams = [t for t in (data.get("teams") or []) if t.get("strSport") == "Soccer"]
        if teams:
            return teams
        time.sleep(1.5 * (attempt + 1))
    return []


def search_badge(name: str, session: requests.Session) -> str | None:
    # Plusieurs variantes de requête, du plus précis au plus large.
    variants = []
    for v in (query_name(name), name, " ".join(name.split()[:2])):
        if v and v not in variants:
            variants.append(v)
    for q in variants:
        teams = _fetch(q, session)
        if not teams:
            continue
        scored = sorted(((match_score(q, t), t) for t in teams), key=lambda x: x[0], reverse=True)
        score, best = scored[0]
        if score >= 0.5 and best.get("strBadge"):  # sinon on préfère aucun logo à un mauvais
            return best["strBadge"]
    return None


def gather_names() -> set:
    names: set[str] = set()

    def add(x):
        if x and isinstance(x, str):
            names.add(x.strip())

    for fname, extract in [
        ("team_power.json", lambda d: [t.get("team") for t in (d.get("teams") or [])]),
        ("bigfive_team_stats.json", lambda d: [t.get("team") for t in (d.get("teams") or d)]),
    ]:
        p = DATA / fname
        if p.exists():
            for n in extract(json.loads(p.read_text(encoding="utf-8"))):
                add(n)

    st = DATA / "standings.json"
    if st.exists():
        data = json.loads(st.read_text(encoding="utf-8"))
        for country in data.values():
            for rows in (country.get("seasons") or {}).values():
                for row in rows:
                    add(row.get("team"))
    return names


def main() -> int:
    logos = json.loads(LOGOS.read_text(encoding="utf-8")) if LOGOS.exists() else {}
    have_norm = {norm(k) for k in logos}
    names = gather_names()
    todo = sorted(n for n in names if n not in logos and norm(n) not in have_norm)
    print(f"{len(names)} équipes au total, {len(todo)} sans logo à résoudre.")

    session = requests.Session()
    session.headers.update({"User-Agent": "valentinmartine-logo-fetcher/1.0"})
    found, unmatched = 0, []
    for i, name in enumerate(todo, 1):
        badge = search_badge(name, session)
        if badge:
            logos[name] = badge
            found += 1
        else:
            unmatched.append(name)
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} — {found} trouvés, {len(unmatched)} sans correspondance")
            LOGOS.write_text(json.dumps(logos, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(SLEEP)

    LOGOS.write_text(json.dumps(dict(sorted(logos.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT.write_text(json.dumps(sorted(unmatched), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Terminé : {found} nouveaux logos, {len(unmatched)} non résolus (voir {REPORT.name}).")
    print(f"Total logos : {len(logos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
