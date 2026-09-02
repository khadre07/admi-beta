"""AMI — Analyse des Machines Industrielles (application Streamlit).

Lancement :  streamlit run app.py
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_calendar import calendar as st_calendar

from admi import (alerts, auth, charts, config, i18n, kpis, license as lic,
                  report, stock, update)
from admi.config import (DEPARTEMENTS, DOW, MOIS, OBJECTIF_LABELS,
                         OBJECTIF_SENS, OBJECTIF_UNITES, STATUTS_MACHINE, THEME,
                         TYPES_ARRET, TYPES_INTERV, TYPES_PLAN, dep)
from admi.data import (DATA_FILE, delete_record, get_alert_config, load_db,
                       save_alert_config, save_db, save_settings, uid,
                       upsert_record)


def _machine_opts(db):
    return [m["nom"] for m in db.machines], [m["id"] for m in db.machines]


def _dept_picker(label, current="am", key=None):
    ids = [d["id"] for d in DEPARTEMENTS]
    idx = ids.index(current) if current in ids else 0
    return st.selectbox(T(label), ids, index=idx,
                        format_func=lambda i: TD(i, dep(i)["nom"]), key=key)


def _open_edit(prefix, entries, fmt):
    """Sélecteur d'édition : renvoie l'id choisi (ou None). Réinitialisé après action."""
    opts = ["—"] + [fmt(e) for e in entries]
    sel = st.selectbox(T("Modifier un enregistrement existant"), opts, key=f"{prefix}_editsel")
    if sel != "—":
        return entries[opts.index(sel) - 1]["id"]
    return None


def _close_dialog(prefix):
    # NB : on ne modifie PAS la clé du selectbox (interdit après instanciation) ;
    # le garde `*_last_edit` empêche la réouverture automatique du dialogue.
    st.session_state[f"{prefix}_target"] = None
    if prefix == "interv":
        st.session_state["interv_rows_for"] = None


def _crud_controls(db, prefix, add_label, entries, fmt):
    """Bouton « + Ajouter » + sélecteur d'édition. Ouvre le dialogue via *_target."""
    if not can_edit():
        return  # lecteur : lecture seule, aucun contrôle de saisie
    top = st.columns([1, 2])
    with top[0]:
        if st.button(T(add_label), type="primary", key=f"{prefix}_add"):
            st.session_state[f"{prefix}_target"] = ("new", None)
    with top[1]:
        eid = _open_edit(prefix, entries, fmt)
    if eid is None:
        st.session_state[f"{prefix}_last_edit"] = None
    elif (st.session_state.get(f"{prefix}_target") is None
          and eid != st.session_state.get(f"{prefix}_last_edit")):
        st.session_state[f"{prefix}_target"] = ("edit", eid)
        st.session_state[f"{prefix}_last_edit"] = eid

STATUTS_PLAN = ["Planifié", "Réalisé", "En retard", "Annulé"]
STATUT_EMOJI = {"Planifié": "🕓", "Réalisé": "✓", "En retard": "⚠", "Annulé": "✕"}
from admi.io_excel import (LABELS, TYPES, apply_import, export_bytes,
                           parse_import, template_bytes)
from admi.theme import CSS, live_clock_html, register_template

st.set_page_config(page_title="AMI — Analyse de Maintenance Industrielle",
                   page_icon="🏭", layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)
register_template()

PLOTLY_CFG = {
    "displayModeBar": "hover", "displaylogo": False, "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "filename": "admi_graphique", "scale": 2},
}


# ---------------------------------------------------------------------------
# État & helpers
# ---------------------------------------------------------------------------
def get_db():
    # Rechargé à chaque exécution : chaque utilisateur voit les modifications des
    # autres (source de vérité = la base SQLite/PostgreSQL).
    db = load_db()
    st.session_state.db = db
    return db


def _lang():
    return st.session_state.get("lang", "fr")


def T(s):
    return i18n.t(s, _lang())


def TD(dept_id, nom_fr):
    return i18n.dept_label(dept_id, nom_fr, _lang())


def TT(value):
    return i18n.type_label(value, _lang())


def _months():
    return i18n.MOIS_EN if _lang() == "en" else MOIS


def _role():
    return st.session_state.get("role", "viewer")


def can_edit():
    return _role() in ("admin", "operator")


def is_admin():
    return _role() == "admin"


def _maybe_alert(subject, message):
    """Envoie une alerte (email/SMS) si les alertes auto sont activées. Best-effort."""
    try:
        cfg = get_alert_config()
        if cfg.get("enabled"):
            alerts.notify(cfg, subject, message)
    except Exception:
        pass


def fmt_num(n, dec=0):
    return i18n.fmt_num(n, dec)


def fmt_money(n):
    return fmt_num(n, 0) + " FCFA"


def section_title(text, extra=""):
    st.markdown(f'<div class="section-title">{T(text)}<div class="line"></div>{extra}</div>',
                unsafe_allow_html=True)


def kpi_card(label, value, unit="", delta="", color=None, value_size=30):
    color = color or THEME["accent"]
    unit_html = f'<span class="unit"> {unit}</span>' if unit else ""
    delta_html = f'<div class="delta">{delta}</div>' if delta else ""
    st.markdown(
        f'<div class="kpi-card"><div class="bar" style="background:{color}"></div>'
        f'<div class="label">{T(label)}</div>'
        f'<div class="value" style="font-size:{value_size}px">{value}{unit_html}</div>'
        f'{delta_html}</div>', unsafe_allow_html=True)


def dash_section(icon, label):
    """Bandeau de section du tableau de bord (🛠️ Performance, ⚡ Énergie…)."""
    st.markdown(
        f'<div class="dash-section"><span class="label">{icon} {T(label)}</span>'
        f'<div class="line"></div></div>', unsafe_allow_html=True)


def objectif_delta(db, metric, value, prefixe=""):
    """Rappel de l'objectif sous un indicateur : « Objectif ≥ 90 % ✓ ».

    Renvoie une chaîne vide si aucune cible n'est fixée dans Paramètres.
    """
    cible = db.objectif(metric)
    atteint = kpis.objectif_atteint(metric, value, cible)
    if atteint is None:
        return ""
    signe = "≤" if OBJECTIF_SENS[metric] == "max" else "≥"
    unite = OBJECTIF_UNITES[metric]
    dec = 1 if metric == "mttr" else 0
    couleur = THEME["success"] if atteint else THEME["danger"]
    return (f'{prefixe}<span style="color:{couleur}; font-weight:600">'
            f'{T("Objectif")} {signe} {fmt_num(cible, dec)} {unite} {"✓" if atteint else "✗"}</span>')


def objectif_couleur(db, metric, value, defaut):
    """Couleur du chiffre d'une jauge : verte si l'objectif est tenu, rouge sinon."""
    atteint = kpis.objectif_atteint(metric, value, db.objectif(metric))
    if atteint is None:
        return defaut
    return THEME["success"] if atteint else THEME["danger"]


def dept_selectbox(label, key, include_all=True):
    ids = (["all"] if include_all else []) + [d["id"] for d in DEPARTEMENTS]

    def _fmt(i):
        return T("Tous les départements") if i == "all" else TD(i, dep(i)["nom"])

    return st.selectbox(T(label), ids, format_func=_fmt, key=key)


def plot(fig):
    # theme=None : on garde notre template sombre "admi" au lieu du thème Plotly de Streamlit.
    # Clé unique par graphique (compteur réinitialisé à chaque run) pour éviter les
    # collisions d'ID auto-générés (StreamlitDuplicateElementId).
    st.session_state["_plot_n"] = st.session_state.get("_plot_n", 0) + 1
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CFG, theme=None,
                        key=f"plot_{st.session_state['_plot_n']}")


# ---------------------------------------------------------------------------
# SECTION : Tableau de bord
# ---------------------------------------------------------------------------
def _month_fmt(m):
    return _months()[MOIS.index(m)]


def _bandeau_stock(db):
    """Alerte en tête du tableau de bord quand des pièces passent sous leur seuil."""
    alerte = stock.pieces_en_alerte(db.pieces)
    if not alerte:
        return
    noms = ", ".join(p["designation"] for p in alerte[:4])
    if len(alerte) > 4:
        noms += f' {T("et")} {len(alerte) - 4} {T("autre(s)")}'
    st.markdown(
        f'<div class="stock-alert"><div class="ico">⚠️</div><div>'
        f'<b>{len(alerte)} {T("pièce(s) de rechange sous le seuil d\'alerte")}</b>'
        f'<div class="hint">{noms}</div></div></div>', unsafe_allow_html=True)
    if st.button(T("Voir le stock →"), key="dash_goto_stock"):
        # On mémorise la destination : le radio de navigation ne peut pas être
        # modifié une fois instancié, la sidebar l'applique au début du run suivant.
        st.session_state["_goto"] = "Pièces de rechange"
        st.rerun()


