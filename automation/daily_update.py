"""
Mise à jour quotidienne complète des prédictions sportives + déploiement.

1. Pipeline clubs (téléchargement -> ré-entraînement/export -> stats -> drapeaux ->
   compos clubs + autres championnats via Sofascore -> logos -> normalisation -> sync).
2. Tennis ATP (dépôt tennis-predictions), copié vers le site par son propre export.
   La Coupe du Monde, terminée le 19/07/2026, n'est plus régénérée : ses données restent figées.
3. Échecs (chess-predictions) et tennis de table (table-tennis-predictions, réentraînement contrôlé le lundi).
4. fftt-ping et ffe-echecs : mise à jour complète le lundi, résultats du week-end (ping) samedi et dimanche.
5. Copie vers le site des JSON et des pages Paris IX, puis commit + push UNIQUEMENT des données (pas le code).
   Vercel redéploie automatiquement au push du site.

Planifié via le Planificateur de tâches Windows (tâche « VM Daily Predictions Update »).
NB : une tâche planifiée ne tourne que PC ALLUMÉ. Les workflows GitHub Actions servaient de relais
PC éteint ; bloqués par la facturation depuis octobre 2026, ils ne sont plus nécessaires.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
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
CHESS = PERSO / "chess-predictions"
TT = PERSO / "table-tennis-predictions"
FFTT = PERSO / "fftt-ping"
FFE = PERSO / "ffe-echecs"
# Bash de Git explicitement : dans une tâche planifiée, « bash » peut désigner celui de WSL.
BASH = r"C:\Program Files\Git\bin\bash.exe"
MODELE_TT = ("lgbm_model.pkl", "lgbm_metrics.json", "model_metrics.json")
FICHIERS_TT = ("tt_matches.db", "lgbm_model.pkl", "model_metrics.json", "lgbm_metrics.json",
               "lgbm_shap_importance.csv", "lgbm_calibration.csv", "lgbm_calibration_report.json",
               "elo_baseline_metrics.json", "predictions.json")
LOG_DIR = CLUBS / "automation" / "logs"
AUTHOR_EMAIL = "212414673+ValentinMartine@users.noreply.github.com"
AUTHOR_NAME = "ValentinMartine"

# Une étape Sofascore bloquée a gardé la tâche active plus de 11 heures le 30/09/2026.
DELAI_ETAPE = 45 * 60
# La mise à jour complète de fftt-ping prend plusieurs heures.
DELAI_HEBDO = 8 * 3600
# Tâche lancée sans fenêtre : une demande d'identifiants git attendrait indéfiniment.
ENV_GIT = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "PYTHONIOENCODING": "utf-8"}

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"daily_{datetime.now():%Y%m%d}.log"


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], cwd: Path, check: bool = True, delai: int = DELAI_ETAPE) -> subprocess.CompletedProcess:
    """Exécute une commande, journalise sa sortie. Lève si check et code non nul, ou au-delà du délai."""
    # Sortie dans un fichier, pas dans un tuyau : un petit-enfant orphelin (uc_driver.exe de
    # seleniumbase) gardait le tuyau ouvert et bloquait la tâche deux jours (02/10/2026).
    with tempfile.TemporaryFile() as sortie:
        try:
            res = subprocess.run(cmd, cwd=cwd, stdout=sortie, stderr=subprocess.STDOUT, timeout=delai, env=ENV_GIT)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"délai de {delai} s dépassé : {' '.join(cmd)}") from exc
        sortie.seek(0)
        texte = sortie.read().decode("utf-8", errors="replace")
    for ln in texte.splitlines():
        if ln.strip():
            log(f"    {ln}")
    if check and res.returncode != 0:
        raise RuntimeError(f"échec ({res.returncode}) : {' '.join(cmd)}")
    return res


def commit_and_push(repo: Path, path_spec: str | list[str], message: str) -> None:
    """Committe/pousse les chemins de données seulement s'ils ont changé ({jour} : date du jour)."""
    if not repo.exists():
        log(f"  [{repo.name}] dépôt introuvable, ignoré")
        return
    chemins = [path_spec] if isinstance(path_spec, str) else path_spec
    chemins = [c for c in chemins if (repo / c).exists()]
    message = message.replace("{jour}", f"{datetime.now():%Y-%m-%d}")
    status = subprocess.run(["git", "status", "--porcelain", "--", *chemins],
                            cwd=repo, capture_output=True, text=True) if chemins else None
    if status is None or not status.stdout.strip():
        log(f"  [{repo.name}] aucun changement de données")
        return
    run(["git", "add", "--", *chemins], repo)
    run(["git", "-c", f"user.email={AUTHOR_EMAIL}", "-c", f"user.name={AUTHOR_NAME}",
         "commit", "-q", "-m", message], repo)
    if not _push_resilient(repo):
        return
    log(f"  [{repo.name}] données poussées : {message}")


