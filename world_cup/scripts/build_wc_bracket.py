"""
Construit le bracket (tableau à élimination directe) de la Coupe du Monde 2026 pour un
affichage radial sur le site. Reconstruit l'arbre par identité des vainqueurs (robuste,
sans deviner l'ordre officiel) : R16 -> ses deux matchs de R32 nourriciers.

Le tournoi étant en cours, on va jusqu'au tour le plus récent joué (8es de finale).
Sortie : data/wc_bracket.json (+ copie vers le site).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "wc_bracket.json"
SITE = Path("C:/Users/valen/Documents/Projets/Projets_Informatiques/Perso/valentinmartine/public/data/wc_bracket.json")

# Fenêtres de dates (identifiées à partir des données : R32 = 16 matchs, R16 = 8 matchs).
R32_RANGE = ("2026-06-28", "2026-07-03")
R16_RANGE = ("2026-07-04", "2026-07-07")

ISO2 = {
    "Algeria": "DZ", "Argentina": "AR", "Australia": "AU", "Austria": "AT", "Belgium": "BE",
    "Bosnia and Herzegovina": "BA", "Brazil": "BR", "Canada": "CA", "Cape Verde": "CV",
    "Colombia": "CO", "Croatia": "HR", "DR Congo": "CD", "Ecuador": "EC", "Egypt": "EG",
    "England": "EN", "France": "FR", "Germany": "DE", "Ghana": "GH", "Ivory Coast": "CI",
    "Japan": "JP", "Mexico": "MX", "Morocco": "MA", "Netherlands": "NL", "Norway": "NO",
    "Paraguay": "PY", "Portugal": "PT", "Senegal": "SN", "South Africa": "ZA", "Spain": "ES",
    "Sweden": "SE", "Switzerland": "CH", "United States": "US",
}


def flag(country: str) -> str:
    iso = ISO2.get(country)
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso) if iso else "🏳️"


def main() -> int:
    wm = json.loads((ROOT / "data" / "predictions.json").read_text(encoding="utf-8"))["wc_matches"]

    def winner(m):
        w = m.get("actual_decisive_winner")
        if w:
            return w
        try:
            h, a = map(int, m["actual_score"].split("-"))
            return m["home"] if h > a else (m["away"] if a > h else None)
        except Exception:
            return None

    r32 = [m for m in wm if R32_RANGE[0] <= m["date"] <= R32_RANGE[1]]
    r16 = [m for m in wm if R16_RANGE[0] <= m["date"] <= R16_RANGE[1]]

    def feeder(team):
        for m in r32:
            if team in (m["home"], m["away"]) and winner(m) == team:
                return m
        return None

    teams, r32_nodes, r16_nodes = [], [], []
    for rm in r16:
        for team in (rm["home"], rm["away"]):
            fm = feeder(team)
            if fm is None:
                continue
            w = winner(fm)
            teams.append({"name": fm["home"], "flag": flag(fm["home"]), "advanced": w == fm["home"]})
            teams.append({"name": fm["away"], "flag": flag(fm["away"]), "advanced": w == fm["away"]})
            r32_nodes.append({"winner": w, "flag": flag(w)})
        rw = winner(rm)
        r16_nodes.append({"winner": rw, "flag": flag(rw), "label": f"{rm['home']} {rm['actual_score']} {rm['away']}"})

    qf_matches = [m for m in wm if m.get("stage") == "quarter_final"]
    sf_matches = [m for m in wm if m.get("stage") == "semi_final"]
    final_matches = [m for m in wm if m.get("stage") == "final"]

    qf_nodes = []
    for k in range(4):
        t1 = r16_nodes[2*k]["winner"] if 2*k < len(r16_nodes) else None
        t2 = r16_nodes[2*k+1]["winner"] if 2*k+1 < len(r16_nodes) else None
        qf_match = None
        if t1 and t2:
            for m in qf_matches:
                if {m["home"], m["away"]} == {t1, t2}:
                    qf_match = m
                    break
        if qf_match:
            qw = winner(qf_match)
            qf_nodes.append({"winner": qw, "flag": flag(qw) if qw else None, "label": f"{qf_match['home']} {qf_match['actual_score']} {qf_match['away']}" if qf_match.get("actual_score") else None})
        else:
            qf_nodes.append({"winner": None, "flag": None})

    sf_nodes = []
    for k in range(2):
        t1 = qf_nodes[2*k]["winner"] if 2*k < len(qf_nodes) else None
        t2 = qf_nodes[2*k+1]["winner"] if 2*k+1 < len(qf_nodes) else None
        sf_match = None
        if t1 and t2:
            for m in sf_matches:
                if {m["home"], m["away"]} == {t1, t2}:
                    sf_match = m
                    break
        if sf_match:
            sw = winner(sf_match)
            sf_nodes.append({"winner": sw, "flag": flag(sw) if sw else None, "label": f"{sf_match['home']} {sf_match['actual_score']} {sf_match['away']}" if sf_match.get("actual_score") else None})
        else:
            sf_nodes.append({"winner": None, "flag": None})

    winner_node = None
    t1 = sf_nodes[0]["winner"] if len(sf_nodes) > 0 else None
    t2 = sf_nodes[1]["winner"] if len(sf_nodes) > 1 else None
    final_match = None
    if t1 and t2:
        for m in final_matches:
            if {m["home"], m["away"]} == {t1, t2}:
                final_match = m
                break
    if final_match:
        fw = winner(final_match)
        winner_node = {"winner": fw, "flag": flag(fw) if fw else None}

    payload = {
        "stage_reached": "Huitièmes de finale (8es)",
        "note": "Bracket réel de la Coupe du Monde 2026 jusqu'au tour le plus récent joué.",
        "teams": teams,
        "r32": r32_nodes,
        "r16": r16_nodes,
        "qf": qf_nodes,
        "sf": sf_nodes,
        "winner": winner_node
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if SITE.parent.exists():
        SITE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"bracket : {len(teams)} équipes, {len(r32_nodes)} R32, {len(r16_nodes)} R16, {len(qf_nodes)} QF, {len(sf_nodes)} SF -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
