"""Tests d'import Word (.docx) et PDF — extraction de tableaux."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.data import Database, uid
from admi.io_excel import apply_import, parse_import


def test_import_docx_tables():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=5)
    for i, h in enumerate(["Département / Service", "Mois (1-12)", "Année",
                           "Consommation (kWh)", "Montant (FCFA)"]):
        t.rows[0].cells[i].text = h
    for row in [["Peinture", "3", "2026", "12000", "1650000"],
                ["Sacherie", "3", "2026", "20000", "2800000"]]:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = v
    buf = io.BytesIO()
    doc.save(buf)

    db = Database()
    res = parse_import(buf.getvalue(), "rapport.docx", db)
    assert len(res["energie"]) == 2
    assert res["errors"] == []
    assert res["energie"][0]["mois"] == 2  # mars = index 2


def test_import_pdf_table():
    rl = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    data = [["Machine", "Département (optionnel)", "Type d'arrêt", "Cause",
             "Début (AAAA-MM-JJ HH:MM)", "Fin (AAAA-MM-JJ HH:MM)", "Description"],
            ["Presse ZZ-1", "Peinture", "Panne", "Rupture courroie",
             "2026-03-10 08:00", "2026-03-10 11:30", "RAS"]]
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4)
    tb = Table(data)
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                            ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    pdf.build([tb])

    db = Database()
    db.machines.append({"id": uid(), "nom": "Presse ZZ-1", "departementId": "pt",
                        "puissanceKW": 33, "dateMES": "2024-01-01", "statut": "En service"})
    res = parse_import(buf.getvalue(), "arrets.pdf", db)
    assert len(res["arrets"]) == 1
    assert res["errors"] == []
    apply_import(db, res, "append")
    assert len(db.arrets) == 1


def test_import_unrecognized_document_raises():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "Colonne A"
    t.rows[0].cells[1].text = "Colonne B"
    t.add_row().cells[0].text = "x"
    buf = io.BytesIO()
    doc.save(buf)
    with pytest.raises(ValueError):
        parse_import(buf.getvalue(), "inconnu.docx", Database())
