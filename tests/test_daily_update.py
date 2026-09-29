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
