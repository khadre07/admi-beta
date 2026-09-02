"""Fixtures partagées par les tests de bout en bout.

L'application est lancée en entier (AppTest) sur une base, une licence et un
fichier d'utilisateurs jetables : les données réelles ne sont jamais touchées.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Application connectée en admin, sur des données jetables."""
    from streamlit.testing.v1 import AppTest

    from admi import auth, license as lic

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
