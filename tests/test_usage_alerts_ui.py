"""Chantier A — intégration : la vue Machines expose le suivi des seuils d'heures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_machines_view_shows_usage_columns(app):
    app.sidebar.radio[0].set_value("Machines & Puissance").run()
    assert not app.exception, [str(e.value) for e in app.exception]
    cols = set()
    for df in app.dataframe:
        cols |= set(df.value.columns)
    assert "Heures d'utilisation" in cols
    assert "Suivi seuils" in cols
