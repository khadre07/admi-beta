"""Calculs des indicateurs de maintenance (KPI) — fonctions pures.

Reproduit fidèlement les formules de l'application ADMI d'origine :
  disponibilité = (1 - tempsArret / heuresOuverture) * 100   (bornée 0..100)
  MTBF          = (heuresOuverture - tempsArret) / nbPannes
  MTTR          = tempsArret / nbArrets
  heuresOuverture = Σ_machines  heures d'ouverture du département de la machine
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import DEPARTEMENTS

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


def compute_kpis(db, periode: str, annee: int, mois: int, dept: str) -> dict:
    start, end = period_bounds(periode, annee, mois)
    arrets = filter_arrets(db, start, end, dept)
    intervs = filter_interventions(db, start, end, dept)
    energie = filter_energie(db, periode, annee, mois, dept)

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
