"""Le raccourci « Voir le stock → » du bandeau d'alerte doit changer de section.

Ce test fait tourner l'application entière (AppTest) sur une base et un dossier
de données jetables : ni la licence, ni les comptes, ni les données de
l'utilisateur ne sont touchés.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

from admi import auth, license as lic

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Application connectée en admin, avec une pièce sous son seuil d'alerte."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(lic, "LIC_FILE", tmp_path / "license.json")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    lic.activate(lic.generate_license(), "tests")

    from admi import db as dbmod
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "_tables", {})
    monkeypatch.setattr(dbmod, "_meta", dbmod.MetaData())

    at = AppTest.from_file(APP, default_timeout=300).run()
    at.text_input[0].set_value("admin")
    at.text_input[1].set_value("admin")
    at.button[0].click().run()
    return at


def test_stock_alert_shortcut_opens_the_parts_section(app):
    from admi.data import load_db, upsert_record
    db = load_db()
    piece = next(p for p in db.pieces if p["seuilAlerte"])
    upsert_record(db, "pieces", {**piece, "quantite": 0})

    app.run()
    bouton = [b for b in app.button if "Voir le stock" in (b.label or "")]
    assert bouton, "le bandeau d'alerte doit proposer le raccourci vers le stock"

    bouton[0].click().run()
    assert not app.exception, [str(e.value) for e in app.exception]
    assert app.sidebar.radio[0].value == "Pièces de rechange"
