"""Chantier C — tous les chiffres des graphes doivent figurer dans le PDF.

On génère le rapport PDF sur des données contrôlées, on en extrait le texte
(pymupdf) et on vérifie que les valeurs *par département* des graphes — qui
n'étaient dessinées que sous forme de barres, sans étiquette — y apparaissent.
"""
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.data import Database
from admi import report, i18n


def _pdf_text(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def _controlled_db():
    db = Database()
    db.machines += [
        {"id": "m1", "nom": "Presse", "departementId": "am",
         "puissanceKW": 45, "dateMES": "2025-01-01", "statut": "En service"},
        {"id": "m2", "nom": "Onduleur", "departementId": "ond",
         "puissanceKW": 20, "dateMES": "2025-01-01", "statut": "En service"},
    ]
    db.arrets += [
        {"id": "a1", "machineId": "m1", "departementId": "am", "type": "Panne",
         "cause": "Roulement", "dateDebut": "2026-01-05T08:00", "dateFin": "2026-01-05T14:30"},  # 6.5h
        {"id": "a2", "machineId": "m2", "departementId": "ond", "type": "Panne",
         "cause": "Surchauffe", "dateDebut": "2026-01-06T08:00", "dateFin": "2026-01-06T12:00"},  # 4.0h
    ]
    # 13 interventions préventives sur am : ce compte (13) n'apparaît dans AUCUN
    # tableau du rapport aujourd'hui — seulement dans le graphe préventif/correctif.
    for n in range(13):
        db.interventions.append({"id": f"i{n}", "machineId": "m1", "departementId": "am",
                                 "type": "Préventif", "date": "2026-01-05",
                                 "coutMainOeuvre": 0, "pieces": []})
    return db


def test_pdf_shows_per_department_stop_hours():
    i18n.set_lang("fr")
    db = _controlled_db()
    pdf = report.build_pdf_report(db, "mois", 2026, 0, "all")   # janvier 2026
    text = _pdf_text(pdf)
    # Heures d'arrêt par département (graphe) : am = 6,5 h, ond = 4,0 h.
    assert "6,5" in text
    assert "4,0" in text


def test_pdf_shows_preventive_corrective_counts():
    i18n.set_lang("fr")
    db = _controlled_db()
    pdf = report.build_pdf_report(db, "mois", 2026, 0, "all")
    text = _pdf_text(pdf)
    # Le compte préventif du graphe (13 pour am) doit figurer en clair dans le PDF.
    assert "13" in text
