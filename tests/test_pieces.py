"""Tests du stock de pièces de rechange — mêmes règles que l'application d'origine :
valeur = quantité × coût unitaire, statut ok / alerte / rupture, et mouvements
d'entrée, de sortie et d'ajustement qui ne peuvent pas rendre le stock négatif."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import stock
from admi.data import Database


def _piece(**kw):
    base = {"id": "p1", "reference": "COU-A32", "designation": "Courroie trapézoïdale A32",
            "departementId": "am", "quantite": 12, "seuilAlerte": 3, "unite": "unité",
            "coutUnitaire": 8500, "emplacement": "Magasin A - Rayon 2", "fournisseur": ""}
    base.update(kw)
    return base


def _db_with_piece(**kw):
    db = Database()
    db.pieces.append(_piece(**kw))
    return db


def test_piece_valeur_is_quantity_times_unit_cost():
    assert stock.piece_valeur(_piece(quantite=12, coutUnitaire=8500)) == 102000


def test_piece_statut_ok_above_threshold():
    assert stock.piece_statut(_piece(quantite=12, seuilAlerte=3)) == "ok"


def test_piece_statut_alerte_at_or_below_threshold():
    assert stock.piece_statut(_piece(quantite=3, seuilAlerte=3)) == "alerte"
    assert stock.piece_statut(_piece(quantite=1, seuilAlerte=3)) == "alerte"


def test_piece_statut_rupture_when_empty():
    assert stock.piece_statut(_piece(quantite=0, seuilAlerte=3)) == "rupture"


def test_entree_increases_stock_and_logs_movement():
    db = _db_with_piece(quantite=12)
    stock.apply_mouvement(db, "p1", "Entrée", 5, "2026-08-20", "Réception livraison")
    assert db.pieces[0]["quantite"] == 17
    mv = db.mouvements[-1]
    assert mv["pieceId"] == "p1" and mv["type"] == "Entrée" and mv["quantite"] == 5
    assert mv["motif"] == "Réception livraison" and mv["date"] == "2026-08-20"


def test_sortie_decreases_stock():
    db = _db_with_piece(quantite=12)
    stock.apply_mouvement(db, "p1", "Sortie", 4, "2026-08-20", "Intervention PT-1")
    assert db.pieces[0]["quantite"] == 8
    assert db.mouvements[-1]["quantite"] == -4


def test_sortie_never_makes_stock_negative():
    db = _db_with_piece(quantite=2)
    stock.apply_mouvement(db, "p1", "Sortie", 5, "2026-08-20", "")
    assert db.pieces[0]["quantite"] == 0


def test_ajustement_sets_the_new_total():
    db = _db_with_piece(quantite=12)
    stock.apply_mouvement(db, "p1", "Ajustement", 9, "2026-08-20", "Inventaire")
    assert db.pieces[0]["quantite"] == 9
    assert db.mouvements[-1]["quantite"] == -3  # l'écart constaté, pas le total


def test_mouvement_on_unknown_piece_is_refused():
    db = _db_with_piece()
    assert stock.apply_mouvement(db, "inconnue", "Entrée", 1, "2026-08-20", "") is None
    assert db.mouvements == []


def test_totaux_du_stock():
    db = Database()
    db.pieces += [_piece(id="p1", quantite=12, seuilAlerte=3, coutUnitaire=8500),
                  _piece(id="p2", quantite=2, seuilAlerte=5, coutUnitaire=4500),
                  _piece(id="p3", quantite=0, seuilAlerte=1, coutUnitaire=22000)]
    t = stock.totaux(db.pieces)
    assert t["references"] == 3
    assert t["valeur"] == 12 * 8500 + 2 * 4500 + 0
    assert t["alerte"] == 2   # p2 sous le seuil et p3 en rupture
    assert t["rupture"] == 1


def test_pieces_en_alerte_listed_for_the_dashboard_banner():
    db = Database()
    db.pieces += [_piece(id="p1", designation="Courroie", quantite=12, seuilAlerte=3),
                  _piece(id="p2", designation="Roulement", quantite=1, seuilAlerte=5)]
    assert [p["designation"] for p in stock.pieces_en_alerte(db.pieces)] == ["Roulement"]
