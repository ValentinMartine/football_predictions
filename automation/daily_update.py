"""
Mise à jour quotidienne des prédictions sportives + déploiement.

Exécute le pipeline du projet clubs (téléchargement -> ré-entraînement/export ->
stats -> drapeaux -> compos -> forme des joueurs en sélection -> synchro site),
puis committe et pousse UNIQUEMENT les données générées (pas le code) sur les deux
dépôts. Vercel redéploie automatiquement au push du site.

Planifié via le Planificateur de tâches Windows (tâche « VM Daily Predictions Update »).
Lancé sans dépendance PowerShell pour éviter tout souci de politique d'exécution.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

CLUBS = Path(__file__).resolve().parents[1]
PERSO = CLUBS.parent
SITE = PERSO / "valentinmartine"
WORLDCUP = PERSO / "worldcup_2026_predictions"
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"daily_{datetime.now():%Y%m%d}.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Exécute une commande, journalise sa sortie, lève si code non nul."""
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for stream in (res.stdout, res.stderr):
        for ln in (stream or "").splitlines():
            if ln.strip():
                log(f"    {ln}")
    if res.returncode != 0:
        raise RuntimeError(f"échec ({res.returncode}) : {' '.join(cmd)}")
    return res


def commit_and_push(repo: Path, path_spec: str, message: str) -> None:
    """Committe/pousse le sous-dossier de données seulement s'il a changé."""
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
        log("Pipeline clubs (download -> export -> stats -> flags -> compos -> forme -> O/U -> sync)...")
        run([sys.executable, "scripts/update_pipeline.py"], CLUBS)

        # Coupe du Monde : cotes + prédictions à venir (non bloquant ; écrit wc_odds.json côté site)
        try:
            run([sys.executable, "scripts/fetch_wc_odds.py"], WORLDCUP)
            run([sys.executable, "scripts/predict_wc_upcoming.py"], WORLDCUP)
            run([sys.executable, "scripts/build_wc_bracket.py"], WORLDCUP)
            log("  Coupe du Monde : cotes + prédictions rafraîchies")
        except Exception as exc:  # noqa: BLE001
            log(f"  Coupe du Monde ignorée (non bloquant) : {exc}")

        today = f"{datetime.now():%Y-%m-%d}"
        commit_and_push(CLUBS, "data", f"chore(data): mise à jour quotidienne des prédictions ({today})")
        commit_and_push(SITE, "public/data", f"chore(data): rafraîchissement quotidien des données du site ({today})")

        log("=== Fin : succès ===")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"ERREUR: {exc}")
        log("=== Fin : échec ===")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
