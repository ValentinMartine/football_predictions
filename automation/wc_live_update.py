"""
Mise à jour LÉGÈRE et fréquente de la Coupe du Monde (toutes les 2 h, tâche planifiée).

Ne fait que la Coupe du Monde : derniers résultats (martj42) + patch Sofascore en direct
-> ré-entraînement rapide -> export -> bracket + Monte Carlo -> copie site -> push.
Bien plus léger que daily_update.py (qui refait aussi clubs + autres championnats une
fois par jour). But : que le site reflète vite les matchs terminés.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Sortie robuste sous Windows (la console/redirection est en cp1252 : évite les crashs
# d'encodage quand la sortie d'un sous-processus contient des caractères non cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CLUBS = Path(__file__).resolve().parents[1]
PERSO = CLUBS.parent
SITE = PERSO / "valentinmartine"
WORLDCUP = CLUBS / "world_cup"  # Coupe du Monde désormais dans le monorepo clubs
SITE_DATA = SITE / "public" / "data"
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

WC_TO_SITE = {
    "predictions.json": "worldcup_predictions.json",
    "wc_bracket.json": "wc_bracket.json",
    "wc_montecarlo.json": "wc_montecarlo.json",
    "worldcup_lineups.json": "worldcup_lineups.json",
}

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"wc_live_{datetime.now():%Y%m%d}.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path, check: bool = True) -> None:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for stream in (res.stdout, res.stderr):
        for ln in (stream or "").splitlines():
            if ln.strip():
                log(f"    {ln}")
    if check and res.returncode != 0:
        raise RuntimeError(f"échec ({res.returncode}) : {' '.join(cmd)}")


def commit_and_push(repo: Path, path_spec: str, message: str) -> None:
    if not repo.exists():
        return
    status = subprocess.run(["git", "status", "--porcelain", "--", path_spec],
                            cwd=repo, capture_output=True, text=True)
    if not status.stdout.strip():
        log(f"  [{repo.name}] aucun changement")
        return
    run(["git", "add", "--", path_spec], repo)
    run(["git", "-c", f"user.email={AUTHOR_EMAIL}", "-c", f"user.name={AUTHOR_NAME}",
         "commit", "-q", "-m", message], repo)
    if not _push_resilient(repo):
        return
    log(f"  [{repo.name}] poussé : {message}")


def _push_resilient(repo: Path) -> bool:
    """Pousse ; si l'origine a avancé, rebase en gardant NOS données (les plus fraîches).
    En cas d'échec du rebase, on l'abandonne proprement (pas de HEAD détaché) et on
    réessaiera au prochain run — jamais de dépôt laissé dans un état cassé."""
    if subprocess.run(["git", "push", "-q"], cwd=repo).returncode == 0:
        return True
    subprocess.run(["git", "fetch", "origin", "-q"], cwd=repo)
    # --autostash : un fichier modifié non commité (travail en cours) ne bloque plus le rebase.
    rb = subprocess.run(["git", "rebase", "--autostash", "-X", "theirs", "@{u}"], cwd=repo,
                        capture_output=True, text=True)
    if rb.returncode != 0:
        subprocess.run(["git", "rebase", "--abort"], cwd=repo)
        log(f"  [{repo.name}] push rejeté, non résolu — réessai au prochain run")
        return False
    if subprocess.run(["git", "push", "-q"], cwd=repo).returncode != 0:
        log(f"  [{repo.name}] push toujours rejeté — réessai au prochain run")
        return False
    return True


def main() -> int:
    log("=== Mise à jour Coupe du Monde (live) ===")
    try:
        run([sys.executable, "scripts/download_match_data.py"], WORLDCUP)
        run([sys.executable, "scripts/patch_wc_results_from_sofascore.py"], WORLDCUP, check=False)
        run([sys.executable, "scripts/train_and_backtest.py"], WORLDCUP)
        run([sys.executable, "-m", "src.export"], WORLDCUP)
        run([sys.executable, "scripts/build_wc_bracket.py"], WORLDCUP)
        run([sys.executable, "scripts/montecarlo_wc.py"], WORLDCUP)
        # Compositions + notes (« ma note » / Sofascore) : scraping best-effort, non bloquant.
        # fetch_wc_lineups copie lui-même worldcup_lineups.json vers le site.
        run([sys.executable, "scripts/fetch_wc_lineups.py"], WORLDCUP, check=False)
        if SITE_DATA.exists():
            for src_name, dst_name in WC_TO_SITE.items():
                src = WORLDCUP / "data" / src_name
                if src.exists():
                    shutil.copy2(src, SITE_DATA / dst_name)
        today = f"{datetime.now():%Y-%m-%d %H:%M}"
        commit_and_push(WORLDCUP, "data", f"chore(data): mise à jour Coupe du Monde ({today})")
        commit_and_push(SITE, "public/data", f"chore(data): rafraîchissement Coupe du Monde ({today})")
        log("=== Fin : succès ===")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"ERREUR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
