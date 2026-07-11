"""
Mise à jour quotidienne complète des prédictions sportives + déploiement.

1. Pipeline clubs (téléchargement -> ré-entraînement/export -> stats -> drapeaux ->
   compos clubs + autres championnats via Sofascore -> logos -> normalisation -> sync).
2. Régénération Coupe du Monde (dépôt séparé) à partir des derniers résultats, puis
   copie des données WC vers le site.
3. Commit + push UNIQUEMENT des données (pas le code) sur les trois dépôts.
   Vercel redéploie automatiquement au push du site.

Planifié via le Planificateur de tâches Windows (tâche « VM Daily Predictions Update »).
NB : une tâche planifiée ne tourne que PC ALLUMÉ. Pour l'autonomie PC éteint, ce sont
les workflows GitHub Actions (cloud) qui prennent le relais.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CLUBS = Path(__file__).resolve().parents[1]
PERSO = CLUBS.parent
SITE = PERSO / "valentinmartine"
WORLDCUP = PERSO / "worldcup_2026_predictions"  # dépôt séparé = source du site
SITE_DATA = SITE / "public" / "data"
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

# fichiers WC (dépôt séparé, data/) -> nom de destination côté site (public/data/)
WC_TO_SITE = {
    "predictions.json": "worldcup_predictions.json",
    "wc_bracket.json": "wc_bracket.json",
    "wc_montecarlo.json": "wc_montecarlo.json",
    "worldcup_lineups.json": "worldcup_lineups.json",
}

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"daily_{datetime.now():%Y%m%d}.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Exécute une commande, journalise sa sortie. Lève si check et code non nul."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for stream in (res.stdout, res.stderr):
        for ln in (stream or "").splitlines():
            if ln.strip():
                log(f"    {ln}")
    if check and res.returncode != 0:
        raise RuntimeError(f"échec ({res.returncode}) : {' '.join(cmd)}")
    return res


def copy_wc_to_site() -> None:
    if not SITE_DATA.exists():
        return
    for src_name, dst_name in WC_TO_SITE.items():
        src = WORLDCUP / "data" / src_name
        if src.exists():
            shutil.copy2(src, SITE_DATA / dst_name)


def commit_and_push(repo: Path, path_spec: str, message: str) -> None:
    """Committe/pousse le sous-dossier de données seulement s'il a changé."""
    if not repo.exists():
        log(f"  [{repo.name}] dépôt introuvable, ignoré")
        return
    status = subprocess.run(["git", "status", "--porcelain", "--", path_spec],
                            cwd=repo, capture_output=True, text=True)
    if not status.stdout.strip():
        log(f"  [{repo.name}] aucun changement de données")
        return
    run(["git", "add", "--", path_spec], repo)
    run(["git", "-c", f"user.email={AUTHOR_EMAIL}", "-c", f"user.name={AUTHOR_NAME}",
         "commit", "-q", "-m", message], repo)
    run(["git", "push", "-q"], repo)
    log(f"  [{repo.name}] données poussées : {message}")


def main() -> int:
    log("=== Début mise à jour quotidienne ===")
    try:
        log("Pipeline clubs (download -> export -> stats -> flags -> compos + autres ligues -> logos -> sync)...")
        run([sys.executable, "scripts/update_pipeline.py"], CLUBS)

        log("Régénération Coupe du Monde (dépôt séparé)...")
        try:
            run([sys.executable, "scripts/download_fifa_rankings.py"], WORLDCUP, check=False)
            run([sys.executable, "scripts/download_match_data.py"], WORLDCUP)
            # Résultats live Sofascore pour les matchs pas encore publiés par martj42 (retard).
            run([sys.executable, "scripts/patch_wc_results_from_sofascore.py"], WORLDCUP, check=False)
            run([sys.executable, "scripts/download_worldcup_metadata.py"], WORLDCUP, check=False)
            run([sys.executable, "scripts/train_and_backtest.py"], WORLDCUP)
            run([sys.executable, "-m", "src.export"], WORLDCUP)
            run([sys.executable, "scripts/build_wc_bracket.py"], WORLDCUP)
            run([sys.executable, "scripts/montecarlo_wc.py"], WORLDCUP)
            run([sys.executable, "scripts/fetch_wc_lineups.py"], WORLDCUP, check=False)  # scraping best-effort
            copy_wc_to_site()
            log("  Coupe du Monde régénérée + copiée vers le site")
        except Exception as exc:  # noqa: BLE001
            log(f"  Coupe du Monde ignorée (non bloquant) : {exc}")

        today = f"{datetime.now():%Y-%m-%d}"
        commit_and_push(CLUBS, "data", f"chore(data): mise à jour quotidienne clubs ({today})")
        commit_and_push(WORLDCUP, "data", f"chore(data): mise à jour quotidienne Coupe du Monde ({today})")
        commit_and_push(SITE, "public/data", f"chore(data): rafraîchissement quotidien du site ({today})")

        log("=== Fin : succès ===")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"ERREUR: {exc}")
        log("=== Fin : échec ===")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
