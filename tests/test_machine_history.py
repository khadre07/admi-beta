"""Chantier B — historique de pannes par machine.

Brique pure : kpis.machine_arret_stats — mini-bilan des arrêts d'une machine
(nombre, temps d'arrêt, dernière panne, MTBF machine).
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.data import Database
from admi import kpis


def _db_with_stops():
    db = Database()
    db.machines.append({"id": "m1", "nom": "Presse", "departementId": "am",
                        "puissanceKW": 45, "dateMES": "2026-01-01", "statut": "En service"})
    db.arrets += [
        {"id": "a1", "machineId": "m1", "departementId": "am", "type": "Panne",
         "cause": "Roulement", "dateDebut": "2026-01-03T08:00", "dateFin": "2026-01-03T14:00"},  # 6h
        {"id": "a2", "machineId": "m1", "departementId": "am", "type": "Maintenance préventive",
         "cause": "", "dateDebut": "2026-01-05T08:00", "dateFin": "2026-01-05T10:00"},  # 2h
        {"id": "a3", "machineId": "AUTRE", "departementId": "am", "type": "Panne",
         "cause": "x", "dateDebut": "2026-01-04T08:00", "dateFin": "2026-01-04T12:00"},  # autre machine
    ]
    return db


def test_stats_pannes_only():
    db = _db_with_stops()
    s = kpis.machine_arret_stats(db, "m1", pannes_only=True, now=datetime(2026, 1, 8))
    assert s["nb"] == 1                       # une seule panne pour m1
    assert s["tempsArretH"] == 6              # durée des pannes affichées
    assert s["derniere"] == "2026-01-03T08:00"
    assert s["nbPannes"] == 1
    # MTBF = heures d'utilisation / nb pannes ; usage = 168 - (6+2) = 160
    assert s["mtbf"] == 160


def test_stats_all_stops():
    db = _db_with_stops()
    s = kpis.machine_arret_stats(db, "m1", pannes_only=False, now=datetime(2026, 1, 8))
    assert s["nb"] == 2
    assert s["tempsArretH"] == 8
    assert s["derniere"] == "2026-01-05T08:00"   # arrêt le plus récent, tous types
    assert s["nbPannes"] == 1                     # MTBF reste basé sur les pannes


def test_stats_no_stops():
    db = _db_with_stops()
    s = kpis.machine_arret_stats(db, "AUCUNE", pannes_only=True, now=datetime(2026, 1, 8))
    assert s["nb"] == 0
    assert s["tempsArretH"] == 0
    assert s["derniere"] is None
    assert s["mtbf"] is None


def test_machine_history_block_renders(app):
    app.sidebar.radio[0].set_value("Machines & Puissance").run()
    assert not app.exception, [str(e.value) for e in app.exception]
    md = " ".join(str(m.value) for m in app.markdown)
    assert "Historique des pannes par machine" in md
