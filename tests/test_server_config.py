"""R1 — réseau / serveur : libellé lisible du backend de base de données."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import db as dbmod


def test_backend_label_postgres():
    assert dbmod.backend_label("postgresql://u:p@host:5432/admi") == "PostgreSQL"
    assert dbmod.backend_label("postgresql+psycopg://host/admi") == "PostgreSQL"


def test_backend_label_sqlite():
    assert dbmod.backend_label("sqlite:////var/lib/admi/admi.db") == "SQLite"


def test_backend_label_other():
    assert dbmod.backend_label("mysql://host/admi") == "mysql"


def test_settings_network_panel_renders(app):
    app.sidebar.radio[0].set_value("Paramètres").run()
    assert not app.exception, [str(e.value) for e in app.exception]
    md = " ".join(str(m.value) for m in app.markdown)
    assert "Réseau & serveur" in md
    assert "Base de données active" in md
