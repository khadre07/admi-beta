"""Le raccourci « Voir le stock → » du bandeau d'alerte doit changer de section.

Ce test fait tourner l'application entière (AppTest) sur une base et un dossier
de données jetables : ni la licence, ni les comptes, ni les données de
l'utilisateur ne sont touchés.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