def view_dashboard(db):
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
    with c1:
        periode = st.selectbox(T("Période"), ["Mensuelle", "Annuelle"], format_func=T, key="dash_periode")
        periode = "mois" if periode == "Mensuelle" else "annee"
    with c2:
        mois = MOIS.index(st.selectbox(T("Mois"), MOIS, index=min(7, 11),
                                       format_func=_month_fmt, key="dash_mois")) \
            if periode == "mois" else 0
    with c3:
        annee = st.selectbox(T("Année"), list(range(2020, 2027))[::-1], key="dash_annee")
    with c4:
        dept = dept_selectbox("Département", "dash_dept")

    k = kpis.compute_kpis(db, periode, annee, mois, dept)
    _bandeau_stock(db)

    # -- 🛠️ Performance de la maintenance --------------------------------------
    dash_section("🛠️", "Performance de la maintenance")
    left, mid, right = st.columns([1, 1, 1])
    with left:
        section_title("Disponibilité")
        plot(charts.gauge_disponibilite(
            k["disponibilite"],
            couleur=objectif_couleur(db, "disponibilite", k["disponibilite"], THEME["success"]),
            cible=db.objectif("disponibilite")))
        dispo_h = k["heuresOuverture"] - k["tempsArretH"]
        st.markdown(
            f'<div class="gauge-foot">'
            f'<span class="chip good">● {T("Disponible")} — {fmt_num(dispo_h, 1)} h</span>'
            f'<span class="chip bad">● {T("Arrêt")} — {fmt_num(k["tempsArretH"], 1)} h</span></div>'
            f'<div class="gauge-note">{k["nbArrets"]} {T("arrêt(s) sur la période")}'
            f'{objectif_delta(db, "disponibilite", k["disponibilite"], " · ")}</div>',
            unsafe_allow_html=True)
    with mid:
        section_title("Réalisation du préventif")
        taux = k["tauxRealisationPreventif"]
        plot(charts.gauge_taux_preventif(
            taux, couleur=objectif_couleur(db, "tauxPreventif", taux, THEME["success"]),
            cible=db.objectif("tauxPreventif")))
        en_attente = max(0, k["planningDus"] - k["planningRealises"])
        st.markdown(
            f'<div class="gauge-foot">'
            f'<span class="chip good">● {T("Réalisées")} — {k["planningRealises"]}</span>'
            f'<span class="chip warn">● {T("En attente / retard")} — {en_attente}</span></div>'
            f'<div class="gauge-note">{k["planningDus"]} {T("action(s) planifiée(s)")}'
            f'{objectif_delta(db, "tauxPreventif", taux, " · ")}</div>',
            unsafe_allow_html=True)
    with right:
        kpi_card("MTBF", fmt_num(k["mtbf"], 1) if k["mtbf"] is not None else "—",
                 "heures" if k["mtbf"] is not None else "",
                 f'{k["nbPannes"]} {T("panne(s)")}'
                 + objectif_delta(db, "mtbf", k["mtbf"], " · "), THEME["accent2"])
        st.write("")
        kpi_card("MTTR", fmt_num(k["mttr"], 1) if k["mttr"] is not None else "—",
                 "heures" if k["mttr"] is not None else "",
                 T("Temps moyen de réparation")
                 + objectif_delta(db, "mttr", k["mttr"], " · "), THEME["warn"])
        st.write("")
        kpi_card("Temps d'arrêt cumulé", fmt_num(k["tempsArretH"], 1), "heures",
                 objectif_delta(db, "tempsArret", k["tempsArretH"])
                 or T("Objectif non défini dans Paramètres"), "#94A3B8")
        st.write("")
        kpi_card("Coût maintenance", fmt_money(k["coutMaint"]), "",
                 "Pièces + main d'œuvre, période sélectionnée", THEME["success"], value_size=22)

    st.write("")
    start, end = kpis.period_bounds(periode, annee, mois)
    arrets = kpis.filter_arrets(db, start, end, dept)
    intervs = kpis.filter_interventions(db, start, end, dept)
    energie_p = kpis.filter_energie(db, periode, annee, mois, dept)

    r1a, r1b = st.columns(2)
    with r1a:
        section_title("Temps d'arrêt par département (h)")
        plot(charts.bar_arrets_by_dept(kpis.arrets_by_dept(arrets)))
    with r1b:
        section_title("Répartition du coût de maintenance")
        plot(charts.donut_cout_by_dept(kpis.cout_by_dept(intervs)))

    section_title("Interventions préventif / correctif par département")
    plot(charts.grouped_interv_prevcorr(kpis.interv_prev_corr_by_dept(intervs)))

    # -- ⚡ Énergie & puissance --------------------------------------------------
    st.write("")
    dash_section("⚡", "Énergie & puissance")
    g = st.columns(3)
    with g[0]:
        kpi_card("Énergie consommée", fmt_num(k["kwh"], 0), "kWh", color=THEME["accent2"])
    with g[1]:
        kpi_card("Coût énergie", fmt_money(k["coutEnergie"]), "", color=THEME["accent"], value_size=22)
    with g[2]:
        kpi_card("Puissance installée", fmt_num(k["puissanceInstallee"], 0), "kW", color="#94A3B8")

    st.write("")
    r2a, r2b = st.columns(2)
    with r2a:
        section_title("Consommation énergétique par département (kWh)")
        plot(charts.bar_energie_by_dept(kpis.energie_by_dept(energie_p)))
    with r2b:
        section_title("Répartition de la consommation énergétique")
        plot(charts.pie_energie_repartition(kpis.energie_by_dept(energie_p)))

    energie_annee = [e for e in db.energie
                     if e["annee"] == annee and (dept == "all" or e["departementId"] == dept)]
    section_title(f"Consommation énergétique mensuelle — {annee}")
    plot(charts.stacked_energie_mensuelle(energie_annee, dept))

    # -- 📈 Tendance pluriannuelle ----------------------------------------------
    st.write("")
    dash_section("📈", "Tendance pluriannuelle")
    tcol1, tcol2 = st.columns([3, 1])
    with tcol2:
        metric_label = st.selectbox("Métrique de tendance",
                                    ["Temps d'arrêt (h)", "Coût maintenance (FCFA)",
                                     "Consommation énergie (kWh)", "Disponibilité (%)"],
                                    key="trend_metric")
    metric_map = {"Temps d'arrêt (h)": "tempsArretH", "Coût maintenance (FCFA)": "coutMaint",
                  "Consommation énergie (kWh)": "kwh", "Disponibilité (%)": "disponibilite"}
    with tcol1:
        section_title("Depuis 2020")
        st.markdown(
            f'<div style="color:{THEME["muted2"]}; font-size:12px; margin-bottom:6px">'
            f'{T("Vue annuelle calculée sur toutes les données saisies ou importées depuis 2020, "
                 "pour le département sélectionné plus haut.")}</div>', unsafe_allow_html=True)
    plot(charts.line_trend(kpis.yearly_trend(db, dept), metric_map[metric_label]))


# ---------------------------------------------------------------------------
# SECTION : Machines & Puissance
# ---------------------------------------------------------------------------
def view_machines(db):
    _crud_controls(db, "mach", "＋ Nouvelle machine", db.machines,
                   lambda m: f'{m["nom"]} ({dep(m["departementId"])["court"]})')
    total_kw = sum(float(m.get("puissanceKW") or 0) for m in db.machines)
    section_title("Bilan de puissance installée",
                  f'<span style="color:{THEME["accent"]}; font-family:JetBrains Mono">'
                  f'{fmt_num(total_kw)} kW total</span>')
    plot(charts.bar_puissance_by_dept(db))

    section_title("Parc machines")
    rows = [{T("Machine"): m["nom"], T("Dépt."): dep(m["departementId"])["court"],
             T("Puissance (kW)"): m.get("puissanceKW", 0), T("Mise en service"): m.get("dateMES", ""),
             T("Statut"): TT(m.get("statut", ""))} for m in db.machines]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if st.session_state.get("mach_target"):
        machine_dialog(db, st.session_state.mach_target)


# ---------------------------------------------------------------------------
# SECTION : Pièces de rechange
# ---------------------------------------------------------------------------
_STATUT_PIECE = {"ok": ("✓", "OK", "success"),
                 "alerte": ("⚠", "Stock bas", "warn"),
                 "rupture": ("✕", "Rupture", "danger")}


def _piece_label(p):
    court = dep(p["departementId"])["court"] if p.get("departementId") else "—"
    return f'{p["designation"]} ({court})'


