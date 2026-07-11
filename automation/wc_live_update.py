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

CLUBS = Path(__file__).resolve().parents[1]
PERSO = CLUBS.parent
SITE = PERSO / "valentinmartine"
WORLDCUP = PERSO / "worldcup_2026_predictions"
SITE_DATA = SITE / "public" / "data"
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

WC_TO_SITE = {
    "predictions.json": "worldcup_predictions.json",
    "wc_bracket.json": "wc_bracket.json",
    "wc_montecarlo.json": "wc_montecarlo.json",
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
    run(["git", "push", "-q"], repo)
    log(f"  [{repo.name}] poussé : {message}")


def main() -> int:
    log("=== Mise à jour Coupe du Monde (live) ===")
    try:
        run([sys.executable, "scripts/download_match_data.py"], WORLDCUP)
        run([sys.executable, "scripts/patch_wc_results_from_sofascore.py"], WORLDCUP, check=False)
        run([sys.executable, "scripts/train_and_backtest.py"], WORLDCUP)
        run([sys.executable, "-m", "src.export"], WORLDCUP)
        run([sys.executable, "scripts/build_wc_bracket.py"], WORLDCUP)
        run([sys.executable, "scripts/montecarlo_wc.py"], WORLDCUP)
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
