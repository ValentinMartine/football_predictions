"""Données financières des clubs Big Five, jointes aux noms d'équipes du projet :

- Transfermarkt : valeur marchande totale de l'effectif, taille d'effectif, âge moyen.
- Capology : masse salariale annuelle brute (montants bruts en euros embarqués dans la page).

Sortie : data/team_market.json {équipe: {value_meur, squad, avg_age, payroll_meur}}.
Scraping léger (5 pages par source), best-effort : en cas d'échec, le fichier existant
est conservé.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

# saison du projet (convention pipeline : « 2025 » = saison 2025-26, bascule en août)
SEASON = date.today().year if date.today().month >= 8 else date.today().year - 1

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "team_market.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/team_market.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TM_LEAGUES = {
    "GB1": "premier-league", "ES1": "laliga", "IT1": "serie-a",
    "L1": "bundesliga", "FR1": "ligue-1",
}
CAP_LEAGUES = ["uk/premier-league", "es/la-liga", "it/serie-a", "de/1-bundesliga", "fr/ligue-1"]

# alias nom source -> nom du projet (Understat/football-data)
ALIASES = {
    "manchester city": "manchester city", "manchester united": "manchester united",
    "tottenham hotspur": "tottenham", "wolverhampton wanderers": "wolverhampton wanderers",
    "brighton and hove albion": "brighton", "west ham united": "west ham",
    "newcastle united": "newcastle united", "nottingham forest": "nottingham forest",
    "afc bournemouth": "bournemouth", "leeds united": "leeds",
    "bayern munich": "bayern munich", "bayer 04 leverkusen": "bayer leverkusen",
    "borussia monchengladbach": "borussia m.gladbach", "borussia dortmund": "borussia dortmund",
    "eintracht frankfurt": "eintracht frankfurt", "vfb stuttgart": "vfb stuttgart",
    "1.fsv mainz 05": "mainz 05", "fsv mainz 05": "mainz 05",
    "atletico de madrid": "atletico madrid", "real betis balompie": "real betis",
    "espanyol barcelona": "espanyol",
    "athletic bilbao": "athletic", "celta de vigo": "celta vigo",
    "deportivo alaves": "alaves", "rcd espanyol barcelona": "espanyol",
    "psg": "paris saint germain",
    # abréviations football-data.co.uk (table bigfive)
    "man city": "manchester city", "man united": "manchester united",
    "paris sg": "paris saint germain", "dortmund": "borussia dortmund",
    "nottm forest": "nottingham forest", "sociedad": "real sociedad",
    "ein frankfurt": "eintracht frankfurt", "betis": "real betis",
    "ath bilbao": "athletic", "ath madrid": "atletico madrid",
    "wolves": "wolverhampton wanderers", "leverkusen": "bayer leverkusen",
    "espanol": "espanyol", "st pauli": "st pauli", "celta": "celta vigo",
    "paris saint-germain": "paris saint germain", "olympique marseille": "marseille",
    "olympique lyon": "lyon", "olympique lyonnais": "lyon", "as monaco": "monaco", "losc lille": "lille",
    "stade rennais": "rennes", "rc strasbourg alsace": "strasbourg",
    "as roma": "roma", "ac milan": "ac milan", "inter milan": "inter",
    "juventus fc": "juventus", "ss lazio": "lazio", "ssc napoli": "napoli",
    "acf fiorentina": "fiorentina", "torino fc": "torino", "hellas verona": "verona",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = s.replace("&amp;", "and").replace("&", "and").replace("-", " ").replace(".", "").replace("'", "")
    s = s.replace("munchen", "munich").replace("monchengladbach", "mgladbach")
    s = s.replace("hamburger", "hamburg").replace("brestois", "brest").replace("rennais", "rennes")
    s = s.replace("koln", "cologne").replace("1fc", "fc").replace("1fsv", "fsv")
    s = re.sub(r"\b(fc|cf|afc|ssc|ss|ac|as|sc|club de futbol|cd|vfl|vfb|rcd|us|rc|rb|ud|sv|fsv|"
               r"stade|calcio|bc|cfc|ogc|aj|sco|ca|hellas|balompie|de futbol|sporting|club|barcelona b)\b", " ", s)
    s = re.sub(r"\b(18|19|20)\d{2}\b", " ", s)  # années de fondation (1907, 1909...)
    s = re.sub(r"\b\d{1,2}\b", " ", s)  # numéros résiduels (05, 29...)
    return re.sub(r"\s+", " ", s).strip()


def _get(url: str, tries: int = 3) -> str:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (i + 1))
    raise last


def _meur(txt: str) -> float | None:
    """'€1.44bn' -> 1440.0 ; '€850.00m' -> 850.0 ; '€900k' -> 0.9"""
    m = re.match(r"€([\d.]+)(bn|m|k)", txt.strip())
    if not m:
        return None
    v = float(m.group(1))
    return round(v * {"bn": 1000, "m": 1, "k": 0.001}[m.group(2)], 1)


def fetch_transfermarkt() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for code, slug in TM_LEAGUES.items():
        try:
            html = _get(f"https://www.transfermarkt.com/{slug}/startseite/wettbewerb/{code}/plus/?saison_id={SEASON}")
        except Exception as exc:  # noqa: BLE001
            print(f"  TM {code}: échec ({exc})")
            continue
        # bloc <tr> par club : nom (title du lien hauptlink), nombres, valeurs €
        n0 = len(out)
        for block in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            if "hauptlink" not in block:
                continue
            name_m = re.search(r'title="([^"]+)"', block)
            euros = re.findall(r"€[\d.]+(?:bn|m|k)", block)
            nums = re.findall(r'<td class="zentriert">(?:\s*<a[^>]*>)?([\d.,]+)', block)
            if not name_m or not euros:
                continue
            name = name_m.group(1)
            out[norm(name)] = {
                "tm_name": name,
                "squad": int(float(nums[0].replace(",", "."))) if nums else None,
                "avg_age": float(nums[1].replace(",", ".")) if len(nums) > 1 else None,
                "value_meur": _meur(euros[-1]),  # dernier € du bloc = valeur totale
            }
        print(f"  TM {code}: {len(out) - n0} clubs")
        time.sleep(1.5)
    return out


def fetch_capology() -> dict[str, float]:
    out: dict[str, float] = {}
    for path in CAP_LEAGUES:
        try:
            html = _get(f"https://www.capology.com/{path}/payrolls/{SEASON}-{SEASON + 1}/")
        except Exception as exc:  # noqa: BLE001
            print(f"  Capology {path}: échec ({exc})")
            continue
        i = html.find("var data = [")
        if i < 0:
            print(f"  Capology {path}: tableau introuvable")
            continue
        j = html.find("];", i)
        chunk = html[i:j]
        n0 = len(out)
        for entry in chunk.split("},"):
            name_m = re.search(r"/club/[a-z0-9-]+/salaries/[^']*'[^>]*>(?:<img[^>]*>)?\s*([^<]+?)\s*</a>", entry)
            eur_m = re.search(r'"annual_gross_eur":\s*accounting\.formatMoney\("(\d+)"', entry)
            if name_m and eur_m:
                out[norm(name_m.group(1))] = round(int(eur_m.group(1)) / 1e6, 1)
        print(f"  Capology {path}: {len(out) - n0} clubs")
        time.sleep(1.5)
    return out


def main() -> int:
    try:
        tm = fetch_transfermarkt()
        cap = fetch_capology()
    except Exception as exc:  # noqa: BLE001
        print(f"scraping échoué, fichier conservé : {exc}")
        return 0

    # jointure sur les noms d'équipes du projet : team_power (Understat) + bigfive_team_stats
    # (club-football-match-data, noms différents ex. « Paris SG ») pour couvrir les 2 tables du site
    teams_src = json.loads((ROOT / "data" / "team_power.json").read_text(encoding="utf-8"))
    project_teams = [t["team"] for t in teams_src.get("teams", [])]
    bf_path = ROOT / "data" / "bigfive_team_stats.json"
    if bf_path.exists():
        bf = json.loads(bf_path.read_text(encoding="utf-8"))
        seen = set(project_teams)
        for t in (bf.get("teams") or []):
            if t["team"] not in seen:  # chaque nom exact reçoit sa clé (les 2 tables du site)
                project_teams.append(t["team"])
                seen.add(t["team"])

    def find(entries: dict, team: str):
        n = ALIASES.get(norm(team), norm(team))
        if n in entries:
            return entries[n]
        for k, v in entries.items():
            ka = ALIASES.get(k, k)
            # inclusion uniquement si la partie courte est assez longue (évite Paris FC ⊂ PSG)
            if ka == n or (min(len(n), len(ka)) >= 9 and (n in ka or ka in n)):
                return v
        # repli : recouvrement de tokens (>= 60 % du plus court), interdit sur les noms
        # à un seul token (sinon « Paris FC » absorberait « Paris Saint Germain »)
        nt = set(n.split())
        best, best_s = None, 0.0
        for k, v in entries.items():
            kt = set(ALIASES.get(k, k).split())
            if min(len(nt), len(kt)) < 2:
                continue
            score = len(nt & kt) / min(len(nt), len(kt))
            if score > best_s:
                best, best_s = v, score
        return best if best_s >= 0.6 else None

    merged, missing = {}, []
    for team in project_teams:
        tmv = find(tm, team)
        capv = find(cap, team)
        if tmv is None and capv is None:
            missing.append(team)
            continue
        merged[team] = {
            "value_meur": tmv.get("value_meur") if tmv else None,
            "squad": tmv.get("squad") if tmv else None,
            "avg_age": tmv.get("avg_age") if tmv else None,
            "payroll_meur": capv if isinstance(capv, (int, float)) else None,
        }

    payload = {"source": "Transfermarkt (valeurs) + Capology (salaires bruts annuels, EUR)",
               "teams": merged}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"team_market.json : {len(merged)}/{len(project_teams)} équipes"
          + (f" | non jointes : {', '.join(missing[:8])}" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