def view_pieces(db):
    _crud_controls(db, "piece", "＋ Nouvelle pièce", sorted(db.pieces, key=lambda p: p["designation"]),
                   _piece_label)
    if can_edit() and db.pieces:
        if st.button(T("↕ Mouvement de stock"), key="piece_mvt_btn"):
            st.session_state["piece_mvt_target"] = ("new", None)

    t = stock.totaux(db.pieces)
    g = st.columns(4)
    with g[0]:
        kpi_card("Références en stock", fmt_num(t["references"]), color=THEME["accent2"])
    with g[1]:
        kpi_card("Valeur totale du stock", fmt_money(t["valeur"]), color=THEME["success"], value_size=22)
    with g[2]:
        kpi_card("Sous le seuil d'alerte", fmt_num(t["alerte"]),
                 color=THEME["warn"] if t["alerte"] else THEME["success"])
    with g[3]:
        kpi_card("En rupture", fmt_num(t["rupture"]),
                 color=THEME["danger"] if t["rupture"] else THEME["success"])

    st.write("")
    f1, f2 = st.columns([1, 1])
    with f1:
        dept = dept_selectbox("Filtrer par département", "piece_dept")
    with f2:
        st.write("")
        alertes_only = st.checkbox(T("Afficher uniquement les alertes et ruptures"), key="piece_alerte_only")

    liste = [p for p in db.pieces
             if (dept == "all" or p.get("departementId") == dept)
             and not (alertes_only and stock.piece_statut(p) == "ok")]
    liste.sort(key=lambda p: p["designation"])

    section_title("Catalogue des pièces",
                  f'<span style="color:{THEME["muted"]}; font-family:JetBrains Mono; font-size:12px">'
                  f'{len(liste)} {T("référence(s)")}</span>')
    if not liste:
        st.info(T("Aucune pièce ne correspond à ce filtre. Ajoutez une référence pour suivre son stock."))
    else:
        rows = []
        for p in liste:
            icone, libelle, _ = _STATUT_PIECE[stock.piece_statut(p)]
            rows.append({
                T("Désignation"): p["designation"],
                T("Réf."): p.get("reference", "") or "—",
                T("Dépt."): dep(p["departementId"])["court"] if p.get("departementId") else "—",
                T("Emplacement"): p.get("emplacement", "") or "—",
                T("Quantité"): f'{fmt_num(p.get("quantite", 0))} {p.get("unite", "")}'.strip(),
                T("Seuil"): fmt_num(p.get("seuilAlerte", 0)),
                T("Statut"): f"{icone} {T(libelle)}",
                T("Coût unit."): fmt_money(p.get("coutUnitaire", 0)),
                T("Valeur"): fmt_money(stock.piece_valeur(p)),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    section_title("Historique des mouvements de stock")
    if not db.mouvements:
        st.info(T("Les entrées, sorties et ajustements de stock apparaîtront ici."))
    else:
        noms = {p["id"]: p["designation"] for p in db.pieces}
        recents = sorted(db.mouvements, key=lambda m: m.get("date", ""), reverse=True)[:50]
        signe = {"Entrée": "+", "Sortie": "−", "Ajustement": "±"}
        rows = [{T("Date"): m.get("date", ""),
                 T("Pièce"): noms.get(m["pieceId"], T("Pièce supprimée")),
                 T("Type"): TT(m["type"]),
                 T("Quantité"): f'{signe.get(m["type"], "")}{fmt_num(abs(float(m.get("quantite") or 0)))}',
                 T("Motif"): m.get("motif", "") or "—"} for m in recents]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if st.session_state.get("piece_target"):
        piece_dialog(db, st.session_state.piece_target)
    if st.session_state.get("piece_mvt_target"):
        mouvement_dialog(db, st.session_state.piece_mvt_target)


# ---------------------------------------------------------------------------
# SECTION : Temps d'arrêt
# ---------------------------------------------------------------------------
def view_arrets(db):
    _crud_controls(db, "arret", "＋ Nouvel arrêt",
                   sorted(db.arrets, key=lambda a: a["dateDebut"], reverse=True),
                   lambda a: f'{db.machine_name(a["machineId"])} · {a["dateDebut"].replace("T", " ")} · {a["type"]}')
    dept = dept_selectbox("Filtrer par département", "arret_dept")
    arrets = [a for a in db.arrets if dept == "all" or a["departementId"] == dept]
    arrets.sort(key=lambda a: a["dateDebut"], reverse=True)

    c1, c2 = st.columns([1, 2])
    with c1:
        kpi_card("Arrêts enregistrés", fmt_num(len(arrets)), color=THEME["accent2"])
    with c2:
        section_title("Répartition des arrêts par type (h)")
        plot(charts.bar_arrets_by_type(arrets, height=200))

    g1, g2 = st.columns(2)
    with g1:
        section_title("Top 5 des machines les plus problématiques")
        st.caption(T("Classées par nombre de pannes ; le temps d'arrêt cumulé "
                     "apparaît au survol."))
        plot(charts.bar_top_machines(arrets, db.machines, height=280))
    with g2:
        section_title("Top 5 des causes d'arrêt (Pareto)")
        st.caption(T("Barres = occurrences ; le pourcentage cumulé est écrit "
                     "sur chaque barre."))
        plot(charts.pareto_causes(arrets, height=280))

    section_title("Journal des arrêts")
    rows = [{T("Machine"): db.machine_name(a["machineId"]), T("Dépt."): dep(a["departementId"])["court"],
             T("Type"): TT(a["type"]), T("Début"): a["dateDebut"].replace("T", " "),
             T("Fin"): a["dateFin"].replace("T", " "),
             T("Durée (h)"): round(kpis.hours_between(a["dateDebut"], a["dateFin"]), 1),
             T("Cause"): a.get("cause", "")} for a in arrets]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if st.session_state.get("arret_target"):
        arret_dialog(db, st.session_state.arret_target)


# ---------------------------------------------------------------------------
# SECTION : Interventions
# ---------------------------------------------------------------------------
def view_interventions(db):
    _crud_controls(db, "interv", "＋ Nouveau rapport",
                   sorted(db.interventions, key=lambda i: i["date"], reverse=True),
                   lambda i: f'{i["date"]} · {db.machine_name(i["machineId"])} · {i["type"]}')
    dept = dept_selectbox("Filtrer par département", "interv_dept")
    intervs = [i for i in db.interventions if dept == "all" or i["departementId"] == dept]
    intervs.sort(key=lambda i: i["date"], reverse=True)
    total = sum(kpis.intervention_cost(i) for i in intervs)
    n_prev = sum(1 for i in intervs if i["type"] == "Préventif")

    c = st.columns(3)
    with c[0]:
        kpi_card("Rapports", fmt_num(len(intervs)), color=THEME["accent2"])
    with c[1]:
        kpi_card("Coût total (pièces + MO)", fmt_money(total), color=THEME["accent"], value_size=22)
    with c[2]:
        ratio = (n_prev / len(intervs) * 100) if intervs else 0
        kpi_card("Part préventif", f"{fmt_num(ratio,1)} %", color=THEME["success"])

    section_title("Rapports d'intervention")
    rows = []
    for i in intervs:
        n_pieces = len(i.get("pieces", []))
        rows.append({T("Date"): i["date"], T("Machine"): db.machine_name(i["machineId"]),
                     T("Dépt."): dep(i["departementId"])["court"], T("Type"): TT(i["type"]),
                     T("Technicien"): i.get("technicien", ""),
                     T("Durée (h)"): i.get("duree", 0), T("Pièces"): n_pieces,
                     T("Coût total (FCFA)"): round(kpis.intervention_cost(i))})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Rapport d'intervention (fiche PDF par intervention)
    if intervs:
        section_title("Générer un rapport d'intervention")
        opts = [f'{i["date"]} · {db.machine_name(i["machineId"])} · {i["type"]}' for i in intervs]
        g1, g2 = st.columns([2, 1])
        with g1:
            sel = st.selectbox("Intervention", opts, key="interv_report_sel")
        chosen = intervs[opts.index(sel)]
        with g2:
            st.write("")
            st.download_button(T("⬇ Rapport d'intervention (PDF)"),
                               report.build_intervention_report(db, chosen),
                               file_name=f"AMI_intervention_{chosen['date']}.pdf",
                               mime="application/pdf", width="stretch")

    if st.session_state.get("interv_target"):
        interv_dialog(db, st.session_state.interv_target)


# ---------------------------------------------------------------------------
# SECTION : Énergie
# ---------------------------------------------------------------------------
def view_energie(db):
    annee = st.selectbox("Année", list(range(2020, 2027))[::-1], key="energie_annee")
    liste = [e for e in db.energie if e["annee"] == annee]
    _crud_controls(db, "energie", "＋ Saisir une consommation",
                   sorted(liste, key=lambda e: (e["mois"], dep(e["departementId"])["nom"])),
                   lambda e: f'{MOIS[e["mois"]]} {e["annee"]} · {dep(e["departementId"])["nom"]}')
    total_kwh = sum(float(e.get("kwh") or 0) for e in liste)
    total_cost = sum(float(e.get("montant") or 0) for e in liste)

    c = st.columns(3)
    with c[0]:
        kpi_card(f"Consommation {annee}", fmt_num(total_kwh), "kWh", color=THEME["accent2"])
    with c[1]:
        kpi_card("Coût énergie total", fmt_money(total_cost), color=THEME["success"], value_size=22)
    with c[2]:
        kpi_card("Nombre de relevés", fmt_num(len(liste)), color=THEME["accent"])

    agg = kpis.energie_by_dept(liste)
    a, b = st.columns(2)
    with a:
        section_title("Répartition par département / service")
        plot(charts.bar_energie_by_dept(agg))
    with b:
        section_title("Part de chaque département (%)")
        plot(charts.pie_energie_repartition(agg))

    section_title("Relevés détaillés")
    rows = [{T("Mois"): i18n.month(e["mois"]), T("Département / Service"): TD(e["departementId"], dep(e["departementId"])["nom"]),
             T("Consommation (kWh)"): e["kwh"], T("Montant (FCFA)"): e["montant"]}
            for e in sorted(liste, key=lambda e: (e["mois"], dep(e["departementId"])["nom"]))]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if st.session_state.get("energie_target"):
        energie_dialog(db, st.session_state.energie_target)


# ---------------------------------------------------------------------------
# SECTION : Import / Export Excel
# ---------------------------------------------------------------------------
def view_import(db):
    exp, tpl = st.columns(2)
    with exp:
        section_title("Exporter les données actuelles")
        st.download_button(T("⬇ Exporter en Excel"), export_bytes(db),
                           file_name="AMI_export.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with tpl:
        section_title("Modèle d'import")
        st.download_button(T("⬇ Télécharger le modèle Excel"), template_bytes(),
                           file_name="AMI_modele_import.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    if not can_edit():
        st.info("L'import de données est réservé aux comptes éditeurs (operator / admin). "
                "L'export ci-dessus reste disponible.")
        return

    section_title("Importer un fichier")
    up = st.file_uploader(
        "Fichier Excel, CSV, Word ou PDF (Machines, Arrêts, Énergie, Interventions, Planning)",
        type=["xlsx", "xls", "csv", "docx", "pdf"])
    st.caption("Excel/CSV : une feuille par type. Word/PDF : les données doivent être en **tableaux** "
               "avec une ligne d'en-tête (mêmes colonnes que le modèle) — pas de texte libre.")
    if up is not None:
        try:
            result = parse_import(up.getvalue(), up.name, db)
        except Exception as exc:  # noqa: BLE001 - message utilisateur
            st.error(f"Impossible d'exploiter ce fichier : {exc}")
            return
        st.session_state.pending = result

    pending = st.session_state.get("pending")
    if pending:
        cols = st.columns(6)
        for idx, t in enumerate(TYPES):
            with cols[idx]:
                kpi_card(LABELS[t], fmt_num(len(pending[t])), "ligne(s)", color=THEME["success"], value_size=22)
        with cols[5]:
            kpi_card("Erreurs", fmt_num(len(pending["errors"])),
                     color=THEME["danger"] if pending["errors"] else THEME["muted"], value_size=22)

        if pending["errors"]:
            with st.expander(f"⚠️ {len(pending['errors'])} ligne(s) ignorée(s)"):
                for e in pending["errors"]:
                    st.markdown(f"**{LABELS.get(e['type'], e['type'])}** — feuille "
                                f"« {e['sheet']} », ligne {e['line']} : {e['message']}")

        mode_label = st.radio("Mode d'import",
                              ["Ajouter aux données existantes", "Remplacer les données existantes"],
                              key="import_mode")
        mode = "append" if mode_label.startswith("Ajouter") else "replace"
        if mode == "replace":
            st.warning("« Remplacer » écrase définitivement, pour chaque type présent dans le fichier, "
                       "les données déjà enregistrées dans AMI.")
        b1, b2 = st.columns([1, 4])
        with b1:
            if st.button("Confirmer l'import", type="primary"):
                total = apply_import(db, pending, mode)
                save_db(db)
                st.session_state.pending = None
                st.success(f"Import terminé : {total} ligne(s) intégrée(s).")
                st.rerun()
        with b2:
            if st.button("Annuler"):
                st.session_state.pending = None
                st.rerun()


# ---------------------------------------------------------------------------
# SECTION : Planning (calendrier interactif)
# ---------------------------------------------------------------------------
CAL_CSS = f"""
.fc {{ --fc-border-color:{THEME['border']}; --fc-page-bg-color:transparent; }}
.fc .fc-toolbar-title {{ color:{THEME['text']}; font-family:'Oswald',sans-serif;
  text-transform:uppercase; letter-spacing:.03em; font-size:20px; }}
.fc .fc-col-header-cell-cushion, .fc .fc-daygrid-day-number {{
  color:{THEME['muted']}; text-decoration:none; font-size:12px; }}
.fc-theme-standard td, .fc-theme-standard th {{ border-color:{THEME['border']}; }}
.fc .fc-day-today {{ background: rgba(242,169,59,0.08) !important; }}
.fc .fc-daygrid-day-frame {{ min-height: 88px; }}
.fc .fc-button-primary {{ background:{THEME['panel2']}; border-color:{THEME['border_light']};
  color:{THEME['text']}; text-transform:capitalize; }}
.fc .fc-button-primary:hover {{ background:{THEME['border']}; }}
.fc .fc-button-primary:not(:disabled).fc-button-active,
.fc .fc-button-primary:not(:disabled):active {{
  background:{THEME['accent']}; border-color:{THEME['accent']}; color:#1A1200; }}
.fc-event {{ cursor:pointer; font-size:11px; padding:1px 4px; }}
.fc a {{ color:inherit; }}
"""
CAL_OPTIONS = {
    "headerToolbar": {"left": "prev,next today", "center": "title",
                      "right": "dayGridMonth,multiMonthYear"},
    "initialView": "dayGridMonth", "locale": "fr", "firstDay": 1, "height": 720,
    "buttonText": {"today": "Aujourd'hui", "month": "Mois", "year": "Année"},
    "dayMaxEvents": 3, "navLinks": True,
}


def _planning_events(db):
    events = []
    for p in db.planning:
        color = dep(p["departementId"])["couleur"]
        faded = p["statut"] in ("Réalisé", "Annulé")
        events.append({
            "id": p["id"],
            "title": f'{STATUT_EMOJI.get(p["statut"], "")} {p["titre"]}',
            "start": p["date"], "allDay": True,
            "backgroundColor": THEME["panel2"] if faded else color,
            "borderColor": color,
            "textColor": THEME["muted"] if faded else "#0A1220",
        })
    return events


def _add_months(d: date, n: int) -> date:
    total = d.month - 1 + n
    y, m = d.year + total // 12, total % 12 + 1
    last = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
    return date(y, m, min(d.day, last.day))


def _repeat_dates(d: date, repeat: str):
    if "semaine" in repeat:
        return [d + timedelta(weeks=i) for i in range(8)]
    if "mois" in repeat:
        return [_add_months(d, i) for i in range(6)]
    if "trimestre" in repeat:
        return [_add_months(d, i * 3) for i in range(4)]
    return [d]


@st.dialog("Planification d'intervention")
def planning_dialog(db, target):
    mode, val = target
    p = next((x for x in db.planning if x["id"] == val), None) if mode == "edit" else None
    titre = st.text_input("Titre", value=(p["titre"] if p else ""),
                          placeholder="Ex : Graissage mensuel presse AM-1")
    c1, c2 = st.columns(2)
    d = c1.date_input("Date", value=date.fromisoformat(p["date"] if p else val), format="DD/MM/YYYY")
    ptype = c2.selectbox("Type", TYPES_PLAN,
                         index=(TYPES_PLAN.index(p["type"]) if p and p["type"] in TYPES_PLAN else 0))
    names = [m["nom"] for m in db.machines]
    ids = [m["id"] for m in db.machines]
    midx = ids.index(p["machineId"]) if p and p["machineId"] in ids else 0
    mname = st.selectbox("Machine", names, index=midx)
    machine_id = ids[names.index(mname)]
    statut = st.selectbox("Statut", STATUTS_PLAN,
                          index=(STATUTS_PLAN.index(p["statut"]) if p and p["statut"] in STATUTS_PLAN else 0))
    repeat = "Aucune"
    if mode != "edit":
        repeat = st.selectbox("Répétition", ["Aucune (ponctuel)", "Chaque semaine × 8",
                                             "Chaque mois × 6", "Chaque trimestre × 4"])
    desc = st.text_area("Description", value=(p.get("description", "") if p else ""))

    b1, b2, b3 = st.columns(3)
    if b1.button("Enregistrer", type="primary", width="stretch"):
        if not titre.strip():
            st.warning("Le titre est requis.")
        else:
            base = {"machineId": machine_id, "departementId": db.machine_dept(machine_id),
                    "titre": titre.strip(), "type": ptype, "statut": statut, "description": desc.strip()}
            if mode == "edit" and p:
                upsert_record(db, "planning", {**p, **base, "date": d.isoformat()})
            else:
                for dd in _repeat_dates(d, repeat):
                    upsert_record(db, "planning", {"id": uid(), **base, "date": dd.isoformat()})
            st.session_state.plan_target = None
            st.rerun()
    if mode == "edit" and p and b2.button("Supprimer", width="stretch"):
        delete_record(db, "planning", p["id"])
        st.session_state.plan_target = None
        st.rerun()
    if b3.button("Annuler", width="stretch"):
        st.session_state.plan_target = None
        st.rerun()


def view_planning(db):
    if st.button("＋ Planifier une intervention", type="primary"):
        st.session_state.plan_target = ("new", date.today().isoformat())

    state = st_calendar(events=_planning_events(db), options=CAL_OPTIONS,
                        custom_css=CAL_CSS, key="planning_cal")
    # n'agir que sur une nouvelle interaction (le composant renvoie sa dernière valeur à chaque rerun)
    sig = json.dumps(state, sort_keys=True, default=str) if state else ""
    if state and sig != st.session_state.get("planning_sig"):
        st.session_state.planning_sig = sig
        cb = state.get("callback")
        if cb == "eventClick":
            st.session_state.plan_target = ("edit", state["eventClick"]["event"]["id"])
        elif cb in ("dateClick", "select"):
            payload = state.get("dateClick") or state.get("select")
            st.session_state.plan_target = ("new", str(payload["date"])[:10])

    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:12px">' +
        "".join(
            f'<span style="display:inline-flex; align-items:center; gap:5px; font-size:11px; '
            f'color:{d["couleur"]}"><span style="width:8px;height:8px;border-radius:50%;'
            f'background:{d["couleur"]}"></span>{d["nom"]}</span>'
            for d in DEPARTEMENTS
        ) + "</div>", unsafe_allow_html=True)

    if st.session_state.get("plan_target"):
        planning_dialog(db, st.session_state.plan_target)


# ---------------------------------------------------------------------------
# SECTION : Paramètres (heures de travail par département)
# ---------------------------------------------------------------------------
def view_settings(db):
    section_title("Heures de travail par département")
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:12px">'
        "Ces horaires définissent le temps d'ouverture théorique de chaque département : ils servent de "
        "référence pour calculer la <b>disponibilité</b>, le <b>MTBF</b> et le <b>MTTR</b>. Par défaut, un "
        "département est en marche continue (24h/24, 7j/7) — décochez les jours non travaillés et ajustez "
        "les heures/jour (ex : Administration = 8h, du lundi au vendredi).</div>", unsafe_allow_html=True)

    if not is_admin():
        rows = [{"Département": d["nom"],
                 "Heures/j": db.dept_schedule(d["id"])["heuresParJour"],
                 "Total/sem": round(sum(db.dept_schedule(d["id"])["jours"]) * db.dept_schedule(d["id"])["heuresParJour"], 1)}
                for d in DEPARTEMENTS]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.info("Modification réservée aux administrateurs.")
        _settings_objectifs(db)
        _settings_departements(db)
        return

    with st.form("settings_form"):
        head = st.columns([2.4, 1] + [0.5] * 7 + [1])
        for col, label in zip(head, ["Département", "Heures/j", *DOW, "Total/sem"]):
            col.markdown(f'<div style="font-size:10.5px; color:{THEME["muted"]}; text-transform:uppercase; '
                         f'font-weight:700">{label}</div>', unsafe_allow_html=True)
        pending = {}
        for d in DEPARTEMENTS:
            s = db.dept_schedule(d["id"])
            row = st.columns([2.4, 1] + [0.5] * 7 + [1])
            row[0].markdown(f'<span style="color:{d["couleur"]}">●</span> {d["nom"]}', unsafe_allow_html=True)
            h = row[1].number_input("h", 0.0, 24.0, float(s["heuresParJour"]), 0.5,
                                    key=f"h_{d['id']}", label_visibility="collapsed")
            days = [row[2 + i].checkbox("j", value=bool(s["jours"][i]), key=f"j_{d['id']}_{i}",
                                        label_visibility="collapsed") for i in range(7)]
            row[9].markdown(f'<div style="color:{THEME["accent"]}; font-weight:600; font-family:JetBrains Mono">'
                            f'{fmt_num(sum(days) * h, 1)} h</div>', unsafe_allow_html=True)
            pending[d["id"]] = (h, days)
        if st.form_submit_button("Enregistrer les horaires", type="primary"):
            for did, (h, days) in pending.items():
                s = db.dept_schedule(did)
                s["heuresParJour"] = h
                s["jours"] = list(days)
            save_settings(db)
            st.success("Horaires enregistrés — la disponibilité, le MTBF et le MTTR en tiennent compte.")

    _settings_objectifs(db)
    _settings_departements(db)


def _save_departements(db):
    """Persiste la liste courante et la garde synchronisée avec config."""
    db.settings["departements"] = [dict(d) for d in DEPARTEMENTS]
    save_settings(db)


def _settings_departements(db):
    """Ajout, modification et suppression des départements de l'usine."""
    st.write("")
    section_title("Départements de l'usine")
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:12px">'
        + T("Un département ajouté ici devient immédiatement disponible dans tous les formulaires "
            "(machines, arrêts, énergie, interventions, planning, pièces) et prend sa couleur dans "
            "tous les graphiques.")
        + "</div>", unsafe_allow_html=True)

    rows = [{T("Nom"): TD(d["id"], d["nom"]), T("Code"): d["court"],
             T("Couleur"): d["couleur"], T("Enregistrements"): db.dept_usage(d["id"])}
            for d in DEPARTEMENTS]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if not is_admin():
        st.info("Modification réservée aux administrateurs.")
        return

    ids = [d["id"] for d in DEPARTEMENTS]
    cible = st.selectbox(T("Département à modifier"), ["__new__"] + ids,
                         format_func=lambda i: T("＋ Nouveau département") if i == "__new__"
                         else f'{dep(i)["nom"]} ({dep(i)["court"]})',
                         key="dept_cible")
    courant = dep(cible) if cible != "__new__" else None

    with st.form("dept_form"):
        c1, c2, c3 = st.columns([2.4, 1, 1])
        nom = c1.text_input(T("Nom complet"), value=(courant["nom"] if courant else ""),
                            placeholder="Ex : Menuiserie Métallique")
        court = c2.text_input(T("Code court"), value=(courant["court"] if courant else ""),
                              max_chars=5, placeholder="MM")
        couleur = c3.color_picker(T("Couleur"), value=(courant["couleur"] if courant else "#7C83FD"))
        enregistrer = st.form_submit_button(T("Enregistrer le département"), type="primary")

    if enregistrer:
        if not nom.strip() or not court.strip():
            st.error(T("Le nom et le code court sont requis."))
        elif courant:
            courant.update({"nom": nom.strip(), "court": court.strip().upper(), "couleur": couleur})
            config.set_departements(DEPARTEMENTS)
            _save_departements(db)
            st.success(T("Département enregistré."))
            st.rerun()
        else:
            nouveau = {"id": config.new_dept_id(nom, ids), "nom": nom.strip(),
                       "court": court.strip().upper(), "couleur": couleur}
            config.set_departements([*DEPARTEMENTS, nouveau])
            _save_departements(db)
            st.success(T("Département ajouté."))
            st.rerun()

    if courant:
        usage = db.dept_usage(cible)
        st.write("")
        if usage:
            st.warning(
                f'{usage} {T("enregistrement(s) utilisent ce département. Si vous le supprimez, "
                             "ils resteront en base mais n\'afficheront plus de département reconnu.")}')
        if st.button(T("Supprimer ce département"), key="dept_del"):
            st.session_state["dept_confirm"] = cible
        if st.session_state.get("dept_confirm") == cible:
            st.error(T("Confirmez la suppression :") + f' **{courant["nom"]}**')
            b = st.columns(2)
            if b[0].button(T("Oui, supprimer"), key="dept_del_ok", type="primary"):
                config.set_departements([d for d in DEPARTEMENTS if d["id"] != cible])
                _save_departements(db)
                st.session_state["dept_confirm"] = None
                st.rerun()
            if b[1].button(T("Annuler"), key="dept_del_no"):
                st.session_state["dept_confirm"] = None
                st.rerun()

    st.write("")
    if st.button(T("Réinitialiser les 8 départements d'usine"), key="dept_reset"):
        st.session_state["dept_reset_confirm"] = True
    if st.session_state.get("dept_reset_confirm"):
        st.error(T("Vos ajouts et modifications de départements seront perdus. "
                   "Les machines, arrêts, énergie, interventions, planning et pièces restent intacts."))
        b = st.columns(2)
        if b[0].button(T("Oui, réinitialiser"), key="dept_reset_ok", type="primary"):
            config.reset_departements()
            _save_departements(db)
            st.session_state["dept_reset_confirm"] = False
            st.rerun()
        if b[1].button(T("Annuler"), key="dept_reset_no"):
            st.session_state["dept_reset_confirm"] = False
            st.rerun()


