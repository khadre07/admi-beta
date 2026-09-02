"""Constantes ADMI : départements, couleurs, types, palette de thème.

Repris fidèlement de l'application HTML d'origine (ADMI version 11.08.2026).
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Départements de l'usine (id, nom complet, code court, couleur)
# ---------------------------------------------------------------------------
DEPARTEMENTS_DEFAUT = [
    {"id": "am",  "nom": "Articles Ménagers",            "court": "AM",  "couleur": "#7C83FD"},
    {"id": "ond", "nom": "Ondulations (Toitures Zinc)",  "court": "OND", "couleur": "#38BDF8"},
    {"id": "pt",  "nom": "Peinture",                     "court": "PT",  "couleur": "#FF6B6B"},
    {"id": "chi", "nom": "Chimie (Colle à Bois)",        "court": "CHI", "couleur": "#FFD166"},
    {"id": "sac", "nom": "Sacherie",                     "court": "SAC", "couleur": "#06D6A0"},
    {"id": "sl",  "nom": "Structures Légères",           "court": "SL",  "couleur": "#22D3EE"},
    {"id": "adm", "nom": "Administration",               "court": "ADM", "couleur": "#F472B6"},
    {"id": "srv", "nom": "Services Généraux",            "court": "SRV", "couleur": "#FB923C"},
]

# Liste vivante : les départements sont modifiables par l'administrateur et
# persistés avec les réglages. Les autres modules font `from .config import
# DEPARTEMENTS` à l'import — d'où la mutation **sur place** dans
# set_departements() : la référence partagée reste valable.
DEPARTEMENTS = [dict(d) for d in DEPARTEMENTS_DEFAUT]

DEPT_BY_ID = {d["id"]: d for d in DEPARTEMENTS}
DEPT_COLOR = {d["id"]: d["couleur"] for d in DEPARTEMENTS}


def set_departements(liste) -> None:
    """Remplace la liste des départements sans casser les imports existants."""
    DEPARTEMENTS[:] = [dict(d) for d in liste]
    DEPT_BY_ID.clear()
    DEPT_BY_ID.update({d["id"]: d for d in DEPARTEMENTS})
    DEPT_COLOR.clear()
    DEPT_COLOR.update({d["id"]: d["couleur"] for d in DEPARTEMENTS})


def reset_departements() -> None:
    """Revient aux 8 départements d'usine."""
    set_departements(DEPARTEMENTS_DEFAUT)


def new_dept_id(nom: str, existants) -> str:
    """Identifiant technique dérivé du nom, unique dans la liste."""
    sans_accents = unicodedata.normalize("NFD", str(nom or ""))
    sans_accents = "".join(c for c in sans_accents if unicodedata.category(c) != "Mn")
    base = "".join(c for c in sans_accents.lower() if c.isalnum())[:10] or "dept"
    candidat, i = base, 1
    while candidat in existants:
        candidat = f"{base}{i}"
        i += 1
    return candidat


# Couleurs proposées aux départements ajoutés après les huit d'usine. Ordre
# fixe, jamais tiré au hasard : deux départements de la même couleur rendraient
# les camemberts et les barres empilées illisibles.
PALETTE_DEPTS = [d["couleur"] for d in DEPARTEMENTS_DEFAUT] + [
    "#A855F7",  # violet
    "#4ADE80",  # vert clair
    "#F59E0B",  # ambre
    "#E879F9",  # magenta
    "#2DD4BF",  # turquoise
    "#94A3B8",  # ardoise
]


def new_dept_color(couleurs_utilisees) -> str:
    """Première couleur de la palette que personne n'utilise déjà."""
    prises = {str(c).upper() for c in couleurs_utilisees}
    for couleur in PALETTE_DEPTS:
        if couleur.upper() not in prises:
            return couleur
    # Palette épuisée : on repart au début plutôt que d'inventer une teinte.
    return PALETTE_DEPTS[len(prises) % len(PALETTE_DEPTS)]


def dep(dept_id: str) -> dict:
    """Retourne le département, ou un objet de repli si l'id est inconnu."""
    return DEPT_BY_ID.get(
        dept_id, {"id": dept_id, "nom": dept_id, "court": dept_id, "couleur": "#888888"}
    )


MOIS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]
MOIS_COURT = [m[:3] for m in MOIS]
DOW = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

TYPES_ARRET = [
    "Panne", "Arrêt préventif", "Arrêt programmé",
    "Changement de production", "Manque matière", "Autre",
]
TYPES_INTERV = [
    "Préventif", "Correctif", "Curatif d'urgence",
    "Inspection / Contrôle", "Amélioration",
]
TYPES_PLAN = [
    "Préventif", "Inspection", "Lubrification",
    "Contrôle réglementaire", "Révision générale", "Autre",
]
STATUTS_MACHINE = ["En service", "En panne", "En maintenance", "Hors service"]

# ---------------------------------------------------------------------------
# Objectifs de performance : cible à atteindre pour chaque indicateur.
# « min » = la cible est un plancher (on veut faire au moins autant),
# « max » = la cible est un plafond (on veut rester en dessous).
# ---------------------------------------------------------------------------
OBJECTIF_SENS = {
    "disponibilite": "min", "tauxPreventif": "min", "mtbf": "min",
    "mttr": "max", "tempsArret": "max",
}
OBJECTIF_LABELS = {
    "disponibilite": "Disponibilité", "tauxPreventif": "Taux préventif",
    "mtbf": "MTBF", "mttr": "MTTR", "tempsArret": "Temps d'arrêt cumulé",
}
OBJECTIF_UNITES = {
    "disponibilite": "%", "tauxPreventif": "%",
    "mtbf": "h", "mttr": "h", "tempsArret": "h",
}

# ---------------------------------------------------------------------------
# Palette du thème sombre (variables CSS de l'app d'origine)
# ---------------------------------------------------------------------------
THEME = {
    "bg": "#0A1220",
    "bg2": "#0D1626",
    "panel": "#121C2E",
    "panel2": "#17233A",
    "border": "#243250",
    "border_light": "#2E3E60",
    "text": "#E7ECF3",
    "muted": "#8CA0BC",
    "muted2": "#5E7195",
    "accent": "#F2A93B",
    "accent2": "#2BC7BE",
    "danger": "#EF5B5B",
    "success": "#48D48A",
    "warn": "#F2A93B",
    "grid": "rgba(140,160,188,0.12)",
}
