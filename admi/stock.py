"""Stock de pièces de rechange — règles métier pures (aucune dépendance Streamlit).

Reprend fidèlement l'application d'origine :
  valeur  = quantité × coût unitaire
  statut  = rupture (0) · alerte (≤ seuil) · ok
  entrée / sortie ajoutent ou retirent la quantité saisie, un ajustement fixe
  le nouveau total ; le stock ne descend jamais sous zéro.
"""
from __future__ import annotations

from .data import uid

TYPES_MOUVEMENT = ["Entrée", "Sortie", "Ajustement"]


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def piece_valeur(piece: dict) -> float:
    return _num(piece.get("quantite")) * _num(piece.get("coutUnitaire"))


def piece_statut(piece: dict) -> str:
    q, seuil = _num(piece.get("quantite")), _num(piece.get("seuilAlerte"))
    if q <= 0:
        return "rupture"
    if q <= seuil:
        return "alerte"
    return "ok"


def pieces_en_alerte(pieces: list) -> list:
    """Pièces sous leur seuil ou en rupture — celles du bandeau du tableau de bord."""
    return [p for p in pieces if piece_statut(p) != "ok"]


def totaux(pieces: list) -> dict:
    statuts = [piece_statut(p) for p in pieces]
    return {
        "references": len(pieces),
        "valeur": sum(piece_valeur(p) for p in pieces),
        "alerte": sum(1 for s in statuts if s != "ok"),
        "rupture": sum(1 for s in statuts if s == "rupture"),
    }


def apply_mouvement(db, piece_id: str, type_mvt: str, quantite, date: str, motif: str = ""):
    """Applique un mouvement au stock et le journalise.

    Renvoie le mouvement créé, ou None si la pièce n'existe pas.
    """
    piece = next((p for p in db.pieces if p["id"] == piece_id), None)
    if piece is None:
        return None
    qte = _num(quantite)
    stock_actuel = _num(piece.get("quantite"))
    if type_mvt == "Entrée":
        delta = qte
    elif type_mvt == "Sortie":
        delta = -qte
    else:  # Ajustement : la quantité saisie est le nouveau total
        delta = qte - stock_actuel
    piece["quantite"] = max(0.0, stock_actuel + delta)

    mouvement = {"id": uid(), "pieceId": piece_id, "date": date,
                 "type": type_mvt, "quantite": delta, "motif": motif}
    db.mouvements.append(mouvement)
    return mouvement
