"""L'export Excel doit contenir le stock : le catalogue des pièces et le journal
des mouvements, en plus des feuilles historiques."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from admi import stock
from admi.data import Database
from admi.io_excel import export_bytes


def _db():
    db = Database()
    db.pieces.append({"id": "p1", "reference": "COU-A32", "designation": "Courroie trapézoïdale A32",
                      "departementId": "am", "quantite": 12, "seuilAlerte": 3, "unite": "unité",
                      "coutUnitaire": 8500, "emplacement": "Magasin A - Rayon 2", "fournisseur": "SN Pièces"})
    stock.apply_mouvement(db, "p1", "Sortie", 4, "2026-08-20", "Intervention PT-1")
    return db


def _sheet(name):
    return pd.read_excel(io.BytesIO(export_bytes(_db())), sheet_name=name)


def test_export_contains_parts_sheet_with_computed_value():
    df = _sheet("Pièces")
    assert list(df["Désignation"]) == ["Courroie trapézoïdale A32"]
    row = df.iloc[0]
    assert row["Quantité"] == 8            # 12 reçus, 4 sortis
    assert row["Valeur (FCFA)"] == 8 * 8500
    assert row["Département"] == "Articles Ménagers"


def test_export_contains_movements_sheet():
    df = _sheet("Mouvements")
    row = df.iloc[0]
    assert row["Pièce"] == "Courroie trapézoïdale A32"
    assert row["Type"] == "Sortie"
    assert row["Quantité"] == -4
    assert row["Motif"] == "Intervention PT-1"