def _settings_objectifs(db):
    """Cibles de performance rappelées sous chaque indicateur du tableau de bord."""
    st.write("")
    section_title("Objectifs de performance")
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:12px">'
        + T("Chaque objectif s'affiche sous son indicateur au tableau de bord, en vert s'il est tenu "
            "et en rouge sinon. Laissez un champ vide pour ne pas fixer de cible.")
        + "</div>", unsafe_allow_html=True)

    if not is_admin():
        rows = [{T("Indicateur"): T(OBJECTIF_LABELS[m]),
                 T("Cible"): (f'{"≤" if OBJECTIF_SENS[m] == "max" else "≥"} '
                              f'{fmt_num(db.objectif(m), 1 if m == "mttr" else 0)} {OBJECTIF_UNITES[m]}'
                              if db.objectif(m) is not None else "—")}
                for m in OBJECTIF_LABELS]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.info("Modification réservée aux administrateurs.")
        return

    with st.form("objectifs_form"):
        cols = st.columns(len(OBJECTIF_LABELS))
        saisis = {}
        for col, metric in zip(cols, OBJECTIF_LABELS):
            sens = "≤" if OBJECTIF_SENS[metric] == "max" else "≥"
            courant = db.objectif(metric)
            with col:
                st.markdown(
                    f'<div style="font-size:10.5px; color:{THEME["muted"]}; text-transform:uppercase; '
                    f'font-weight:700">{T(OBJECTIF_LABELS[metric])}</div>'
                    f'<div style="font-size:11px; color:{THEME["muted2"]}; margin-bottom:2px">'
                    f'{sens} … {OBJECTIF_UNITES[metric]}</div>', unsafe_allow_html=True)
                saisis[metric] = st.text_input("obj", value="" if courant is None else f"{courant:g}",
                                               key=f"obj_{metric}", label_visibility="collapsed",
                                               placeholder=T("aucune"))
        if st.form_submit_button("Enregistrer les objectifs", type="primary"):
            objectifs, invalides = {}, []
            for metric, brut in saisis.items():
                brut = (brut or "").strip().replace(",", ".")
                if not brut:
                    continue
                try:
                    objectifs[metric] = float(brut)
                except ValueError:
                    invalides.append(T(OBJECTIF_LABELS[metric]))
            if invalides:
                st.error(T("Valeur non numérique pour :") + " " + ", ".join(invalides))
            else:
                db.settings["objectifs"] = objectifs
                save_settings(db)
                st.success("Objectifs enregistrés — ils apparaissent sous les indicateurs du tableau de bord.")


