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
    monkeypatch.setattr(du, "maj_tennis_de_table", lambda lundi: True)
    monkeypatch.setattr(du, "maj_hebdo_ping_echecs", lambda jour: None)
    monkeypatch.setattr(du, "synchroniser_site", lambda: None)
    du.main()
    tennis = [(c, chk) for c, cwd, chk in appels if cwd == du.TENNIS]
    noms = [c for c, _ in tennis]
    assert noms.index("scripts/signaux_actualite.py") < noms.index("src.export")
    assert ("scripts/signaux_actualite.py", False) in tennis


def _depot_en_retard(tmp_path):
    import subprocess

    def git(*args, cwd):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
                       capture_output=True)

    origine = tmp_path / "origine.git"
    git("init", "-q", "--bare", "-b", "main", str(origine), cwd=tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        git("clone", "-q", str(origine), str(d), cwd=tmp_path)
    (a / "x.txt").write_text("1")
    git("add", ".", cwd=a); git("commit", "-q", "-m", "1", cwd=a); git("push", "-q", "origin", "HEAD:main", cwd=a)
    git("pull", "-q", "origin", "main", cwd=b)
    (b / "y.txt").write_text("distant")
    git("add", ".", cwd=b); git("commit", "-q", "-m", "2", cwd=b); git("push", "-q", cwd=b)
    (a / "z.txt").write_text("local")
    git("add", ".", cwd=a); git("commit", "-q", "-m", "3", cwd=a)
    git("branch", "-q", "--set-upstream-to=origin/main", cwd=a)
    return a


def test_push_rejete_n_ecrit_rien_sur_la_sortie_d_erreur(tmp_path, monkeypatch, capfd):
    # Du 06 au 27/10/2026, le rejet du push écrit par git sur la sortie d'erreur héritée a coupé la tâche :
    # l'enveloppe PowerShell (ErrorActionPreference Stop, 2>&1) le prend pour une erreur fatale.
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    depot = _depot_en_retard(tmp_path)
    assert du._push_resilient(depot)
    assert capfd.readouterr().err == ""


def test_enveloppe_powershell_ne_s_arrete_pas_sur_la_sortie_d_erreur():
    enveloppe = (Path(du.__file__).parent / "run_daily_update_hidden.ps1").read_text(encoding="utf-8")
    assert '$ErrorActionPreference = "Continue"' in enveloppe


def _sans_effet(monkeypatch, tmp_path):
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    appels = []
    monkeypatch.setattr(du, "run", lambda cmd, cwd, check=True, delai=0: appels.append((cmd, cwd, delai)))
    commits = []
    monkeypatch.setattr(du, "commit_and_push", lambda repo, chemins, msg: commits.append((repo, chemins)))
    return appels, commits


def test_main_met_a_jour_echecs_et_tennis_de_table(tmp_path, monkeypatch):
    # Échecs et tennis de table ne tournaient que sur GitHub Actions, bloqué par la facturation en octobre 2026.
    appels, commits = _sans_effet(monkeypatch, tmp_path)
    monkeypatch.setattr(du, "maj_tennis_de_table", lambda lundi: appels.append((["tt"], du.TT, 0)))
    monkeypatch.setattr(du, "maj_hebdo_ping_echecs", lambda jour: None)
    monkeypatch.setattr(du, "synchroniser_site", lambda: None)
    du.main()
    depots = {cwd for _, cwd, _ in appels}
    assert {du.CHESS, du.TT, du.TENNIS} <= depots
    assert {du.CHESS, du.TT, du.SITE} <= {r for r, _ in commits}
    wta = [c for c, cwd, _ in appels if cwd == du.TENNIS and "wta" in c]
    assert any("train_and_backtest.py" in " ".join(c) for c in wta)


def test_ping_et_echecs_le_lundi_resultats_du_week_end(tmp_path, monkeypatch):
    appels, commits = _sans_effet(monkeypatch, tmp_path)
    du.maj_hebdo_ping_echecs(0)
    assert [cwd for _, cwd, _ in appels] == [du.FFTT, du.FFE]
    assert all(delai == du.DELAI_HEBDO for _, _, delai in appels)
    appels.clear()
    du.maj_hebdo_ping_echecs(5)
    assert [c[-2] for c, _, _ in appels] == ["tableau_de_bord/resultats_week_end.sh"]
    appels.clear()
    du.maj_hebdo_ping_echecs(2)
    assert appels == []


def test_pages_paris9_refusees_si_page_publique_nominative(tmp_path, monkeypatch):
    publique = tmp_path / "fftt" / "publique"
    publique.mkdir(parents=True)
    (publique / "index.html").write_text('{"public": true, "lic": "123"}', encoding="utf-8")
    monkeypatch.setattr(du, "FFTT", tmp_path / "fftt")
    monkeypatch.setattr(du, "SITE", tmp_path / "site")
    with pytest.raises(RuntimeError, match="publique"):
        du.copier_pages_paris9()


def test_json_illisible_jamais_copie_vers_le_site(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    source, cible = tmp_path / "p.json", tmp_path / "site.json"
    source.write_text('{"tronqué": ', encoding="utf-8")
    cible.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        du.copier_json(source, cible)
    assert cible.read_text(encoding="utf-8") == "{}"


def test_candidat_tennis_de_table_rejete_restaure_le_modele(tmp_path, monkeypatch):
    import types

    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    monkeypatch.setattr(du, "TT", tmp_path)
    (tmp_path / "data").mkdir()
    for f in du.MODELE_TT:
        (tmp_path / "data" / f).write_text("production", encoding="utf-8")

    def run(cmd, cwd, check=True, delai=0):
        if "train_model.py" in cmd:
            for f in du.MODELE_TT:
                (tmp_path / "data" / f).write_text("candidat", encoding="utf-8")
        return types.SimpleNamespace(returncode=1 if "scripts/eval_gate.py" in cmd else 0)

    monkeypatch.setattr(du, "run", run)
    du.maj_tennis_de_table(lundi=True)
    assert {(tmp_path / "data" / f).read_text(encoding="utf-8") for f in du.MODELE_TT} == {"production"}
    assert not (tmp_path / "data" / "_lgbm_metrics_production.json").exists()


def test_commit_avec_plusieurs_chemins(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "LOG_FILE", tmp_path / "journal.log")
    depot = _depot_en_retard(tmp_path)
    (depot / "data").mkdir()
    (depot / "data" / "a.json").write_text("{}")
    (depot / "pages").mkdir()
    (depot / "pages" / "b.html").write_text("x")
    (depot / "brouillon.txt").write_text("ne pas committer")
    du.commit_and_push(depot, ["data", "pages", "absent"], "chore(data): essai du {jour}")
    import subprocess
    suivis = subprocess.run(["git", "ls-files"], cwd=depot, capture_output=True, text=True).stdout.split()
    assert {"data/a.json", "pages/b.html"} <= set(suivis) and "brouillon.txt" not in suivis
    dernier = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=depot, capture_output=True, text=True).stdout
    assert "{jour}" not in dernier


def _paris9(tmp_path, monkeypatch, fichiers):
    publique = tmp_path / "fftt" / "publique"
    (publique / "france").mkdir(parents=True)
    (publique / "index.html").write_text('{"public": true}', encoding="utf-8")
    for nom, contenu in fichiers.items():
        (publique / "france" / nom).write_text(contenu, encoding="utf-8")
    site = tmp_path / "site" / "public/projects/pronostics-paris9"
    (site / "france").mkdir(parents=True)
    (site / "france" / "ancien.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(du, "FFTT", tmp_path / "fftt")
    monkeypatch.setattr(du, "SITE", tmp_path / "site")
    return site


def test_pages_paris9_publique_et_toutes_les_poules(tmp_path, monkeypatch):
    # Depuis le 06/10/2026, aucune page avec les noms des joueurs n'est publiée sur le site.
    site = _paris9(tmp_path, monkeypatch, {"clubs.json": "{}", "0101.json": '{"poule": 1}',
                                         "319D.json": "{}", "tournois.json": "[]"})
    du.copier_pages_paris9()
    assert (site / "index.html").read_text(encoding="utf-8") == '{"public": true}'
    assert sorted(p.name for p in (site / "france").iterdir()) == ["0101.json", "319D.json", "clubs.json", "tournois.json"]
    assert not (tmp_path / "site" / "public" / "pronostics-paris9-255e79ed").exists()


def test_poules_refusees_au_moindre_doute(tmp_path, monkeypatch):
    for fichiers in ({"clubs.json": "{}", "0101.json": '{"lic": "1"}'}, {"clubs.json": "{}", "notes.txt": "x"},
                     {"0101.json": "{}"}):
        site = _paris9(tmp_path, monkeypatch, fichiers)
        with pytest.raises(RuntimeError):
            du.copier_pages_paris9()
        assert [p.name for p in (site / "france").iterdir()] == ["ancien.json"]
        import shutil
        shutil.rmtree(tmp_path / "fftt"); shutil.rmtree(tmp_path / "site")
