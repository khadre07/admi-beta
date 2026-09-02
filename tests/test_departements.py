"""Les départements ne sont plus figés dans le code : ils sont modifiables et
persistés. Les modules qui ont fait `from .config import DEPARTEMENTS` à l'import
doivent voir les changements — d'où la mutation sur place de la liste."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import config, data
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


def test_a_new_department_gets_a_colour_nobody_else_uses():
    """Deux départements de la même couleur rendent les graphiques illisibles."""
    utilisees = [d["couleur"] for d in config.DEPARTEMENTS]
    proposee = config.new_dept_color(utilisees)
    assert proposee not in utilisees
    assert config.new_dept_color(utilisees + [proposee]) not in utilisees + [proposee]


def test_the_colour_proposed_is_stable():
    """Même liste, même proposition : pas de couleur tirée au hasard."""
    assert config.new_dept_color([]) == config.new_dept_color([])
    assert config.new_dept_color([]) == config.DEPARTEMENTS_DEFAUT[0]["couleur"]


def test_the_palette_never_runs_out():
    fantaisie = [f"#{i:06X}" for i in range(400)]
    assert config.new_dept_color(fantaisie).startswith("#")


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


def _boutons(app, key):
    return [b for b in app.button if getattr(b, "key", None) == key]


def test_the_dashboard_lets_an_admin_add_a_department(app):
    """Le filtre du tableau de bord ne sert à rien si le département n'existe pas
    encore : on doit pouvoir l'ajouter sans aller dans Paramètres."""
    bouton = [b for b in app.button if "Nouveau département" in (b.label or "")]
    assert bouton, "un raccourci d'ajout doit accompagner le filtre du tableau de bord"
    bouton[0].click().run()
    assert not app.exception, [str(e.value) for e in app.exception]


def test_the_dashboard_shortcut_is_reserved_to_admins(app):
    from admi import auth
    auth.create_user("lecteur", "lecteur", "viewer")
    next(b for b in app.button if "Se déconnecter" in (b.label or "")).click().run()
    app.text_input[0].set_value("lecteur")
    app.text_input[1].set_value("lecteur")
    app.button[0].click().run()

    assert not [b for b in app.button if "Nouveau département" in (b.label or "")], \
        "un lecteur ne crée pas de département"


def test_the_form_proposes_a_free_colour_for_a_new_department(app):
    app.sidebar.radio[0].set_value("Paramètres").run()
    assert app.selectbox(key="dept_cible").value == "__new__"
    proposee = app.color_picker[0].value
    assert proposee.upper() not in {d["couleur"].upper() for d in config.DEPARTEMENTS}


def test_deleting_a_used_department_is_refused(app):
    """Supprimer un département utilisé rendrait ses enregistrements orphelins :
    ils resteraient en base mais sortiraient de tous les graphiques."""
    app.sidebar.radio[0].set_value("Paramètres").run()
    app.selectbox(key="dept_cible").set_value("am").run()

    assert not _boutons(app, "dept_del"), "pas de bouton de suppression sur un département utilisé"
    messages = " ".join(e.value for e in app.error)
    assert "Suppression impossible" in messages
    assert "machine" in messages, "le message dit ce qui bloque, type par type"
    assert "am" in config.DEPT_BY_ID


def test_an_unused_department_can_be_deleted(app):
    """Un département qu'aucun enregistrement n'utilise se supprime normalement."""
    app.sidebar.radio[0].set_value("Paramètres").run()
    next(t for t in app.text_input if t.label == "Nom complet").set_value("Menuiserie Métallique")
    next(t for t in app.text_input if t.label == "Code court").set_value("MM")
    next(b for b in app.button
         if "Enregistrer le département" in (b.label or "")).click().run()
    assert "menuiserie" in config.DEPT_BY_ID

    app.selectbox(key="dept_cible").set_value("menuiserie").run()
    _boutons(app, "dept_del")[0].click().run()
    _boutons(app, "dept_del_ok")[0].click().run()
    assert "menuiserie" not in config.DEPT_BY_ID
    assert not app.exception, [str(e.value) for e in app.exception]


def test_resetting_is_refused_while_a_custom_department_is_in_use(app):
    """Réinitialiser supprime les départements ajoutés : même garde-fou."""
    from admi.data import load_db, upsert_record

    app.sidebar.radio[0].set_value("Paramètres").run()
    next(t for t in app.text_input if t.label == "Nom complet").set_value("Menuiserie Métallique")
    next(t for t in app.text_input if t.label == "Code court").set_value("MM")
    next(b for b in app.button
         if "Enregistrer le département" in (b.label or "")).click().run()

    db = load_db()
    upsert_record(db, "machines", {**db.machines[0], "departementId": "menuiserie"})
    app.run()

    _boutons(app, "dept_reset")[0].click().run()
    assert not _boutons(app, "dept_reset_ok"), "pas de confirmation possible tant que c'est utilisé"
    assert any("Menuiserie Métallique" in e.value for e in app.error)
    assert "menuiserie" in config.DEPT_BY_ID


def test_add_departement_creates_persists_and_picks_a_free_colour(tmp_path, monkeypatch):
    """Un seul chemin d'ajout, partagé par Paramètres et le tableau de bord."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ajout.db'}")
    from admi import data, db as dbmod
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_tables", {})
    monkeypatch.setattr(dbmod, "_meta", dbmod.MetaData())

    base = data.load_db()
    ok, nouveau = data.add_departement(base, "  Menuiserie Métallique ", "mm")
    assert ok
    assert nouveau["id"] == "menuiserie" and nouveau["court"] == "MM"
    assert nouveau["couleur"] not in [d["couleur"] for d in config.DEPARTEMENTS_DEFAUT]
    assert config.dep("menuiserie")["nom"] == "Menuiserie Métallique"

    config.reset_departements()  # redémarrage à froid
    data.load_db()
    assert "menuiserie" in config.DEPT_BY_ID, "l'ajout doit être persisté"


def test_add_departement_refuses_an_incomplete_form():
    ok, msg = data.add_departement(Database(), "   ", "MM")
    assert not ok and "requis" in msg
    ok, msg = data.add_departement(Database(), "Menuiserie", " ")
    assert not ok and "requis" in msg


def test_dept_usage_detail_says_what_blocks_the_deletion():
    db = Database()
    db.machines += [{"id": "m1", "departementId": "am"}, {"id": "m2", "departementId": "am"}]
    db.arrets.append({"id": "a1", "departementId": "am"})
    db.pieces.append({"id": "p1", "departementId": "chi"})
    assert db.dept_usage_detail("am") == {"machines": 2, "arrets": 1}
    assert db.dept_usage_detail("sl") == {}


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
