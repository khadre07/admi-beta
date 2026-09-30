"""Calculs des indicateurs de maintenance (KPI) — fonctions pures.

Reproduit fidèlement les formules de l'application ADMI d'origine :
  disponibilité = (1 - tempsArret / heuresOuverture) * 100   (bornée 0..100)
  MTBF          = (heuresOuverture - tempsArret) / nbPannes
  MTTR          = tempsArret / nbArrets
  heuresOuverture = Σ_machines  heures d'ouverture du département de la machine
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import DEPARTEMENTS, OBJECTIF_SENS

TREND_START_YEAR = 2020


def _parse(dt: str) -> datetime:
    """Parse une date/heure ISO ('YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM')."""
    s = str(dt)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s[:10])


def hours_between(a: str, b: str) -> float:
    """Durée en heures entre deux instants ISO, bornée à 0 (comme l'original)."""
    delta = (_parse(b) - _parse(a)).total_seconds() / 3600.0
    return max(0.0, round(delta, 6))


def intervention_cost(interv: dict) -> float:
    pieces = interv.get("pieces") or []
    cout_pieces = sum((float(p.get("cout") or 0) * float(p.get("qte") or 1)) for p in pieces)
    return cout_pieces + float(interv.get("coutMainOeuvre") or 0)


def opening_hours(db, dept_id: str, start: datetime, end: datetime) -> float:
    """Heures d'ouverture théoriques d'un département sur [start, end)."""
    sched = db.dept_schedule(dept_id)
    jours = sched.get("jours", [True] * 7)
    hpj = float(sched.get("heuresParJour", 24))
    total = 0.0
    d = datetime(start.year, start.month, start.day)
    while d < end:
        if jours[d.weekday()]:  # weekday(): lundi=0 .. dimanche=6
            total += hpj
        d += timedelta(days=1)
    return total


def machine_usage_hours(db, machine: dict, now: datetime | None = None) -> float:
    """Heures d'utilisation cumulées d'une machine depuis sa mise en service.

    = heures d'ouverture du département (dateMES -> maintenant) - heures d'arrêt
    de cette machine. Bornée à 0. Sans dateMES, renvoie 0.
    """
    mes = str(machine.get("dateMES") or "").strip()
    if not mes:
        return 0.0
    end = now or datetime.now()
    opening = opening_hours(db, machine.get("departementId"), _parse(mes), end)
    arrets = sum(hours_between(a["dateDebut"], a["dateFin"])
                 for a in db.arrets
                 if a.get("machineId") == machine.get("id") and a.get("dateFin"))
    return max(0.0, round(opening - arrets, 6))


def machine_arret_stats(db, machine_id: str, pannes_only: bool = True,
                         now: datetime | None = None) -> dict:
    """Mini-bilan des arrêts d'une machine (historique par machine).

    `pannes_only` restreint le décompte/affichage aux arrêts de type « Panne ».
    Le MTBF machine reste basé sur les pannes = heures d'utilisation / nb pannes.
    """
    tous = [a for a in db.arrets if a.get("machineId") == machine_id]
    selection = [a for a in tous if not pannes_only or a.get("type") == "Panne"]
    temps = sum(hours_between(a["dateDebut"], a["dateFin"])
                for a in selection if a.get("dateFin"))
    derniere = max((a["dateDebut"] for a in selection), default=None)
    nb_pannes = sum(1 for a in tous if a.get("type") == "Panne")
    machine = db.machine(machine_id)
    usage = machine_usage_hours(db, machine, now) if machine else 0.0
    mtbf = round(usage / nb_pannes, 6) if nb_pannes > 0 else None
    return {"nb": len(selection), "tempsArretH": round(temps, 6),
            "derniere": derniere, "nbPannes": nb_pannes, "mtbf": mtbf}


# Niveaux d'alerte de seuil, ordonnés (permet de n'escalader que vers le haut).
_USAGE_LEVELS = {"": 0, "approche": 1, "atteint": 2}


def usage_alert_level(usage: float, seuil, margin_pct: float = 90.0) -> str:
    """Niveau d'alerte pour un temps d'utilisation face à un seuil.

    "" (rien), "approche" (>= marge % du seuil) ou "atteint" (>= seuil).
    Un seuil vide/nul/non numérique désactive l'alerte -> "".
    """
    try:
        seuil = float(seuil)
    except (TypeError, ValueError):
        return ""
    if seuil <= 0:
        return ""
    if usage >= seuil:
        return "atteint"
    if usage >= seuil * margin_pct / 100.0:
        return "approche"
    return ""


def pending_usage_alerts(usage: float, seuil_maintenance, seuil_arret,
                         notified: dict | None = None, margin_pct: float = 90.0):
    """Décide quelles alertes de seuil sont *nouvelles* (anti-spam). Fonction pure.

    `notified` = niveaux déjà notifiés {"maintenance": niveau, "arret": niveau}.
    Renvoie (alertes_nouvelles, etat_maj) : une alerte n'est émise que si son
    niveau dépasse celui déjà notifié (jamais de rappel à chaque rerun).
    """
    notified = notified or {}
    out = dict(notified)
    alerts = []
    for kind, seuil in (("maintenance", seuil_maintenance), ("arret", seuil_arret)):
        level = usage_alert_level(usage, seuil, margin_pct)
        prev = notified.get(kind, "") or ""
        if _USAGE_LEVELS[level] > _USAGE_LEVELS.get(prev, 0):
            alerts.append({"kind": kind, "level": level,
                           "seuil": float(seuil), "usage": usage})
            out[kind] = level
        else:
            out[kind] = prev
    return alerts, out


def period_bounds(periode: str, annee: int, mois: int):
    if periode == "mois":
        start = datetime(annee, mois + 1, 1)
        end = datetime(annee + 1, 1, 1) if mois == 11 else datetime(annee, mois + 2, 1)
    else:  # annuelle
        start = datetime(annee, 1, 1)
        end = datetime(annee + 1, 1, 1)
    return start, end


def _scope_depts(dept: str):
    return [d["id"] for d in DEPARTEMENTS] if dept == "all" else [dept]


def filter_arrets(db, start, end, dept="all"):
    out = []
    for a in db.arrets:
        dd = _parse(a["dateDebut"])
        if dd < start or dd >= end:
            continue
        if dept != "all" and a["departementId"] != dept:
            continue
        out.append(a)
    return out


def filter_interventions(db, start, end, dept="all"):
    out = []
    for i in db.interventions:
        dd = _parse(i["date"])
        if dd < start or dd >= end:
            continue
        if dept != "all" and i["departementId"] != dept:
            continue
        out.append(i)
    return out


def filter_energie(db, periode, annee, mois, dept="all"):
    out = []
    for e in db.energie:
        if periode == "mois":
            if e["annee"] != annee or e["mois"] != mois:
                continue
        else:
            if e["annee"] != annee:
                continue
        if dept != "all" and e["departementId"] != dept:
            continue
        out.append(e)
    return out


def filter_planning(db, start, end, dept="all"):
    out = []
    for p in db.planning:
        dd = _parse(p["date"])
        if dd < start or dd >= end:
            continue
        if dept != "all" and p["departementId"] != dept:
            continue
        out.append(p)
    return out


def objectif_atteint(metric: str, value, target):
    """L'objectif est-il tenu ? None si la valeur ou la cible n'est pas définie."""
    if value is None or target is None:
        return None
    if OBJECTIF_SENS.get(metric) == "max":
        return float(value) <= float(target)
    return float(value) >= float(target)


def compute_kpis(db, periode: str, annee: int, mois: int, dept: str) -> dict:
    start, end = period_bounds(periode, annee, mois)
    arrets = filter_arrets(db, start, end, dept)
    intervs = filter_interventions(db, start, end, dept)
    energie = filter_energie(db, periode, annee, mois, dept)
    planning = filter_planning(db, start, end, dept)

    heures_ouverture = 0.0
    for d_id in _scope_depts(dept):
        nb_machines = sum(1 for m in db.machines if m["departementId"] == d_id)
        if nb_machines > 0:
            heures_ouverture += nb_machines * opening_hours(db, d_id, start, end)

    temps_arret = sum(hours_between(a["dateDebut"], a["dateFin"]) for a in arrets)
    nb_pannes = sum(1 for a in arrets if a["type"] == "Panne")
    nb_arrets = len(arrets)

    dispo = (max(0.0, min(100.0, (1 - temps_arret / heures_ouverture) * 100))
             if heures_ouverture > 0 else 100.0)
    mtbf = (heures_ouverture - temps_arret) / nb_pannes if nb_pannes > 0 else None
    mttr = temps_arret / nb_arrets if nb_arrets > 0 else None

    cout_maint = sum(intervention_cost(i) for i in intervs)
    kwh = sum(float(e.get("kwh") or 0) for e in energie)
    cout_energie = sum(float(e.get("montant") or 0) for e in energie)
    puissance_totale = sum(float(m.get("puissanceKW") or 0) for m in db.machines)

    # Taux de réalisation du préventif : les actions annulées ne comptent pas.
    planning_dus = [p for p in planning if p.get("statut") != "Annulé"]
    planning_realises = sum(1 for p in planning_dus if p.get("statut") == "Réalisé")
    taux_preventif = (planning_realises / len(planning_dus) * 100) if planning_dus else None

    return {
        "tempsArretH": round(temps_arret, 6),
        "nbPannes": nb_pannes,
        "nbArrets": nb_arrets,
        "disponibilite": dispo,
        "mtbf": mtbf,
        "mttr": mttr,
        "coutMaint": cout_maint,
        "kwh": kwh,
        "coutEnergie": cout_energie,
        "heuresOuverture": heures_ouverture,
        "puissanceInstallee": puissance_totale,
        "planningDus": len(planning_dus),
        "planningRealises": planning_realises,
        "tauxRealisationPreventif": taux_preventif,
    }


def yearly_trend(db, dept: str = "all") -> list:
    """Vue annuelle 2020 -> année courante pour la métrique choisie côté UI."""
    trend = []
    this_year = date.today().year
    for y in range(TREND_START_YEAR, this_year + 1):
        start, end = datetime(y, 1, 1), datetime(y + 1, 1, 1)
        arrets = filter_arrets(db, start, end, dept)
        intervs = filter_interventions(db, start, end, dept)
        energie = [e for e in db.energie
                   if e["annee"] == y and (dept == "all" or e["departementId"] == dept)]

        temps_arret = sum(hours_between(a["dateDebut"], a["dateFin"]) for a in arrets)
        cout_maint = sum(intervention_cost(i) for i in intervs)
        kwh = sum(float(e.get("kwh") or 0) for e in energie)

        heures_ouverture = 0.0
        for d_id in _scope_depts(dept):
            nb = sum(1 for m in db.machines if m["departementId"] == d_id)
            if nb > 0:
                heures_ouverture += nb * opening_hours(db, d_id, start, end)
        dispo = (max(0.0, min(100.0, (1 - temps_arret / heures_ouverture) * 100))
                 if heures_ouverture > 0 else 100.0)

        trend.append({"year": y, "tempsArretH": round(temps_arret, 2),
                      "coutMaint": cout_maint, "kwh": kwh, "disponibilite": dispo})
    return trend


# -- agrégations par département (pour les graphiques) ----------------------
def arrets_by_dept(arrets):
    out = {}
    for a in arrets:
        out[a["departementId"]] = out.get(a["departementId"], 0.0) + hours_between(a["dateDebut"], a["dateFin"])
    return out


def cout_by_dept(intervs):
    out = {}
    for i in intervs:
        out[i["departementId"]] = out.get(i["departementId"], 0.0) + intervention_cost(i)
    return out


def energie_by_dept(energie):
    out = {}
    for e in energie:
        out[e["departementId"]] = out.get(e["departementId"], 0.0) + float(e.get("kwh") or 0)
    return out


def interv_prev_corr_by_dept(intervs):
    """Retourne {deptId: (preventif, correctif/autre)}."""
    out = {}
    for i in intervs:
        prev, corr = out.get(i["departementId"], (0, 0))
        if i["type"] == "Préventif":
            prev += 1
        else:
            corr += 1
        out[i["departementId"]] = (prev, corr)
    return out