# ---------------------------------------------------------------------------
# SECTION : Utilisateurs (admin uniquement)
# ---------------------------------------------------------------------------
def view_users(db):
    users = auth.list_users()
    section_title("Comptes utilisateurs")
    st.dataframe(pd.DataFrame([{"Identifiant": u, "Rôle": r} for u, r in users.items()]),
                 width="stretch", hide_index=True)
    st.caption("Rôles — **admin** : tout · **operator** : saisie des données · **viewer** : lecture seule.")

    section_title("Ajouter un utilisateur")
    with st.form("add_user_form", clear_on_submit=True):
        c = st.columns([2, 2, 1.4, 1.1])
        nu = c[0].text_input("Identifiant")
        npw = c[1].text_input("Mot de passe", type="password")
        nrole = c[2].selectbox("Rôle", auth.ROLES, index=auth.ROLES.index("operator"))
        if c[3].form_submit_button("Ajouter", type="primary"):
            ok, msg = auth.create_user(nu, npw, nrole)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    section_title("Modifier / supprimer")
    target = st.selectbox("Utilisateur", list(users.keys()), key="user_target")
    if target:
        cc = st.columns([1.6, 1, 1.6, 1, 1.2])
        role = cc[0].selectbox("Rôle", auth.ROLES, index=auth.ROLES.index(users[target]), key="user_role")
        if cc[1].button("Appliquer", key="user_role_btn"):
            ok, msg = auth.set_role(target, role)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        newpw = cc[2].text_input("Nouveau mot de passe", type="password", key="user_pw")
        if cc[3].button("Réinit.", key="user_pw_btn"):
            if newpw:
                auth.set_password(target, newpw)
                st.success("Mot de passe réinitialisé.")
            else:
                st.warning("Saisissez un mot de passe.")
        if cc[4].button("Supprimer", key="user_del_btn"):
            ok, msg = auth.delete_user(target)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()


# ---------------------------------------------------------------------------
# SECTION : Alertes (admin uniquement)
# ---------------------------------------------------------------------------
def view_alerts(db):
    cfg = get_alert_config()
    st.markdown(f'<div style="color:{THEME["muted2"]}; font-size:12.5px; margin-bottom:8px">'
                + T("Recevez une alerte (e-mail / SMS) en cas de nouvelle panne. "
                    "Configurez le serveur d'envoi ci-dessous.") + "</div>", unsafe_allow_html=True)
    with st.form("alert_form"):
        enabled = st.toggle(T("Alertes automatiques (nouvelle panne / machine en panne)"),
                            value=cfg.get("enabled", False))
        section_title("Notifications par e-mail")
        emails = st.text_input(T("Destinataires e-mail (séparés par des virgules)"),
                               value=", ".join(cfg.get("emails", [])))
        smtp = cfg.get("smtp", {})
        c1, c2, c3 = st.columns([2, 1, 1])
        host = c1.text_input("SMTP", value=smtp.get("host", ""), placeholder="smtp.gmail.com")
        port = c2.number_input("Port", 1, 65535, int(smtp.get("port", 587)))
        tls = c3.checkbox("TLS", value=smtp.get("tls", True))
        c4, c5, c6 = st.columns(3)
        user = c4.text_input(T("Utilisateur"), value=smtp.get("user", ""))
        pwd = c5.text_input(T("Mot de passe"), value=smtp.get("password", ""), type="password")
        frm = c6.text_input("From", value=smtp.get("from", ""))
        section_title("SMS (Twilio)")
        tw = cfg.get("twilio", {})
        d1, d2, d3 = st.columns(3)
        sid = d1.text_input("Twilio SID", value=tw.get("sid", ""))
        token = d2.text_input("Twilio Token", value=tw.get("token", ""), type="password")
        tfrom = d3.text_input(T("Numéro Twilio (From)"), value=tw.get("from", ""))
        numbers = st.text_input(T("Numéros SMS (séparés par des virgules)"),
                                value=", ".join(cfg.get("sms_numbers", [])))
        saved = st.form_submit_button(T("Enregistrer la configuration"), type="primary")
    if saved:
        newcfg = {"enabled": enabled,
                  "emails": [x.strip() for x in emails.split(",") if x.strip()],
                  "smtp": {"host": host, "port": int(port), "user": user,
                           "password": pwd, "from": frm, "tls": tls},
                  "sms_numbers": [x.strip() for x in numbers.split(",") if x.strip()],
                  "twilio": {"sid": sid, "token": token, "from": tfrom}}
        save_alert_config(newcfg)
        st.success(T("Configuration enregistrée."))
        st.rerun()
    if st.button(T("Envoyer une alerte de test")):
        res = alerts.notify(get_alert_config(), "AMI — Test", T("Ceci est un test d'alerte AMI."))
        if not res:
            st.warning(T("Aucun canal configuré (e-mail ou SMS)."))
        for chan, (ok, msg) in res.items():
            (st.success if ok else st.error)(f"{chan} : {msg}")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
def _nav():
    """Construit la navigation à l'exécution (toutes les vues sont alors définies)."""
    sections = {
        "Tableau de bord": view_dashboard,
        "Planning": view_planning,
        "Machines & Puissance": view_machines,
        "Pièces de rechange": view_pieces,
        "Temps d'arrêt": view_arrets,
        "Interventions": view_interventions,
        "Énergie": view_energie,
        "Rapports": view_report,
        "Import / Export": view_import,
        "Paramètres": view_settings,
    }
    if is_admin():
        sections["Alertes"] = view_alerts
        sections["Utilisateurs"] = view_users
    subtitles = {
        "Tableau de bord": "Vue d'ensemble des indicateurs de maintenance",
        "Planning": "Calendrier des interventions planifiées (mois / année)",
        "Machines & Puissance": "Parc machines et puissance installée par département",
        "Pièces de rechange": "Stock de pièces détachées, seuils d'alerte et mouvements",
        "Temps d'arrêt": "Journal des arrêts machines par département",
        "Interventions": "Historique des interventions et coûts pièces / main d'œuvre",
        "Énergie": "Suivi par département, administration et services",
        "Rapports": "Générer un rapport complet (HTML / PDF)",
        "Import / Export": "Alimenter AMI avec vos données, ou exporter une sauvegarde",
        "Paramètres": "Heures de travail de l'usine par département",
        "Alertes": "Alertes e-mail / SMS en cas de panne",
        "Utilisateurs": "Gestion des comptes et des rôles",
    }
    return sections, subtitles


# ---------------------------------------------------------------------------
# SECTION : Rapports
# ---------------------------------------------------------------------------
def view_report(db):
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; margin-bottom:10px">'
        + T("Générez un rapport complet (indicateurs, graphiques, synthèse par département) au format")
        + f" <b>{T('HTML autonome')}</b> ({T('interactif, imprimable en PDF depuis le navigateur')}) "
        + "/ <b>PDF</b>.</div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
    with c1:
        periode = "mois" if st.selectbox(T("Période"), ["Mensuelle", "Annuelle"], format_func=T,
                                         key="rep_periode") == "Mensuelle" else "annee"
    with c2:
        mois = MOIS.index(st.selectbox(T("Mois"), MOIS, index=min(7, 11),
                                       format_func=_month_fmt, key="rep_mois")) \
            if periode == "mois" else 0
    with c3:
        annee = st.selectbox(T("Année"), list(range(2020, 2027))[::-1], key="rep_annee")
    with c4:
        dept = dept_selectbox("Département", "rep_dept")

    label = (f"{MOIS[mois]}_{annee}" if periode == "mois" else str(annee))
    if st.button(T("⚙ Générer le rapport"), type="primary"):
        with st.spinner(T("Génération du rapport en cours…")):
            st.session_state.rep_html = report.build_html_report(db, periode, annee, mois, dept)
            try:
                st.session_state.rep_pdf = report.build_pdf_report(db, periode, annee, mois, dept)
            except Exception as exc:  # noqa: BLE001
                st.session_state.rep_pdf = None
                st.session_state.rep_pdf_err = str(exc)
            st.session_state.rep_label = label

    if st.session_state.get("rep_html"):
        lab = st.session_state.get("rep_label", "rapport")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(T("⬇ Télécharger le rapport HTML"), st.session_state.rep_html,
                               file_name=f"AMI_rapport_{lab}.html", mime="text/html", width="stretch")
        with d2:
            if st.session_state.get("rep_pdf"):
                st.download_button(T("⬇ Télécharger le rapport PDF"), st.session_state.rep_pdf,
                                   file_name=f"AMI_rapport_{lab}.pdf", mime="application/pdf",
                                   width="stretch")
            else:
                st.button(T("PDF indisponible"), disabled=True, width="stretch")
                if st.session_state.get("rep_pdf_err"):
                    st.caption(f"PDF : {st.session_state.rep_pdf_err}")
        section_title("Aperçu")
        components.html(st.session_state.rep_html.decode("utf-8"), height=680, scrolling=True)


