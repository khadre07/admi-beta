"""Écran Alertes : le bouton de test doit rendre compte, pas faire tomber la page."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import alerts


def _bouton_test(app):
    return [b for b in app.button if "test" in (b.label or "").lower()]


def test_the_test_button_reports_a_failure_instead_of_crashing(app, monkeypatch):
    """Un envoi qui explose (SMTP absurde, module périmé après déploiement…) doit
    s'afficher comme un échec dans l'écran, pas comme une erreur d'application."""
    def _explose(*a, **k):
        raise RuntimeError("serveur injoignable")

    monkeypatch.setattr(alerts, "notify", _explose)
    app.sidebar.radio[0].set_value("Alertes").run()

    bouton = _bouton_test(app)
    assert bouton, "l'écran Alertes propose un envoi de test"
    bouton[0].click().run()

    assert not app.exception, [str(e.value) for e in app.exception]
    assert any("serveur injoignable" in e.value for e in app.error)