def _push_resilient(repo: Path) -> bool:
    """Pousse ; si l'origine a avancé, rebase en gardant NOS données (les plus fraîches).
    En cas d'échec du rebase, on l'abandonne proprement et on réessaiera au prochain run."""
    # Toute sortie de git passe par run() : écrite sur la sortie d'erreur héritée, elle coupait la tâche.
    if run(["git", "push", "-q"], repo, check=False).returncode == 0:
        return True
    run(["git", "fetch", "origin", "-q"], repo, check=False)
    # --autostash : un fichier modifié non commité (travail en cours) ne bloque plus le rebase.
    rb = run(["git", "rebase", "--autostash", "-X", "theirs", "@{u}"], repo, check=False)
    if rb.returncode != 0:
        run(["git", "rebase", "--abort"], repo, check=False)
        log(f"  [{repo.name}] push rejeté, non résolu, réessai au prochain run")
        return False
    if run(["git", "push", "-q"], repo, check=False).returncode != 0:
        log(f"  [{repo.name}] push refusé après rebase")
        return False
    return True


def python_de(repo: Path) -> str:
    venv = repo / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def etape(nom: str, commandes: list[tuple[list[str], Path]], delai: int = DELAI_ETAPE) -> bool:
    """Enchaîne des commandes ; un échec est journalisé sans arrêter la mise à jour des autres projets."""
    try:
        for cmd, cwd in commandes:
            run(cmd, cwd, delai=delai)
        log(f"  {nom} : fait")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"  {nom} ignoré (non bloquant) : {exc}")
        return False


def maj_tennis_de_table(lundi: bool) -> bool:
    py = python_de(TT)
    if not lundi:
        return etape("Tennis de table (prédictions)", [
            ([py, "scripts/predict_upcoming.py", "--days", "7", "--model", "lgbm"], TT),
            ([py, "-m", "src.export"], TT)])
    # Lundi : reprise du workflow « autonomie » (données, réentraînement contrôlé, prédictions).
    for cmd in (["scripts/fetch_wtt_rankings.py"], ["scripts/fetch_ittf_rankings.py"]):
        run([py, *cmd], TT, check=False)
    prod = {f: (TT / "data" / f).read_bytes() for f in MODELE_TT if (TT / "data" / f).exists()}
    ok = etape("Tennis de table (collecte et réentraînement)", [
        ([py, "scripts/run_scraper.py", "--days", "10", "--priority", "2"], TT),
        ([py, "scripts/train_model.py", "--model", "lgbm", "--shap"], TT)])
    sauvegarde = TT / "data" / "_lgbm_metrics_production.json"
    if ok and "lgbm_metrics.json" in prod:
        sauvegarde.write_bytes(prod["lgbm_metrics.json"])
        gate = run([py, "scripts/eval_gate.py", "--candidate", "data/lgbm_metrics.json", "--baseline",
                    str(sauvegarde), "--metric", "log_loss", "--tolerance", "0.005"], TT, check=False)
        sauvegarde.unlink()
        if gate.returncode != 0:
            log("  Tennis de table : candidat rejeté (régression du log loss), modèle de production conservé")
            for f, contenu in prod.items():
                (TT / "data" / f).write_bytes(contenu)
    return etape("Tennis de table (prédictions)", [
        ([py, "scripts/predict_upcoming.py", "--days", "7", "--model", "lgbm"], TT),
        ([py, "scripts/backtest.py", "--real-odds-only"], TT),
        ([py, "-m", "src.export"], TT)])


def copier_json(source: Path, cible: Path) -> None:
    """Copie seulement un JSON lisible : un fichier tronqué ne doit pas partir sur le site."""
    if not source.exists():
        log(f"  copie ignorée, absent : {source}")
        return
    json.loads(source.read_text(encoding="utf-8"))
    shutil.copyfile(source, cible)


def copier_pages_paris9() -> None:
    # Mêmes garde-fous que le workflow du site : seule la version publique (niveau équipe, sans nom ni licence)
    # est copiée ; la page nominative a quitté le site le 06/10/2026. Tout est refusé au moindre doute.
    publique = FFTT / "publique"
    dest = SITE / "public/projects/pronostics-paris9"
    index = (publique / "index.html").read_text(encoding="utf-8")
    if '"public": true' not in index or '"lic":' in index:
        raise RuntimeError("index.html de fftt-ping n'est pas la version publique : copie refusée")
    poules = sorted((publique / "france").iterdir()) if (publique / "france").is_dir() else []
    for f in poules:
        if not re.fullmatch(r"(clubs|tournois|\d{3}[0-9A-Z])\.json", f.name):
            raise RuntimeError(f"france/{f.name} : nom de fichier inattendu")
        contenu = f.read_text(encoding="utf-8")
        if '"lic"' in contenu:
            raise RuntimeError(f"france/{f.name} refusé : licence présente")
        json.loads(contenu)
    if poules and not (publique / "france" / "clubs.json").exists():
        raise RuntimeError("france/clubs.json absent")
    shutil.copyfile(publique / "index.html", dest / "index.html")
    if poules:
        shutil.rmtree(dest / "france", ignore_errors=True)
        shutil.copytree(publique / "france", dest / "france")