def render_splash():
    dots = "".join(
        f'<span style="background:{d["couleur"]}; animation-delay:{i*0.12:.2f}s"></span>'
        for i, d in enumerate(DEPARTEMENTS))
    st.markdown(f"""
    <style>
      section[data-testid="stSidebar"], header[data-testid="stHeader"] {{ display:none !important; }}
      .block-container {{ padding-top: 0 !important; }}
      .admi-splash {{ min-height: 74vh; display:flex; flex-direction:column;
        align-items:center; justify-content:center; text-align:center; gap:6px; }}
      .admi-splash .logo {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:74px;
        letter-spacing:.06em; color:{THEME['text']}; display:flex; align-items:center; gap:16px; }}
      .admi-splash .logo .sq {{ width:26px; height:26px; border-radius:6px; background:{THEME['accent']};
        box-shadow:0 0 26px {THEME['accent']}; animation:sqpulse 1.6s ease-in-out infinite; }}
      .admi-splash .sub {{ color:{THEME['muted']}; font-size:15px; letter-spacing:.04em; margin-top:-2px; }}
      .admi-splash .ring {{ width:64px; height:64px; border-radius:50%; margin:26px 0 8px;
        background:conic-gradient(from 0deg, {THEME['accent']}, {THEME['accent2']}, transparent 75%);
        -webkit-mask:radial-gradient(farthest-side, transparent calc(100% - 6px), #000 0);
                mask:radial-gradient(farthest-side, transparent calc(100% - 6px), #000 0);
        animation:spin .9s linear infinite; }}
      .admi-splash .dots {{ display:flex; gap:9px; margin-top:6px; }}
      .admi-splash .dots span {{ width:11px; height:11px; border-radius:50%;
        animation:dotpulse 1.1s ease-in-out infinite; }}
      .admi-splash .load {{ color:{THEME['muted2']}; font-size:12.5px; letter-spacing:.14em;
        text-transform:uppercase; margin-top:16px; position:relative; overflow:hidden; }}
      .admi-splash .load::after {{ content:""; position:absolute; inset:0;
        background:linear-gradient(90deg, transparent, {THEME['accent']}55, transparent);
        transform:translateX(-100%); animation:shimmer 1.8s ease-in-out infinite; }}
      @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
      @keyframes sqpulse {{ 0%,100% {{ opacity:1; transform:scale(1); }} 50% {{ opacity:.55; transform:scale(.86); }} }}
      @keyframes dotpulse {{ 0%,100% {{ opacity:.25; transform:scale(.8); }} 50% {{ opacity:1; transform:scale(1.15); }} }}
      @keyframes shimmer {{ to {{ transform:translateX(100%); }} }}
    </style>
    <div class="admi-splash">
      <div class="logo"><span class="sq"></span>AMI</div>
      <div class="sub">{T("Analyse de Maintenance Industrielle")}</div>
      <div class="ring"></div>
      <div class="dots">{dots}</div>
      <div class="load">Chargement du tableau de bord</div>
    </div>
    """, unsafe_allow_html=True)
    c = st.columns([2, 1, 2])[1]
    if c.button("Entrer", type="primary", width="stretch"):
        get_db()  # précharge/génère les données pendant que l'utilisateur « entre »
        st.session_state.entered = True
        st.rerun()


# ---------------------------------------------------------------------------
# DIALOGUES DE SAISIE (machines, arrêts, interventions, énergie)
# ---------------------------------------------------------------------------
def _dialog_buttons(has_edit):
    b = st.columns(3)
    return (b[0].button(T("Enregistrer"), type="primary", width="stretch"),
            (b[1].button(T("Supprimer"), width="stretch") if has_edit else False),
            b[2].button(T("Annuler"), width="stretch"))


@st.dialog("Machine")
def machine_dialog(db, target):
    mode, val = target
    m = next((x for x in db.machines if x["id"] == val), None) if mode == "edit" else None
    nom = st.text_input(T("Nom de la machine"), value=(m["nom"] if m else ""),
                        placeholder="Ex : Presse à injection AM-3")
    c1, c2 = st.columns(2)
    with c1:
        deptid = _dept_picker("Département", (m["departementId"] if m else "am"), key="mach_dlg_dept")
    with c2:
        kw = st.number_input(T("Puissance (kW)"), 0.0, 100000.0,
                             float(m["puissanceKW"]) if m else 0.0, 0.5)
    c3, c4 = st.columns(2)
    with c3:
        mes = st.date_input(T("Mise en service"), format="DD/MM/YYYY",
                            value=date.fromisoformat(m["dateMES"]) if (m and m.get("dateMES")) else date.today())
    with c4:
        statut = st.selectbox(T("Statut"), STATUTS_MACHINE, format_func=TT,
                              index=STATUTS_MACHINE.index(m["statut"]) if (m and m["statut"] in STATUTS_MACHINE) else 0)
    save, delete, cancel = _dialog_buttons(m is not None)
    if save:
        if not nom.strip():
            st.warning(T("Le nom de la machine est requis."))
        else:
            data = {"nom": nom.strip(), "departementId": deptid, "puissanceKW": kw,
                    "dateMES": mes.isoformat(), "statut": statut}
            rec = {**m, **data} if m else {"id": uid(), **data}
            upsert_record(db, "machines", rec)
            if statut == "En panne" and (m is None or m.get("statut") != "En panne"):
                _maybe_alert(f"AMI — {i18n.type_label('En panne')} : {nom.strip()}",
                             f"{nom.strip()} · {i18n.dept_label(deptid, dep(deptid)['nom'])}")
            _close_dialog("mach"); st.rerun()
    if delete and m:
        delete_record(db, "machines", m["id"])
        _close_dialog("mach"); st.rerun()
    if cancel:
        _close_dialog("mach"); st.rerun()


@st.dialog("Pièce de rechange")
def piece_dialog(db, target):
    mode, val = target
    p = next((x for x in db.pieces if x["id"] == val), None) if mode == "edit" else None
    designation = st.text_input(T("Désignation"), value=(p["designation"] if p else ""),
                                placeholder="Ex : Courroie trapézoïdale A32")
    c1, c2 = st.columns(2)
    with c1:
        reference = st.text_input(T("Référence (optionnel)"), value=(p.get("reference", "") if p else ""),
                                  placeholder="Ex : COU-A32")
    with c2:
        ids = ["", *[d["id"] for d in DEPARTEMENTS]]
        courant = (p.get("departementId") or "") if p else ""
        deptid = st.selectbox(T("Département associé"), ids,
                              index=ids.index(courant) if courant in ids else 0,
                              format_func=lambda i: T("— Non spécifié —") if not i else TD(i, dep(i)["nom"]),
                              key="piece_dlg_dept")
    c3, c4, c5 = st.columns(3)
    with c3:
        quantite = st.number_input(T("Quantité en stock"), 0.0, 1e9,
                                   float(p["quantite"]) if p else 0.0, 1.0)
    with c4:
        unite = st.text_input(T("Unité"), value=(p.get("unite", "unité") if p else "unité"),
                              placeholder="unité, m, L…")
    with c5:
        seuil = st.number_input(T("Seuil d'alerte"), 0.0, 1e9,
                                float(p["seuilAlerte"]) if p else 1.0, 1.0)
    c6, c7 = st.columns(2)
    with c6:
        cout = st.number_input(T("Coût unitaire (FCFA)"), 0.0, 1e12,
                               float(p["coutUnitaire"]) if p else 0.0, 100.0)
    with c7:
        emplacement = st.text_input(T("Emplacement"), value=(p.get("emplacement", "") if p else ""),
                                    placeholder="Magasin A - Rayon 2")
    fournisseur = st.text_input(T("Fournisseur (optionnel)"), value=(p.get("fournisseur", "") if p else ""))

    save, delete, cancel = _dialog_buttons(p is not None)
    if save:
        if not designation.strip():
            st.warning(T("La désignation est requise."))
        else:
            data = {"designation": designation.strip(), "reference": reference.strip(),
                    "departementId": deptid or None, "quantite": quantite,
                    "unite": unite.strip() or "unité", "seuilAlerte": seuil,
                    "coutUnitaire": cout, "emplacement": emplacement.strip(),
                    "fournisseur": fournisseur.strip()}
            rec = {**p, **data} if p else {"id": uid(), **data}
            upsert_record(db, "pieces", rec)
            _close_dialog("piece"); st.rerun()
    if delete and p:
        # L'historique des mouvements est conservé, comme dans l'application d'origine.
        delete_record(db, "pieces", p["id"])
        _close_dialog("piece"); st.rerun()
    if cancel:
        _close_dialog("piece"); st.rerun()


@st.dialog("Mouvement de stock")
def mouvement_dialog(db, target):
    pieces = sorted(db.pieces, key=lambda p: p["designation"])
    if not pieces:
        st.info(T("Ajoutez d'abord une pièce au catalogue."))
        if st.button(T("Fermer")):
            st.session_state["piece_mvt_target"] = None; st.rerun()
        return

    ids = [p["id"] for p in pieces]
    par_id = {p["id"]: p for p in pieces}

    def _fmt(pid):
        p = par_id[pid]
        return (f'{p["designation"]} — {T("stock actuel")} : '
                f'{fmt_num(p.get("quantite", 0))} {p.get("unite", "")}'.strip())

    pid = st.selectbox(T("Pièce"), ids, format_func=_fmt, key="mvt_piece")
    c1, c2 = st.columns(2)
    with c1:
        type_mvt = st.selectbox(T("Type de mouvement"), stock.TYPES_MOUVEMENT, format_func=TT,
                                key="mvt_type")
    with c2:
        jour = st.date_input(T("Date"), value=date.today(), format="DD/MM/YYYY", key="mvt_date")
    aide = (T("Pour un ajustement, indiquez la nouvelle quantité totale.")
            if type_mvt == "Ajustement" else T("Quantité entrée ou sortie du magasin."))
    qte = st.number_input(T("Quantité"), 0.0, 1e9, 1.0, 1.0, help=aide)
    st.caption(aide)
    motif = st.text_input(T("Motif"), placeholder="Ex : Réception livraison, sortie pour l'intervention PT-1")

    b = st.columns(2)
    if b[0].button(T("Enregistrer"), type="primary", width="stretch"):
        stock.apply_mouvement(db, pid, type_mvt, qte, jour.isoformat(), motif.strip())
        upsert_record(db, "pieces", par_id[pid])
        upsert_record(db, "mouvements", db.mouvements[-1])
        st.session_state["piece_mvt_target"] = None
        st.rerun()
    if b[1].button(T("Annuler"), width="stretch"):
        st.session_state["piece_mvt_target"] = None; st.rerun()


@st.dialog("Arrêt de maintenance")
def arret_dialog(db, target):
    mode, val = target
    a = next((x for x in db.arrets if x["id"] == val), None) if mode == "edit" else None
    names, ids = _machine_opts(db)
    if not names:
        st.warning(T("Ajoutez d'abord au moins une machine (onglet Machines)."))
        if st.button(T("Fermer")):
            _close_dialog("arret"); st.rerun()
        return
    midx = ids.index(a["machineId"]) if (a and a["machineId"] in ids) else 0
    machine_id = ids[names.index(st.selectbox(T("Machine"), names, index=midx))]
    typ = st.selectbox(T("Type d'arrêt"), TYPES_ARRET, format_func=TT,
                       index=TYPES_ARRET.index(a["type"]) if (a and a["type"] in TYPES_ARRET) else 0)
    cause = st.text_input(T("Cause"), value=(a.get("cause", "") if a else ""), placeholder="Ex : Rupture courroie")
    dd0 = datetime.fromisoformat(a["dateDebut"]) if a else datetime.now().replace(second=0, microsecond=0)
    df0 = datetime.fromisoformat(a["dateFin"]) if a else dd0
    c1, c2 = st.columns(2)
    d_deb = c1.date_input(T("Date de début"), value=dd0.date(), format="DD/MM/YYYY")
    t_deb = c2.time_input(T("Heure de début"), value=dd0.time())
    c3, c4 = st.columns(2)
    d_fin = c3.date_input(T("Date de fin"), value=df0.date(), format="DD/MM/YYYY")
    t_fin = c4.time_input(T("Heure de fin"), value=df0.time())
    desc = st.text_area(T("Description"), value=(a.get("description", "") if a else ""))
    save, delete, cancel = _dialog_buttons(a is not None)
    if save:
        debut = datetime.combine(d_deb, t_deb)
        fin = datetime.combine(d_fin, t_fin)
        if fin < debut:
            st.warning(T("La date de fin doit être après le début."))
        else:
            data = {"machineId": machine_id, "departementId": db.machine_dept(machine_id), "type": typ,
                    "cause": cause.strip(), "dateDebut": debut.strftime("%Y-%m-%dT%H:%M"),
                    "dateFin": fin.strftime("%Y-%m-%dT%H:%M"), "description": desc.strip()}
            rec = {**a, **data} if a else {"id": uid(), **data}
            upsert_record(db, "arrets", rec)
            if a is None and typ == "Panne":
                mn = db.machine_name(machine_id)
                _maybe_alert(f"AMI — {i18n.t('Panne')} : {mn}",
                             f"{mn} · {cause.strip() or '—'} · {debut.strftime('%d/%m/%Y %H:%M')}")
            _close_dialog("arret"); st.rerun()
    if delete and a:
        delete_record(db, "arrets", a["id"])
        _close_dialog("arret"); st.rerun()
    if cancel:
        _close_dialog("arret"); st.rerun()


