"""Base vierge par défaut, et remise à zéro complète depuis Paramètres.

Une application livrée à un client ne doit pas s'ouvrir sur des données
inventées ; et quand on efface tout, ça doit rester effacé au redémarrage.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import config, data


def _boutons(app, key):
    return [b for b in app.button if getattr(b, "key", None) == key]


def test_the_phrase_must_be_written_to_confirm():
    assert data.confirmation_suppression("supprimer la base")
    assert data.confirmation_suppression("  Supprimer La Base  "), "casse et espaces tolérés"
    assert not data.confirmation_suppression("")
    assert not data.confirmation_suppression("oui")
    assert not data.confirmation_suppression("supprimer")


def test_an_admin_can_wipe_everything_from_the_settings(app):
    """Parcours réel : Paramètres → effacer → recopier la phrase → tout est vide."""
    app.sidebar.radio[0].set_value("Paramètres").run()
    assert _boutons(app, "raz"), "la zone de danger propose l'effacement"

    _boutons(app, "raz")[0].click().run()
    champ = [t for t in app.text_input if getattr(t, "key", None) == "raz_phrase"]
    assert champ, "une fenêtre demande de recopier la phrase de confirmation"

    champ[0].set_value(data.PHRASE_SUPPRESSION).run()
    _boutons(app, "raz_ok")[0].click().run()
    assert not app.exception, [str(e.value) for e in app.exception]

    apres = data.load_db()
    assert apres.machines == [] and apres.arrets == [] and apres.pieces == []


def test_the_dialog_offers_to_keep_the_departments(app):
    app.sidebar.radio[0].set_value("Paramètres").run()
    app.selectbox(key="dept_cible").set_value("__new__").run()
    next(t for t in app.text_input if t.label == "Nom complet").set_value("Menuiserie Métallique")
    next(t for t in app.text_input if t.label == "Code court").set_value("MM")
    next(b for b in app.button
         if "Enregistrer le département" in (b.label or "")).click().run()

    _boutons(app, "raz")[0].click().run()
    portee = [r for r in app.radio if getattr(r, "key", None) == "raz_portee"]
    assert portee, "le dialogue laisse choisir ce qu'on efface"

    portee[0].set_value("donnees").run()
    [t for t in app.text_input if getattr(t, "key", None) == "raz_phrase"][0] \
        .set_value(data.PHRASE_SUPPRESSION).run()
    _boutons(app, "raz_ok")[0].click().run()

    assert data.load_db().machines == [], "les données sont bien effacées"
    assert "menuiserie" in config.DEPT_BY_ID, "mais les départements sont conservés"


def test_a_wrong_phrase_erases_nothing(app):
    app.sidebar.radio[0].set_value("Paramètres").run()
    _boutons(app, "raz")[0].click().run()

    [t for t in app.text_input if getattr(t, "key", None) == "raz_phrase"][0] \
        .set_value("oui").run()
    _boutons(app, "raz_ok")[0].click().run()

    assert data.load_db().machines, "sans la phrase exacte, rien n'est effacé"
    assert any("phrase" in e.value.lower() for e in app.error)


def test_the_demo_can_be_reloaded_after_a_wipe(app):
    """Le bouton de réinitialisation ramène un jeu de données complet."""
    app.sidebar.radio[0].set_value("Paramètres").run()
    data.wipe_all()
    app.run()

    _boutons(app, "demo")[0].click().run()
    assert not app.exception, [str(e.value) for e in app.exception]
    assert data.load_db().machines, "les données de démonstration sont rechargées"


def test_wiping_is_reserved_to_admins(app):
    from admi import auth
    auth.create_user("lecteur", "lecteur", "viewer")
    next(b for b in app.button if "Se déconnecter" in (b.label or "")).click().run()
    app.text_input[0].set_value("lecteur")
    app.text_input[1].set_value("lecteur")
    app.button[0].click().run()

    app.sidebar.radio[0].set_value("Paramètres").run()
    assert not _boutons(app, "raz"), "un lecteur n'efface pas la base"


@pytest.fixture
def base_neuve(tmp_path, monkeypatch):
    """Une base SQLite jetable, sans données de démonstration."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'raz.db'}")
    monkeypatch.delenv("ADMI_DEMO", raising=False)
    from admi import db as dbmod
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_tables", {})
    monkeypatch.setattr(dbmod, "_meta", dbmod.MetaData())
    yield
    config.reset_departements()


def test_a_new_installation_opens_on_an_empty_application(base_neuve):
    db = data.load_db()
    assert db.machines == [] and db.arrets == [] and db.pieces == []


def test_the_emptiness_survives_a_restart(base_neuve):
    """Sans marqueur, la démo se réinstallerait au lancement suivant."""
    data.load_db()
    assert data.load_db().machines == []


def test_the_demo_is_loaded_only_when_asked(base_neuve, monkeypatch):
    monkeypatch.setenv("ADMI_DEMO", "1")
    assert data.load_db().machines, "ADMI_DEMO=1 amorce le jeu de démonstration"


def test_loading_the_demo_on_demand(base_neuve):
    data.load_db()
    db = data.load_demo()
    assert db.machines and db.pieces
    assert data.load_db().machines, "la démo chargée est bien persistée"


def test_wiping_can_keep_the_departments(base_neuve):
    """Cas courant d'une mise en service : on jette les données d'essai mais on
    garde le paramétrage de l'usine, souvent long à ressaisir."""
    data.load_demo()
    base = data.load_db()
    data.add_departement(base, "Menuiserie Métallique", "MM")

    vide = data.wipe_all(garder_departements=True)
    assert vide.machines == [] and vide.arrets == [] and vide.pieces == []
    assert "menuiserie" in config.DEPT_BY_ID, "le département ajouté reste"

    apres = data.load_db()
    assert apres.machines == []
    assert config.dep("menuiserie")["court"] == "MM", "et il survit au redémarrage"


def test_wiping_removes_everything_including_added_departments(base_neuve):
    data.load_demo()
    base = data.load_db()
    data.add_departement(base, "Menuiserie Métallique", "MM")
    assert "menuiserie" in config.DEPT_BY_ID

    vide = data.wipe_all()
    assert not any([vide.machines, vide.arrets, vide.energie, vide.interventions,
                    vide.planning, vide.pieces, vide.mouvements])
    assert [d["id"] for d in config.DEPARTEMENTS] == [
        d["id"] for d in config.DEPARTEMENTS_DEFAUT], "les départements ajoutés partent aussi"

    apres = data.load_db()
    assert apres.machines == [] and "menuiserie" not in config.DEPT_BY_ID, \
        "la remise à zéro tient au redémarrage"
