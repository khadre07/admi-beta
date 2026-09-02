"""Les départements ne sont plus figés dans le code : ils sont modifiables et
persistés. Les modules qui ont fait `from .config import DEPARTEMENTS` à l'import
doivent voir les changements — d'où la mutation sur place de la liste."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import config
from admi.data import Database


@pytest.fixture(autouse=True)
def restore_departements():
    """Chaque test repart des 8 départements d'usine."""
    original = [dict(d) for d in config.DEPARTEMENTS]
    yield
    config.set_departements(original)


def test_set_departements_mutates_the_shared_list_in_place():
    avant = config.DEPARTEMENTS  # référence gardée par les autres modules
    config.set_departements([{"id": "mm", "nom": "Menuiserie Métallique",
                              "court": "MM", "couleur": "#7C83FD"}])
    assert config.DEPARTEMENTS is avant  # même objet : les imports restent valides
    assert [d["id"] for d in config.DEPARTEMENTS] == ["mm"]


def test_set_departements_refreshes_lookups():
    config.set_departements([{"id": "mm", "nom": "Menuiserie Métallique",
                              "court": "MM", "couleur": "#123456"}])
    assert config.dep("mm")["nom"] == "Menuiserie Métallique"
    assert config.DEPT_COLOR["mm"] == "#123456"
    assert "am" not in config.DEPT_BY_ID  # l'ancien département a disparu


def test_dep_falls_back_on_an_unknown_id():
    d = config.dep("inconnu")
    assert d["nom"] == "inconnu" and d["court"] == "inconnu"


def test_new_dept_id_is_a_slug_of_the_name():
    assert config.new_dept_id("Menuiserie Métallique", []) == "menuiserie"
    assert config.new_dept_id("Articles Ménagers", []) == "articlesme"


def test_new_dept_id_is_unique():
    assert config.new_dept_id("Peinture", ["peinture"]) == "peinture1"
    assert config.new_dept_id("Peinture", ["peinture", "peinture1"]) == "peinture2"


def test_new_dept_id_falls_back_when_the_name_has_no_letters():
    assert config.new_dept_id("///", []) == "dept"


def test_reset_departements_restores_the_eight_defaults():
    config.set_departements([{"id": "mm", "nom": "M", "court": "MM", "couleur": "#111111"}])
    config.reset_departements()
    assert [d["id"] for d in config.DEPARTEMENTS] == [
        "am", "ond", "pt", "chi", "sac", "sl", "adm", "srv"]


def test_saved_departements_survive_a_reload(tmp_path, monkeypatch):
    """Au démarrage suivant, la liste personnalisée doit remplacer celle d'usine."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'depts.db'}")
    from admi import data, db as dbmod
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_tables", {})
    monkeypatch.setattr(dbmod, "_meta", dbmod.MetaData())

    base = data.load_db()  # premier lancement : amorçage des données de démo
    base.settings["departements"] = [
        *[dict(d) for d in config.DEPARTEMENTS],
        {"id": "mm", "nom": "Menuiserie Métallique", "court": "MM", "couleur": "#A855F7"},
    ]
    data.save_settings(base)

    config.reset_departements()  # on simule un redémarrage à froid
    assert "mm" not in config.DEPT_BY_ID

    data.load_db()
    assert config.dep("mm")["court"] == "MM"
    assert config.DEPT_COLOR["mm"] == "#A855F7"


def test_admin_adds_a_department_that_survives_a_restart(app):
    """Parcours réel : Paramètres → nouveau département → il est proposé partout."""
    from admi import data

    app.sidebar.radio[0].set_value("Paramètres").run()
    next(t for t in app.text_input if t.label == "Nom complet").set_value("Menuiserie Métallique")
    next(t for t in app.text_input if t.label == "Code court").set_value("MM")
    next(b for b in app.button
         if "Enregistrer le département" in (b.label or "")).click().run()
    assert not app.exception, [str(e.value) for e in app.exception]

    assert config.dep("menuiserie")["court"] == "MM"

    config.reset_departements()  # redémarrage à froid
    data.load_db()
    assert config.dep("menuiserie")["court"] == "MM", "le département doit être persisté"

    app.sidebar.radio[0].set_value("Tableau de bord").run()
    assert "Menuiserie Métallique" in app.selectbox(key="dash_dept").options, \
        "le nouveau département doit être proposé dans les filtres du tableau de bord"


def test_deleting_a_used_department_warns_and_can_be_cancelled(app):
    """Le garde-fou du HTML : on annonce combien d'enregistrements sont concernés."""
    app.sidebar.radio[0].set_value("Paramètres").run()
    app.selectbox(key="dept_cible").set_value("am").run()

    app.button(key="dept_del").click().run()
    assert any("Confirmez la suppression" in w.value for w in app.error)
    assert any("utilisent ce département" in w.value for w in app.warning)

    app.button(key="dept_del_no").click().run()
    assert "am" in config.DEPT_BY_ID, "annuler ne doit rien supprimer"


def test_dept_usage_counts_every_record_type():
    db = Database()
    db.machines.append({"id": "m1", "departementId": "am"})
    db.arrets.append({"id": "a1", "departementId": "am"})
    db.energie.append({"id": "e1", "departementId": "am"})
    db.interventions.append({"id": "i1", "departementId": "am"})
    db.planning.append({"id": "p1", "departementId": "am"})
    db.pieces.append({"id": "pc1", "departementId": "am"})
    db.machines.append({"id": "m2", "departementId": "chi"})
    assert db.dept_usage("am") == 6
    assert db.dept_usage("chi") == 1
    assert db.dept_usage("sl") == 0
