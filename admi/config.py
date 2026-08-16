"""Constantes ADMI : départements, couleurs, types, palette de thème.

Repris fidèlement de l'application HTML d'origine (ADMI version 11.08.2026).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Départements de l'usine (id, nom complet, code court, couleur)
# ---------------------------------------------------------------------------
DEPARTEMENTS = [
    {"id": "am",  "nom": "Articles Ménagers",            "court": "AM",  "couleur": "#7C83FD"},
    {"id": "ond", "nom": "Ondulations (Toitures Zinc)",  "court": "OND", "couleur": "#38BDF8"},
    {"id": "pt",  "nom": "Peinture",                     "court": "PT",  "couleur": "#FF6B6B"},
    {"id": "chi", "nom": "Chimie (Colle à Bois)",        "court": "CHI", "couleur": "#FFD166"},
    {"id": "sac", "nom": "Sacherie",                     "court": "SAC", "couleur": "#06D6A0"},
    {"id": "sl",  "nom": "Structures Légères",           "court": "SL",  "couleur": "#22D3EE"},
    {"id": "adm", "nom": "Administration",               "court": "ADM", "couleur": "#F472B6"},
    {"id": "srv", "nom": "Services Généraux",            "court": "SRV", "couleur": "#FB923C"},
]

DEPT_BY_ID = {d["id"]: d for d in DEPARTEMENTS}
DEPT_COLOR = {d["id"]: d["couleur"] for d in DEPARTEMENTS}


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
