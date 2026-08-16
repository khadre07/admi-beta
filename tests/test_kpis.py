"""Tests des calculs KPI — les formules doivent reproduire exactement
l'application d'origine (disponibilité, MTBF, MTTR, coûts, énergie)."""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.data import Database
from admi import kpis


def test_opening_hours_continuous_24_7():
    db = Database()
    # planning par défaut = 24h/24, 7j/7
    hours = kpis.opening_hours(db, "am", datetime(2026, 1, 1), datetime(2026, 1, 8))
    assert hours == 7 * 24  # 7 jours pleins


def test_opening_hours_admin_8h_weekdays():
    db = Database()
    db.dept_schedule("adm").update({"heuresParJour": 8, "jours": [True] * 5 + [False, False]})
    # Semaine du lundi 2026-01-05 au dimanche suivant (2026-01-05 est un lundi)
    hours = kpis.opening_hours(db, "adm", datetime(2026, 1, 5), datetime(2026, 1, 12))
    assert hours == 5 * 8  # 5 jours ouvrés × 8h


def test_minutes_between():
    assert kpis.hours_between("2026-01-10T08:00", "2026-01-10T11:30") == 3.5
    # fin avant début -> 0 (borné comme dans l'original)
    assert kpis.hours_between("2026-01-10T11:30", "2026-01-10T08:00") == 0.0


def test_intervention_cost():
    interv = {
        "coutMainOeuvre": 15000,
        "pieces": [
            {"designation": "Courroie", "qte": 1, "cout": 12000},
            {"designation": "Roulement", "qte": 2, "cout": 4500},
        ],
    }
    # 15000 + 12000*1 + 4500*2 = 36000
    assert kpis.intervention_cost(interv) == 36000


def _one_machine_db():
    db = Database()
    db.machines.append({"id": "m1", "nom": "Presse", "departementId": "am",
                        "puissanceKW": 45, "dateMES": "2022-01-01", "statut": "En service"})
    return db


def test_kpis_availability_and_mtbf_mttr():
    db = _one_machine_db()
    # Janvier 2026 : 31 jours × 24h = 744h d'ouverture (1 machine, continu)
    # 2 arrêts dont 1 panne, total 10h d'arrêt
    db.arrets += [
        {"id": "a1", "machineId": "m1", "departementId": "am", "type": "Panne",
         "cause": "x", "dateDebut": "2026-01-05T08:00", "dateFin": "2026-01-05T14:00",
         "description": ""},  # 6h
        {"id": "a2", "machineId": "m1", "departementId": "am", "type": "Arrêt préventif",
         "cause": "y", "dateDebut": "2026-01-12T09:00", "dateFin": "2026-01-12T13:00",
         "description": ""},  # 4h
    ]
    k = kpis.compute_kpis(db, periode="mois", annee=2026, mois=0, dept="all")
    assert k["heuresOuverture"] == 744
    assert k["tempsArretH"] == 10.0
    assert k["nbArrets"] == 2
    assert k["nbPannes"] == 1
    # dispo = (1 - 10/744) * 100
    assert round(k["disponibilite"], 4) == round((1 - 10 / 744) * 100, 4)
    # mtbf = (744 - 10) / 1 pannes
    assert round(k["mtbf"], 4) == round(734 / 1, 4)
    # mttr = 10 / 2 arrêts
    assert k["mttr"] == 5.0


def test_kpis_no_stops_full_availability():
    db = _one_machine_db()
    k = kpis.compute_kpis(db, periode="mois", annee=2026, mois=0, dept="all")
    assert k["disponibilite"] == 100.0
    assert k["mtbf"] is None  # aucune panne
    assert k["mttr"] is None  # aucun arrêt


def test_kpis_energy_totals():
    db = _one_machine_db()
    db.energie += [
        {"id": "e1", "departementId": "am", "mois": 0, "annee": 2026, "kwh": 15000, "montant": 2250000},
        {"id": "e2", "departementId": "am", "mois": 0, "annee": 2026, "kwh": 5000, "montant": 750000},
        {"id": "e3", "departementId": "am", "mois": 1, "annee": 2026, "kwh": 9999, "montant": 1},  # autre mois -> exclu
    ]
    k = kpis.compute_kpis(db, periode="mois", annee=2026, mois=0, dept="all")
    assert k["kwh"] == 20000
    assert k["coutEnergie"] == 3000000


def test_dept_filter_isolates_department():
    db = _one_machine_db()
    db.machines.append({"id": "m2", "nom": "Réacteur", "departementId": "chi",
                        "puissanceKW": 35, "dateMES": "2022-01-01", "statut": "En service"})
    db.arrets.append({"id": "a1", "machineId": "m2", "departementId": "chi", "type": "Panne",
                      "cause": "x", "dateDebut": "2026-01-05T08:00", "dateFin": "2026-01-05T10:00",
                      "description": ""})
    k_am = kpis.compute_kpis(db, periode="mois", annee=2026, mois=0, dept="am")
    assert k_am["tempsArretH"] == 0.0  # l'arrêt est en chimie, pas en AM
    k_chi = kpis.compute_kpis(db, periode="mois", annee=2026, mois=0, dept="chi")
    assert k_chi["tempsArretH"] == 2.0


def test_yearly_trend_shape():
    db = _one_machine_db()
    db.arrets.append({"id": "a1", "machineId": "m1", "departementId": "am", "type": "Panne",
                      "cause": "x", "dateDebut": "2024-03-05T08:00", "dateFin": "2024-03-05T12:00",
                      "description": ""})
    trend = kpis.yearly_trend(db, dept="all")
    years = [row["year"] for row in trend]
    assert 2024 in years
    row_2024 = next(r for r in trend if r["year"] == 2024)
    assert row_2024["tempsArretH"] == 4.0
