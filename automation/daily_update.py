"""
Mise à jour quotidienne complète des prédictions sportives + déploiement.

1. Pipeline clubs (téléchargement -> ré-entraînement/export -> stats -> drapeaux ->
   compos clubs + autres championnats via Sofascore -> logos -> normalisation -> sync).
2. Tennis ATP (dépôt tennis-predictions), copié vers le site par son propre export.
   La Coupe du Monde, terminée le 19/07/2026, n'est plus régénérée : ses données restent figées.
3. Commit + push UNIQUEMENT des données (pas le code) sur les trois dépôts.
   Vercel redéploie automatiquement au push du site.

Planifié via le Planificateur de tâches Windows (tâche « VM Daily Predictions Update »).
NB : une tâche planifiée ne tourne que PC ALLUMÉ. Pour l'autonomie PC éteint, ce sont
les workflows GitHub Actions (cloud) qui prennent le relais.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Sortie robuste sous Windows (cp1252) : évite les crashs d'encodage sur la sortie
# des sous-processus contenant des caractères non cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CLUBS = Path(__file__).resolve().parents[1]
PERSO = CLUBS.parent
SITE = PERSO / "valentinmartine"
TENNIS = PERSO / "tennis-predictions"
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

# Une étape Sofascore bloquée a gardé la tâche active plus de 11 heures le 30/09/2026.
DELAI_ETAPE = 45 * 60
# Tâche lancée sans fenêtre : une demande d'identifiants git attendrait indéfiniment.
ENV_GIT = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"daily_{datetime.now():%Y%m%d}.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path, check: bool = True, delai: int = DELAI_ETAPE) -> subprocess.CompletedProcess:
    """Exécute une commande, journalise sa sortie. Lève si check et code non nul, ou au-delà du délai."""
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=delai, env=ENV_GIT)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"délai de {delai} s dépassé : {' '.join(cmd)}") from exc
    for stream in (res.stdout, res.stderr):
        for ln in (stream or "").splitlines():
            if ln.strip():
                log(f"    {ln}")
    if check and res.returncode != 0:
        raise RuntimeError(f"échec ({res.returncode}) : {' '.join(cmd)}")
    return res


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
    if not _push_resilient(repo):
        return
    log(f"  [{repo.name}] données poussées : {message}")


def _push_resilient(repo: Path) -> bool:
    """Pousse ; si l'origine a avancé, rebase en gardant NOS données (les plus fraîches).
    En cas d'échec du rebase, on l'abandonne proprement et on réessaiera au prochain run."""
    if subprocess.run(["git", "push", "-q"], cwd=repo, env=ENV_GIT).returncode == 0:
        return True
    subprocess.run(["git", "fetch", "origin", "-q"], cwd=repo, env=ENV_GIT)
    # --autostash : un fichier modifié non commité (travail en cours) ne bloque plus le rebase.
    rb = subprocess.run(["git", "rebase", "--autostash", "-X", "theirs", "@{u}"], cwd=repo,
                        capture_output=True, text=True)
    if rb.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=repo)
        log(f"  [{repo.name}] push rejeté, non résolu — réessai au prochain run")
        return False
    if subprocess.run(["git", "push", "-q"], cwd=repo, env=ENV_GIT).returncode != 0:
        return False
    return True


def main() -> int:
    log("=== Début mise à jour quotidienne ===")
    try:
        log("Pipeline clubs (download -> export -> stats -> flags -> compos + autres ligues -> logos -> sync)...")
        run([sys.executable, "scripts/update_pipeline.py"], CLUBS)

        log("Tennis ATP (download -> patch Sofascore Grands Chelems -> train -> export)...")
        try:
            run([sys.executable, "scripts/download_data.py"], TENNIS)
            run([sys.executable, "scripts/patch_results_from_sofascore.py"], TENNIS, check=False)
            run([sys.executable, "scripts/train_and_backtest.py"], TENNIS)
            run([sys.executable, "-m", "src.export"], TENNIS)  # copie aussi vers le site
            log("  Tennis régénéré + copié vers le site")
        except Exception as exc:  # noqa: BLE001
            log(f"  Tennis ignoré (non bloquant) : {exc}")

        today = f"{datetime.now():%Y-%m-%d}"
        commit_and_push(CLUBS, "data", f"chore(data): mise à jour quotidienne clubs ({today})")
        commit_and_push(TENNIS, "data", f"chore(data): mise à jour quotidienne tennis ({today})")
        commit_and_push(SITE, "public/data", f"chore(data): rafraîchissement quotidien du site ({today})")

        log("=== Fin : succès ===")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"ERREUR: {exc}")
        log("=== Fin : échec ===")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