@st.dialog("Rapport d'intervention", width="large")
def interv_dialog(db, target):
    mode, val = target
    it = next((x for x in db.interventions if x["id"] == val), None) if mode == "edit" else None
    names, ids = _machine_opts(db)
    if not names:
        st.warning(T("Ajoutez d'abord au moins une machine (onglet Machines)."))
        if st.button(T("Fermer")):
            _close_dialog("interv"); st.rerun()
        return
    c1, c2 = st.columns(2)
    idate = c1.date_input(T("Date"), format="DD/MM/YYYY",
                          value=date.fromisoformat(it["date"]) if it else date.today())
    midx = ids.index(it["machineId"]) if (it and it["machineId"] in ids) else 0
    machine_id = ids[names.index(c2.selectbox(T("Machine"), names, index=midx))]
    c3, c4 = st.columns(2)
    typ = c3.selectbox(T("Type d'intervention"), TYPES_INTERV, format_func=TT,
                       index=TYPES_INTERV.index(it["type"]) if (it and it["type"] in TYPES_INTERV) else 0)
    tech = c4.text_input(T("Technicien(s)"), value=(it.get("technicien", "") if it else ""))
    c5, c6 = st.columns(2)
    duree = c5.number_input(T("Durée (h)"), 0.0, 1000.0, float(it["duree"]) if it else 0.0, 0.5)
    cout_mo = c6.number_input(T("Coût main d'œuvre (FCFA)"), 0.0, 1e9, float(it["coutMainOeuvre"]) if it else 0.0, 1000.0)
    desc = st.text_area(T("Description des travaux"), value=(it.get("description", "") if it else ""))

    # --- Pièces changées / réparées : lignes avec boutons + / − ---
    rid = val or "new"
    if st.session_state.get("interv_rows_for") != rid:
        st.session_state["interv_rows_for"] = rid
        base = it["pieces"] if (it and it.get("pieces")) else []
        st.session_state["interv_rows"] = ([dict(p, _k=uid()) for p in base]
                                           or [{"designation": "", "qte": 1, "cout": 0, "_k": uid()}])
    rows = st.session_state["interv_rows"]

    st.markdown("**Pièces changées / réparées**")
    hc = st.columns([4, 1.3, 1.8, 0.8])
    hc[0].caption("Désignation"); hc[1].caption("Qté"); hc[2].caption("Coût unit."); hc[3].caption("")
    for row in rows:
        c = st.columns([4, 1.3, 1.8, 0.8])
        row["designation"] = c[0].text_input("d", value=row.get("designation", ""),
                                             key=f"pd_{row['_k']}", label_visibility="collapsed",
                                             placeholder="Désignation de la pièce")
        row["qte"] = c[1].number_input("q", min_value=1, value=int(row.get("qte") or 1),
                                       key=f"pq_{row['_k']}", label_visibility="collapsed")
        row["cout"] = c[2].number_input("c", min_value=0, value=int(row.get("cout") or 0), step=500,
                                        key=f"pc_{row['_k']}", label_visibility="collapsed")
        if c[3].button("−", key=f"prm_{row['_k']}", help="Supprimer cette pièce"):
            st.session_state["interv_rows"] = [r for r in rows if r["_k"] != row["_k"]]
            st.rerun()
    if st.button(T("＋ Ajouter une pièce"), key="interv_addpiece"):
        rows.append({"designation": "", "qte": 1, "cout": 0, "_k": uid()})
        st.rerun()

    save, delete, cancel = _dialog_buttons(it is not None)
    if save:
        pieces = [{"designation": str(r["designation"]).strip(),
                   "qte": float(r["qte"] or 1), "cout": float(r["cout"] or 0)}
                  for r in st.session_state["interv_rows"] if str(r["designation"]).strip()]
        data = {"machineId": machine_id, "departementId": db.machine_dept(machine_id),
                "date": idate.isoformat(), "type": typ, "technicien": tech.strip(),
                "duree": duree, "coutMainOeuvre": cout_mo, "description": desc.strip(), "pieces": pieces}
        rec = {**it, **data} if it else {"id": uid(), **data}
        upsert_record(db, "interventions", rec)
        _close_dialog("interv"); st.rerun()
    if delete and it:
        delete_record(db, "interventions", it["id"])
        _close_dialog("interv"); st.rerun()
    if cancel:
        _close_dialog("interv"); st.rerun()


@st.dialog("Consommation énergétique")
def energie_dialog(db, target):
    mode, val = target
    e = next((x for x in db.energie if x["id"] == val), None) if mode == "edit" else None
    dept = _dept_picker("Département / Service", (e["departementId"] if e else "am"), key="energie_dlg_dept")
    c1, c2 = st.columns(2)
    mois = c1.selectbox("Mois", MOIS, index=(e["mois"] if e else date.today().month - 1))
    annee = c2.number_input("Année", 2000, 2100, int(e["annee"]) if e else date.today().year, 1)
    c3, c4 = st.columns(2)
    kwh = c3.number_input("Consommation (kWh)", 0.0, 1e9, float(e["kwh"]) if e else 0.0, 100.0)
    montant = c4.number_input("Montant facturé (FCFA)", 0.0, 1e12, float(e["montant"]) if e else 0.0, 1000.0)
    save, delete, cancel = _dialog_buttons(e is not None)
    if save:
        data = {"departementId": dept, "mois": MOIS.index(mois), "annee": int(annee),
                "kwh": kwh, "montant": montant}
        rec = {**e, **data} if e else {"id": uid(), **data}
        upsert_record(db, "energie", rec)
        _close_dialog("energie"); st.rerun()
    if delete and e:
        delete_record(db, "energie", e["id"])
        _close_dialog("energie"); st.rerun()
    if cancel:
        _close_dialog("energie"); st.rerun()


# ---------------------------------------------------------------------------
# LOGO AMI — SVG vectoriel animé (engrenage + jauge radar + ECG + signal)
# ---------------------------------------------------------------------------
# Engrenage (cercle) dans le jaune de l'application ; éléments techniques en cyan.
_LOGO_NAVY = "#F2A93B"      # jaune/orangé de l'app (l'engrenage)
_LOGO_NAVY_D = "#8A6423"
_LOGO_CYAN = "#22D3EE"
_LOGO_CYAN2 = "#38BDF8"
_LOGO_GOLD = "#F5C36B"
_LOGO_GRAY = "#7C8AA0"


def _arc_path(r, a0, a1, cx=60, cy=60):
    p0 = (cx + r * math.cos(math.radians(a0)), cy - r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1)))
    return f"M {p0[0]:.1f} {p0[1]:.1f} A {r} {r} 0 0 0 {p1[0]:.1f} {p1[1]:.1f}"


def logo_svg(size=120, animated=True):
    teeth = "".join(f'<rect x="56.7" y="4.5" width="6.6" height="13" rx="1.6" '
                    f'transform="rotate({k*30} 60 60)"/>' for k in range(12))
    ecg_pts = [(22, 60), (41, 60), (46, 60), (49, 55), (52, 60), (55, 41), (60, 81),
               (64, 49), (67, 60), (73, 60), (98, 60)]
    ecg = " ".join(f"{x},{y}" for x, y in ecg_pts)
    gray = _arc_path(33, -70, -18)
    rx, ry = 60 + 32 * math.cos(math.radians(42)), 60 - 32 * math.sin(math.radians(42))
    a = (lambda css: css) if animated else (lambda css: "")
    return f'''<svg viewBox="0 0 120 120" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AMI">
      <defs><filter id="glow"><feGaussianBlur stdDeviation="1.1" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <style>
        @keyframes spin{{to{{transform:rotate(360deg)}}}}
        @keyframes draw{{0%{{stroke-dashoffset:280}}55%{{stroke-dashoffset:0}}100%{{stroke-dashoffset:-280}}}}
        @keyframes sig{{0%,100%{{opacity:.18}}50%{{opacity:1}}}}
        @keyframes hub{{0%,100%{{opacity:1}}50%{{opacity:.55}}}}
        .gear{{transform-origin:60px 60px;{a("animation:spin 26s linear infinite;")}}}
        .sweep{{transform-origin:60px 60px;{a("animation:spin 4.6s linear infinite;")}}}
        .ecg{{stroke-dasharray:280;{a("animation:draw 2.8s linear infinite;")}}}
        .s1{{{a("animation:sig 1.7s ease-in-out infinite;")}}}
        .s2{{{a("animation:sig 1.7s ease-in-out .22s infinite;")}}}
        .s3{{{a("animation:sig 1.7s ease-in-out .44s infinite;")}}}
        .hub{{{a("animation:hub 1.7s ease-in-out infinite;")}}}
      </style>
      <g class="gear" fill="{_LOGO_NAVY}"><circle cx="60" cy="60" r="43.5" fill="none"
         stroke="{_LOGO_NAVY}" stroke-width="12"/>{teeth}</g>
      <circle cx="60" cy="60" r="37" fill="#0A1220"/>
      <circle cx="60" cy="60" r="32" fill="none" stroke="{_LOGO_GOLD}" stroke-width="2.4"
              stroke-dasharray="150 62" transform="rotate(-96 60 60)"/>
      <path d="{gray}" fill="none" stroke="{_LOGO_GRAY}" stroke-width="2.4" stroke-linecap="round"/>
      <g class="sweep"><line x1="60" y1="60" x2="{rx:.1f}" y2="{ry:.1f}"
         stroke="{_LOGO_CYAN}" stroke-width="2" stroke-linecap="round" filter="url(#glow)"/></g>
      <g fill="none" stroke="{_LOGO_CYAN2}" stroke-width="2.6" stroke-linecap="round" filter="url(#glow)">
        <path class="s1" d="{_arc_path(13, 18, 66)}"/>
        <path class="s2" d="{_arc_path(20, 18, 66)}"/>
        <path class="s3" d="{_arc_path(27, 18, 66)}"/></g>
      <polyline class="ecg" points="{ecg}" fill="none" stroke="{_LOGO_CYAN}" stroke-width="2.7"
                stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>
      <circle class="hub" cx="60" cy="60" r="5.6" fill="{_LOGO_NAVY}" stroke="{_LOGO_CYAN}" stroke-width="1.4"/>
      <circle cx="60" cy="60" r="2.4" fill="{_LOGO_CYAN}"/>
    </svg>'''


def logo_wordmark(size=46):
    """Texte « AMI » façon logo : A avec sommet cyan, MI clairs."""
    return (f'<div style="font-family:\'Oswald\',sans-serif; font-weight:700; font-size:{size}px; '
            f'letter-spacing:.14em; display:flex; align-items:center; line-height:1;">'
            f'<span style="color:{_LOGO_CYAN}">A</span>'
            f'<span style="color:{THEME["text"]}">MI</span></div>')


