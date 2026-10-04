import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))

import daily_update as du


def test_chemin_du_depot_tennis():
    # Le dossier s'appelle tennis-predictions : l'ancien nom faisait ignorer le tennis en silence.
    assert du.TENNIS.name == "tennis-predictions"


def test_etape_bloquee_interrompue(tmp_path, monkeypatch):
    # Le 30/09/2026, une étape Sofascore bloquée a gardé la tâche active plus de 11 heures.
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    with pytest.raises(RuntimeError, match="délai"):
        du.run([sys.executable, "-c", "import time; time.sleep(5)"], tmp_path, delai=1)


def test_git_ne_demande_jamais_d_identifiants():
    assert du.ENV_GIT["GIT_TERMINAL_PROMPT"] == "0"


def test_coupe_du_monde_plus_regeneree():
    source = Path(du.__file__).read_text(encoding="utf-8")
    assert "build_wc_bracket" not in source


def test_un_petit_enfant_qui_survit_ne_bloque_pas_l_etape(tmp_path, monkeypatch):
    # Le 02/10/2026, trois uc_driver.exe orphelins du pipeline clubs gardaient la sortie ouverte :
    # la tâche est restée bloquée deux jours après la fin de l'étape.
    import time

    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    petit_enfant = "import time; time.sleep(20)"
    enfant = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {petit_enfant!r}]); "
        "print('étape finie')"
    )
    debut = time.monotonic()
    du.run([sys.executable, "-c", enfant], tmp_path, delai=60)
    assert time.monotonic() - debut < 10
    assert "étape finie" in (tmp_path / "journal.log").read_text(encoding="utf-8")


def test_signaux_actualite_avant_l_export_tennis_et_non_bloquants(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    monkeypatch.setattr(du, "run", lambda cmd, cwd, check=True, delai=0: appels.append((cmd[-1], cwd, check)))
    monkeypatch.setattr(du, "commit_and_push", lambda *a: None)
    du.main()
    tennis = [(c, chk) for c, cwd, chk in appels if cwd == du.TENNIS]
    noms = [c for c, _ in tennis]
    assert noms.index("scripts/signaux_actualite.py") < noms.index("src.export")
    assert ("scripts/signaux_actualite.py", False) in tennis