def synchroniser_site() -> None:
    donnees = SITE / "public" / "data"
    copies = [(CHESS / "data/predictions.json", donnees / "chess_predictions.json"),
              (TT / "data/predictions.json", donnees / "tt_predictions.json")]
    copies += [(TENNIS / "data" / f, donnees / f) for f in ("tennis_predictions_wta.json", "tennis_elo_history_wta.json")]
    for source, cible in copies:
        try:
            copier_json(source, cible)
        except Exception as exc:  # noqa: BLE001
            log(f"  copie vers le site refusée ({source.name}) : {exc}")
    try:
        copier_pages_paris9()
    except Exception as exc:  # noqa: BLE001
        log(f"  pages Paris IX non copiées : {exc}")


def maj_hebdo_ping_echecs(jour: int) -> None:
    """fftt-ping et ffe-echecs : lundi, mise à jour complète ; samedi et dimanche, résultats du week-end (ping)."""
    if jour == 0:
        if etape("fftt-ping (mise à jour complète)", [([BASH, "tableau_de_bord/mise_a_jour.sh"], FFTT)],
                 delai=DELAI_HEBDO):
            commit_and_push(FFTT, ["archives", "publique", "tableau_de_bord"], "chore(data): tableau de bord du {jour}")
        etape("ffe-echecs (mise à jour complète)", [([BASH, "mise_a_jour.sh"], FFE)], delai=DELAI_HEBDO)
        commit_and_push(FFE, ["interclubs", "interclubs.html"],
                        "chore(data): interclubs du {jour}")
    elif jour in (5, 6):
        # Pas de restauration du cache, à la différence du workflow : donnees/ reste sur le PC d'une exécution à l'autre.
        if etape("fftt-ping (résultats du week-end)", [
                ([BASH, "tableau_de_bord/resultats_week_end.sh", "2"], FFTT)], delai=DELAI_HEBDO):
            commit_and_push(FFTT, ["publique/france", "archives/france"], "chore(data): toutes les poules, résultats du {jour}")


def main() -> int:
    log("=== Début mise à jour quotidienne ===")
    try:
        log("Pipeline clubs (download -> export -> stats -> flags -> compos + autres ligues -> logos -> sync)...")
        run([sys.executable, "scripts/update_pipeline.py"], CLUBS)

        log("Tennis ATP et WTA (download -> calendrier -> patch Sofascore -> train -> export)...")
        try:
            for tour in ("atp", "wta"):
                run([sys.executable, "scripts/download_data.py", tour], TENNIS)
            run([sys.executable, "scripts/fetch_upcoming.py"], TENNIS, check=False)
            for tour in ("atp", "wta"):
                run([sys.executable, "scripts/download_sackmann_stats.py", tour, "--from-year", "2000"], TENNIS,
                    check=False)
            run([sys.executable, "scripts/patch_results_from_sofascore.py"], TENNIS, check=False)
            for tour in ("atp", "wta"):
                run([sys.executable, "scripts/train_and_backtest.py", tour], TENNIS)
                run([sys.executable, "scripts/validate_exports.py", tour], TENNIS)
            # Signaux d'actualité jugés par Nimble (Ollama local) : affichés à côté des prédictions.
            run([sys.executable, "scripts/signaux_actualite.py"], TENNIS, check=False)
            run([sys.executable, "-m", "src.export"], TENNIS)  # copie aussi vers le site
            log("  Tennis régénéré + copié vers le site")
        except Exception as exc:  # noqa: BLE001
            log(f"  Tennis ignoré (non bloquant) : {exc}")

        # Échecs et tennis de table ne tournaient que sur GitHub Actions, bloqué par la facturation en octobre 2026.
        etape("Échecs", [([python_de(CHESS), "-m", "chess_src.export"], CHESS)])
        jour = datetime.now().weekday()
        maj_tennis_de_table(lundi=jour == 0)

        today = f"{datetime.now():%Y-%m-%d}"
        commit_and_push(CLUBS, "data", f"chore(data): mise à jour quotidienne clubs ({today})")
        commit_and_push(TENNIS, "data", f"chore(data): mise à jour quotidienne tennis ({today})")
        commit_and_push(CHESS, "data", f"chore(data): mise à jour quotidienne échecs ({today})")
        commit_and_push(TT, [f"data/{f}" for f in FICHIERS_TT], f"chore(data): mise à jour tennis de table ({today})")

        # Ping et échecs par équipes en dernier : la mise à jour du lundi prend plusieurs heures.
        maj_hebdo_ping_echecs(jour)
        synchroniser_site()
        commit_and_push(SITE, ["public/data", "public/projects/pronostics-paris9"],
                        f"chore(data): rafraîchissement quotidien du site ({today})")

        log("=== Fin : succès ===")
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"ERREUR: {exc}")
        log("=== Fin : échec ===")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