def logo_block(label, mark=134):
    return (f'<div style="display:flex; flex-direction:column; align-items:center; gap:10px;">'
            f'{logo_svg(mark)}{logo_wordmark(44)}'
            f'<div style="color:{THEME["muted2"]}; font-size:11px; letter-spacing:.18em; '
            f'text-transform:uppercase; margin-top:2px;">{T(label)}</div></div>')


def gears_html(label="Chargement", small=False):
    """Animation d'engrenages industriels ADMI (CSS pur)."""
    sz = 0.8 if small else 1.0
    dots = "".join(f'<span style="background:{d["couleur"]}; animation-delay:{i*0.1:.2f}s"></span>'
                   for i, d in enumerate(DEPARTEMENTS))
    return f"""
    <style>
      .admi-mach {{ display:flex; flex-direction:column; align-items:center; gap:14px; }}
      .admi-mach .cluster {{ position:relative; width:{int(150*sz)}px; height:{int(110*sz)}px; }}
      .admi-mach .gear {{ position:absolute; border-radius:50%; --gc:{THEME['accent']};
        background:repeating-conic-gradient(var(--gc) 0deg 15deg, transparent 15deg 30deg);
        -webkit-mask:radial-gradient(circle, transparent 30%, #000 32%, #000 47%, transparent 49%);
                mask:radial-gradient(circle, transparent 30%, #000 32%, #000 47%, transparent 49%); }}
      .admi-mach .gear::after {{ content:""; position:absolute; inset:38%; border-radius:50%;
        background:var(--gc); opacity:.9; }}
      .admi-mach .g1 {{ width:{int(84*sz)}px; height:{int(84*sz)}px; left:{int(8*sz)}px; top:{int(4*sz)}px;
        animation:gspin 3.4s linear infinite; }}
      .admi-mach .g2 {{ width:{int(60*sz)}px; height:{int(60*sz)}px; left:{int(80*sz)}px; top:{int(30*sz)}px;
        --gc:{THEME['accent2']}; animation:gspin 2.3s linear infinite reverse; }}
      .admi-mach .g3 {{ width:{int(40*sz)}px; height:{int(40*sz)}px; left:{int(58*sz)}px; top:{int(-6*sz)}px;
        --gc:{THEME['success']}; animation:gspin 1.7s linear infinite; }}
      .admi-mach .word {{ font-family:'Oswald',sans-serif; font-weight:700; font-size:{int(30*sz)}px;
        letter-spacing:.22em; color:{THEME['text']}; display:flex; gap:2px; }}
      .admi-mach .word span {{ display:inline-block; animation:stamp 1.4s ease-in-out infinite; }}
      .admi-mach .word span:nth-child(2){{animation-delay:.12s}} .admi-mach .word span:nth-child(3){{animation-delay:.24s}}
      .admi-mach .word span:nth-child(4){{animation-delay:.36s}}
      .admi-mach .dots {{ display:flex; gap:7px; }}
      .admi-mach .dots span {{ width:9px; height:9px; border-radius:50%; animation:dotpulse 1.1s ease-in-out infinite; }}
      .admi-mach .lbl {{ color:{THEME['muted2']}; font-size:11px; letter-spacing:.18em; text-transform:uppercase; }}
      @keyframes gspin {{ to {{ transform:rotate(360deg); }} }}
      @keyframes stamp {{ 0%,100% {{ transform:translateY(0); color:{THEME['text']}; }}
        50% {{ transform:translateY(-4px); color:{THEME['accent']}; }} }}
      @keyframes dotpulse {{ 0%,100% {{ opacity:.3; transform:scale(.8);}} 50% {{ opacity:1; transform:scale(1.15);}} }}
    </style>
    <div class="admi-mach">
      <div class="cluster"><div class="gear g1"></div><div class="gear g2"></div><div class="gear g3"></div></div>
      <div class="word"><span>A</span><span>M</span><span>I</span></div>
      <div class="dots">{dots}</div>
      <div class="lbl">{T(label)}</div>
    </div>
    """


def _lang_toggle():
    """Petit sélecteur de langue pour les écrans licence / connexion."""
    langs = list(i18n.LANGS.keys())
    col = st.columns([3, 1])[1]
    with col:
        choice = st.radio("lang", langs, index=langs.index(_lang()),
                          format_func=lambda c: i18n.LANGS[c], horizontal=True,
                          label_visibility="collapsed", key="lang_toggle")
    if choice != _lang():
        st.session_state.lang = choice
        st.rerun()


def render_section_loader():
    st.markdown(
        '<div style="min-height:50vh; display:flex; flex-direction:column; align-items:center; '
        'justify-content:center; gap:10px">' + logo_svg(84)
        + f'<div style="color:{THEME["muted2"]}; font-size:11px; letter-spacing:.18em; '
          f'text-transform:uppercase">{T("Chargement")}</div></div>', unsafe_allow_html=True)


def _hide_chrome_css():
    st.markdown("""<style>
      section[data-testid="stSidebar"], header[data-testid="stHeader"] { display:none !important; }
      .block-container { padding-top: 2vh !important; }
    </style>""", unsafe_allow_html=True)


def render_license_screen():
    _hide_chrome_css()
    _lang_toggle()
    st.markdown(f'<div style="display:flex;justify-content:center;margin-top:2vh">{logo_block("Activation requise")}</div>',
                unsafe_allow_html=True)
    col = st.columns([1, 1.25, 1])[1]
    en = _lang() == "en"
    with col:
        st.markdown("### " + T("Licence d'utilisation"))
        st.caption("Enter your AMI license code to activate the software (provided by your reseller, generated with `licgen`)."
                   if en else
                   "Entrez votre code de licence AMI pour activer le logiciel. "
                   "Un code est fourni par votre revendeur (généré via `licgen`).")
        code = st.text_input(T("Code de licence"), placeholder="AMI-XXXX-XXXX-XXXX-XXXX", key="lic_code")
        name = st.text_input(T("Nom / société (optionnel)"), key="lic_name")
        if st.button(T("Activer la licence"), type="primary", width="stretch"):
            if lic.activate(code, name.strip()):
                st.success("License activated. Welcome." if en else "Licence activée. Bienvenue.")
                st.rerun()
            else:
                st.error("Invalid license code." if en else "Code de licence invalide. Vérifiez la saisie.")


def render_login_screen():
    _hide_chrome_css()
    _lang_toggle()
    st.markdown(f'<div style="display:flex;justify-content:center;margin-top:2vh">{logo_block("Connexion")}</div>',
                unsafe_allow_html=True)
    col = st.columns([1, 1.25, 1])[1]
    en = _lang() == "en"
    with col:
        st.markdown("### " + T("Connexion"))
        user = st.text_input(T("Identifiant"), key="login_user")
        pw = st.text_input(T("Mot de passe"), type="password", key="login_pw")
        if st.button(T("Se connecter"), type="primary", width="stretch"):
            res = auth.verify_login(user, pw)
            if res:
                st.session_state.user = res["username"]
                st.session_state.role = res["role"]
                st.session_state.booted = False
                st.rerun()
            else:
                st.error("Wrong username or password." if en else "Identifiant ou mot de passe incorrect.")
        st.caption("Default account: **admin / admin** (change in production)." if en else
                   "Compte par défaut : **admin / admin** (à modifier en production).")


def main():
    i18n.set_lang(st.session_state.get("lang", "fr"))  # langue courante pour charts/rapports
    # 1) licence  2) connexion  3) démarrage animé  4) application
    # ADMI_SKIP_LICENSE=1 (secret Streamlit Cloud) : déploiement de démo sans licence.
    if not os.environ.get("ADMI_SKIP_LICENSE") and not lic.is_activated():
        render_license_screen()
        return
    if not st.session_state.get("user"):
        render_login_screen()
        return
    if not st.session_state.get("booted"):
        ph = st.empty()
        with ph.container():
            st.markdown('<div style="min-height:70vh; display:flex; align-items:center; '
                        f'justify-content:center">{logo_block("Démarrage du tableau de bord")}</div>',
                        unsafe_allow_html=True)
        time.sleep(1.1)
        st.session_state.booted = True
        ph.empty()

    db = get_db()
    SECTIONS, SUBTITLES = _nav()
    lbl = {"en": "Machines: {m} · stops: {a} · interventions: {i}",
           "fr": "{m} machines · {a} arrêts · {i} interventions"}[_lang()]
    # Navigation demandée par un raccourci interne (bandeau de stock…) : à appliquer
    # avant que le radio ne soit instancié.
    goto = st.session_state.pop("_goto", None)
    if goto in SECTIONS:
        st.session_state["nav_choice"] = goto

    with st.sidebar:
        st.markdown('<div class="admi-brand">' + logo_svg(34) + 'AMI</div>'
                    + f'<div class="admi-sub" style="margin-left:43px">{T("Analyse de Maintenance Industrielle")}</div>',
                    unsafe_allow_html=True)
        st.write("")
        # key="nav_choice" : permet aux raccourcis internes (bandeau de stock…)
        # de pointer une autre section avant le rerun.
        choice = st.radio("Navigation", list(SECTIONS.keys()), format_func=T,
                          label_visibility="collapsed", key="nav_choice")
        st.markdown(f'<div style="margin-top:20px; font-size:10.5px; color:{THEME["muted2"]}; '
                    f'line-height:1.5">' + lbl.format(m=len(db.machines), a=len(db.arrets),
                                                       i=len(db.interventions)) + '</div>',
                    unsafe_allow_html=True)
        st.write("")
        langs = list(i18n.LANGS.keys())
        new_lang = st.radio(T("Langue"), langs, index=langs.index(_lang()),
                            format_func=lambda c: i18n.LANGS[c], horizontal=True)
        if new_lang != _lang():
            st.session_state.lang = new_lang
            st.rerun()
        _conn = {"fr": "Connecté", "en": "Signed in"}[_lang()]
        st.caption(f"{_conn} : **{st.session_state.get('user', '—')}** · {T('Rôle')} : *{_role()}*")
        if st.button(T("Se déconnecter"), width="stretch"):
            st.session_state.user = None
            st.session_state.role = None
            st.rerun()

    # Bannière de mise à jour (best-effort, vérifiée une fois par session)
    if "update_info" not in st.session_state:
        st.session_state.update_info = update.check()
    if st.session_state.update_info:
        cur, latest, url = st.session_state.update_info
        st.warning(f"🔔 Nouvelle version **{latest}** disponible (actuelle : {cur}). "
                   + (f"[Télécharger]({url})" if url else ""))

    # Transition animée lors d'un changement de section
    if st.session_state.get("_section") != choice:
        st.session_state["_section"] = choice
        loader = st.empty()
        with loader.container():
            render_section_loader()
        time.sleep(0.5)
        loader.empty()

    # En-tête : titre à gauche, horloge live à droite (comme la topbar du HTML).
    # L'horloge tourne dans son iframe, sans rerun : les filtres en cours restent.
    titre, horloge = st.columns([4, 1], vertical_alignment="center")
    with titre:
        st.markdown(f"# {T(choice)}")
        st.markdown(f'<div style="color:{THEME["muted2"]}; font-size:12px; margin-top:-12px; '
                    f'margin-bottom:16px">{T(SUBTITLES[choice])}</div>', unsafe_allow_html=True)
    with horloge:
        st.iframe(live_clock_html(_lang()), height=52)
    st.session_state["_plot_n"] = 0   # clés de graphiques stables par run
    SECTIONS[choice](db)


if __name__ == "__main__":
    main()
