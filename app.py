"""AMI — Analyse des Machines Industrielles (application Streamlit).

Lancement :  streamlit run app.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_calendar import calendar as st_calendar

# NB : les symboles ajoutés récemment (add_departement, live_clock_html) sont
# atteints par leur module et non importés par leur nom. Streamlit Cloud relance
# le script après un `git pull` sans redémarrer le processus : les modules déjà
# chargés restent en mémoire, et un `from ... import <nouveau nom>` ferait
# planter l'application entière au lieu de n'affecter que la fonction concernée.
from admi import (alerts, auth, charts, config, data as admi_data, db as dbmod,
                  i18n, kpis, license as lic, report, stock, theme as admi_theme, update)
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
from admi.logo import CYAN as _LOGO_CYAN, logo_svg
from admi.theme import CSS, register_template

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


@st.cache_data
def _build_sha() -> str:
    """SHA court du commit déployé, pour un repère visuel dans la sidebar."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent
    try:
        out = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                                      stderr=subprocess.DEVNULL, timeout=2)
        return out.decode().strip()
    except Exception:
        return ""


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
    return _role() in ("admin", "root")


def is_root():
    return _role() == "root"


def _maybe_alert(subject, message, details=None):
    """Envoie une alerte (email/SMS) si les alertes auto sont activées. Best-effort."""
    try:
        cfg = get_alert_config()
        if cfg.get("enabled"):
            alerts.notify(cfg, subject, message, details)
    except Exception:
        pass


def check_machine_usage_alerts(db):
    """Alerte quand une machine approche/atteint son seuil d'heures d'utilisation.

    Best-effort : un e-mail par franchissement (anti-spam via db.settings), jamais
    de plantage. Appelée une fois par session (voir main()).
    """
    try:
        cfg = get_alert_config()
        if not cfg.get("enabled"):
            return
        messages, dirty = alerts.build_usage_messages(db, cfg)
        for msg in messages:
            alerts.notify(cfg, msg["subject"], msg["message"], msg["details"])
        if dirty:
            save_settings(db)
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
        # Filtrer sur un département absent de la liste n'a pas de sens : on le
        # crée ici plutôt que d'envoyer l'utilisateur dans Paramètres.
        if is_admin() and st.button(T("＋ Nouveau département"), key="dash_new_dept",
                                    width="stretch"):
            st.session_state["dept_dialog"] = True
    if st.session_state.get("dept_dialog"):
        dept_dialog(db)

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
def _machine_usage_row(db, m):
    """(heures d'utilisation, badge d'état) d'une machine vis-à-vis de ses seuils."""
    usage = kpis.machine_usage_hours(db, m)
    sm, sa = m.get("seuilMaintenanceH") or 0, m.get("seuilArretH") or 0
    lvl_arret = kpis.usage_alert_level(usage, sa)
    lvl_maint = kpis.usage_alert_level(usage, sm)
    if lvl_arret == "atteint":
        etat = "🔴 " + T("À arrêter")
    elif lvl_maint == "atteint":
        etat = "🟠 " + T("Entretien requis")
    elif "approche" in (lvl_arret, lvl_maint):
        etat = "🟡 " + T("Seuil proche")
    elif sm or sa:
        etat = "🟢 " + T("OK")
    else:
        etat = "—"
    return usage, etat


def view_machines(db):
    _crud_controls(db, "mach", "＋ Nouvelle machine", db.machines,
                   lambda m: f'{m["nom"]} ({dep(m["departementId"])["court"]})')
    total_kw = sum(float(m.get("puissanceKW") or 0) for m in db.machines)
    section_title("Bilan de puissance installée",
                  f'<span style="color:{THEME["accent"]}; font-family:JetBrains Mono">'
                  f'{fmt_num(total_kw)} kW total</span>')
    plot(charts.bar_puissance_by_dept(db))

    section_title("Parc machines")
    rows = []
    for m in db.machines:
        usage, etat = _machine_usage_row(db, m)
        rows.append({T("Machine"): m["nom"], T("Dépt."): dep(m["departementId"])["court"],
                     T("Puissance (kW)"): m.get("puissanceKW", 0),
                     T("Mise en service"): m.get("dateMES", ""),
                     T("Heures d'utilisation"): f"{fmt_num(usage)} h",
                     T("Suivi seuils"): etat,
                     T("Statut"): TT(m.get("statut", ""))})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    section_title("Historique des pannes par machine")
    if db.machines:
        noms = {m["id"]: f'{m["nom"]} ({dep(m["departementId"])["court"]})' for m in db.machines}
        sel = st.selectbox(T("Machine"), list(noms), format_func=lambda i: noms[i], key="hist_mach")
        pannes_only = not st.checkbox(T("Afficher tous les arrêts"), key="hist_all")
        s = kpis.machine_arret_stats(db, sel, pannes_only=pannes_only)
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            kpi_card("Pannes" if pannes_only else "Arrêts", fmt_num(s["nb"]), color=THEME["accent2"])
        with k2:
            kpi_card("Temps d'arrêt (h)", fmt_num(s["tempsArretH"], 1), color=THEME["danger"])
        with k3:
            kpi_card("MTBF (h)", fmt_num(s["mtbf"], 1) if s["mtbf"] is not None else "—",
                     color=THEME["accent"])
        with k4:
            kpi_card("Dernière panne", s["derniere"].replace("T", " ") if s["derniere"] else "—",
                     color=THEME["muted"], value_size=16)
        sel_arrets = sorted(
            [a for a in db.arrets
             if a["machineId"] == sel and (not pannes_only or a.get("type") == "Panne")],
            key=lambda a: a["dateDebut"], reverse=True)
        if sel_arrets:
            hrows = [{T("Début"): a["dateDebut"].replace("T", " "), T("Type"): TT(a.get("type", "")),
                      T("Cause"): a.get("cause", ""),
                      T("Durée (h)"): round(kpis.hours_between(a["dateDebut"], a.get("dateFin", "")), 1),
                      T("Description"): a.get("description", "")} for a in sel_arrets]
            st.dataframe(pd.DataFrame(hrows), width="stretch", hide_index=True)
        else:
            st.caption(T("Aucune panne enregistrée pour cette machine."))

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

    _settings_branding(db)
    _settings_objectifs(db)
    _settings_departements(db)
    _settings_donnees(db)
    _settings_stockage(db)
    _settings_reseau(db)


@st.dialog("Supprimer toutes les données")
def raz_dialog():
    """Effacement total : on fait recopier une phrase, pas cliquer un bouton.

    Un bouton se clique par réflexe ; une phrase se tape volontairement. C'est
    la seule action de l'application qui soit vraiment irréversible.
    """
    st.error(T("Cette action efface définitivement toutes les machines, arrêts, "
               "relevés d'énergie, interventions, actions planifiées, pièces et "
               "mouvements de stock. Elle est irréversible."))
    portee = st.radio(
        T("Que faut-il effacer ?"),
        ["donnees", "tout"], key="raz_portee",
        format_func=lambda p: T("Les données seulement — garder les départements "
                                "et les horaires de travail") if p == "donnees"
        else T("Tout — y compris les départements, les horaires et les réglages"))
    st.markdown(T("Pour confirmer, recopiez ci-dessous :") +
                f' **{admi_data.PHRASE_SUPPRESSION}**')
    phrase = st.text_input(T("Phrase de confirmation"), key="raz_phrase",
                           placeholder=admi_data.PHRASE_SUPPRESSION,
                           label_visibility="collapsed")
    b1, b2 = st.columns(2)
    if b1.button(T("Supprimer définitivement"), key="raz_ok", type="primary"):
        if not admi_data.confirmation_suppression(phrase):
            st.error(T("La phrase ne correspond pas — rien n'a été supprimé."))
        else:
            admi_data.wipe_all(garder_departements=(portee == "donnees"))
            st.session_state["raz_dialog"] = False
            st.session_state["raz_done"] = portee
            st.rerun()
    if b2.button(T("Annuler"), key="raz_no"):
        st.session_state["raz_dialog"] = False
        st.rerun()


def _settings_donnees(db):
    """Zone de danger : tout effacer, ou recharger un jeu de démonstration."""
    if not is_admin():
        return
    st.write("")
    section_title("Données de l'application")
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:12px">'
        + T("Repartir d'une application vide pour une mise en service réelle, ou "
            "recharger un jeu de démonstration pour présenter l'outil.")
        + "</div>", unsafe_allow_html=True)

    fait = st.session_state.pop("raz_done", None)
    if fait:
        st.success(T("Données supprimées — les départements et les horaires sont conservés.")
                   if fait == "donnees" else T("Toutes les données ont été supprimées."))
    if st.session_state.pop("demo_done", False):
        st.success(T("Jeu de démonstration rechargé."))

    c1, c2 = st.columns(2)
    if c1.button(T("🗑 Supprimer toutes les données"), key="raz", width="stretch"):
        st.session_state["raz_dialog"] = True
    if c2.button(T("↺ Charger les données de démonstration"), key="demo", width="stretch"):
        admi_data.load_demo()
        st.session_state["demo_done"] = True
        st.rerun()

    if st.session_state.get("raz_dialog"):
        raz_dialog()


@st.dialog("Restaurer une sauvegarde")
def restore_dialog(db):
    """Restauration : destructive, donc phrase à recopier (comme l'effacement)."""
    st.error(T("La restauration REMPLACE toutes les données actuelles par celles de "
               "la sauvegarde. Cette action est irréversible."))
    st.markdown(T("Pour confirmer, recopiez ci-dessous :")
                + f" **{admi_data.PHRASE_SUPPRESSION}**")
    phrase = st.text_input(T("Phrase de confirmation"), key="restore_phrase",
                           placeholder=admi_data.PHRASE_SUPPRESSION, label_visibility="collapsed")
    b1, b2 = st.columns(2)
    if b1.button(T("Restaurer définitivement"), key="restore_ok", type="primary"):
        if not admi_data.confirmation_suppression(phrase):
            st.error(T("La phrase ne correspond pas — rien n'a été restauré."))
        else:
            try:
                admi_data.restore_backup(db, st.session_state.get("restore_payload"))
                st.session_state.pop("restore_payload", None)
                st.session_state["restore_dialog"] = False
                st.session_state["restore_done"] = True
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(T("Échec de la restauration :") + f" {exc}")
    if b2.button(T("Annuler"), key="restore_cancel"):
        st.session_state["restore_dialog"] = False
        st.rerun()


def _settings_stockage(db):
    """R2 + R3 — dossier de sauvegarde configurable, sauvegarde & restauration."""
    if not is_admin():
        return
    st.write("")
    section_title("Stockage & sauvegarde")
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:10px">'
        + T("La base de données vit dans PostgreSQL / SQLite (DATABASE_URL). Le dossier "
            "ci-dessous reçoit les fichiers de sauvegarde (admi-backup-*.json).")
        + "</div>", unsafe_allow_html=True)

    if st.session_state.pop("restore_done", False):
        st.success(T("Sauvegarde restaurée — les données actuelles ont été remplacées."))

    # R2 — dossier de sauvegarde
    with st.form("backup_dir_form"):
        chemin = st.text_input(T("Dossier de sauvegarde"), value=str(admi_data.get_backup_dir(db)))
        if st.form_submit_button(T("Valider et enregistrer"), type="primary"):
            ok, msg = admi_data.validate_backup_dir(chemin)
            if ok:
                admi_data.set_backup_dir(db, chemin)
                st.success(msg)
            else:
                st.error(msg)

    # R3 — sauvegarder
    c1, c2 = st.columns(2)
    if c1.button(T("💾 Sauvegarder maintenant"), key="bk_now", width="stretch"):
        try:
            p = admi_data.write_backup(db)
            st.success(T("Sauvegarde créée :") + f" {p}")
        except Exception as exc:  # noqa: BLE001
            st.error(T("Échec de la sauvegarde :") + f" {exc}")
    c2.download_button(
        T("⬇ Télécharger une sauvegarde"),
        json.dumps(admi_data.export_backup(db), ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"admi-backup-{datetime.now():%Y%m%d-%H%M%S}.json",
        mime="application/json", width="stretch")

    # R3 — restaurer (depuis le dossier ou un fichier importé)
    backups = admi_data.list_backups(admi_data.get_backup_dir(db))
    st.markdown(f'<div style="color:{THEME["muted"]}; font-size:11.5px; margin-top:8px">'
                + T("Sauvegardes dans le dossier :") + f" {len(backups)}</div>",
                unsafe_allow_html=True)
    options = {p.name: p for p in backups}
    choix = None
    if options:
        nom = st.selectbox(T("Restaurer depuis une sauvegarde du dossier"), list(options), key="bk_pick")
        choix = options.get(nom)
    up = st.file_uploader(T("…ou importer un fichier de sauvegarde"), type=["json"], key="bk_up")
    if st.button(T("♻ Restaurer"), key="bk_restore"):
        payload = None
        try:
            if up is not None:
                payload = json.loads(up.getvalue().decode("utf-8"))
            elif choix is not None:
                payload = admi_data.read_backup(choix)
        except Exception as exc:  # noqa: BLE001
            st.error(T("Fichier illisible :") + f" {exc}")
        if payload is None:
            st.warning(T("Choisissez une sauvegarde du dossier ou importez un fichier."))
        else:
            try:
                admi_data.backup_to_db(payload)   # valide le format avant la confirmation
                st.session_state["restore_payload"] = payload
                st.session_state["restore_dialog"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    if st.session_state.get("restore_dialog"):
        restore_dialog(db)


def _settings_reseau(db):
    """R1 — réseau / serveur : backend de base, concurrence, accès LAN."""
    if not is_admin():
        return
    st.write("")
    section_title("Réseau & serveur")
    backend = dbmod.backend_label()
    try:
        port = st.get_option("server.port") or 8501
    except Exception:  # noqa: BLE001
        port = 8501
    ip = "127.0.0.1"
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:  # noqa: BLE001
        pass

    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.7; margin-bottom:10px">'
        + T("Base de données active :") + f' <b style="color:{THEME["accent"]}">{backend}</b><br>'
        + T("Accès depuis le réseau local :")
        + f' <b style="color:{THEME["accent2"]}">http://{ip}:{port}</b></div>',
        unsafe_allow_html=True)

    if backend == "PostgreSQL":
        st.success(T("Base partagée PostgreSQL — adaptée à plusieurs utilisateurs simultanés."))
    elif backend == "SQLite":
        st.warning(T("Base SQLite (fichier local) : convient à un seul poste ou à quelques "
                     "utilisateurs surtout en lecture. Pour plusieurs personnes qui saisissent "
                     "en même temps, passez à PostgreSQL via la variable DATABASE_URL."))

    st.caption(T("Pour servir l'application à toute l'équipe : lancez run_server.sh sur le serveur "
                 "(ou streamlit run app.py --server.address 0.0.0.0 --server.port 8501 "
                 "--server.headless true). Voir DEPLOIEMENT.md."))


def _save_departements(db):
    """Persiste la liste courante et la garde synchronisée avec config."""
    db.settings["departements"] = [dict(d) for d in DEPARTEMENTS]
    save_settings(db)


_USAGE_LABELS = {"machines": "machine(s)", "arrets": "arrêt(s)", "energie": "relevé(s) d'énergie",
                 "interventions": "intervention(s)", "planning": "action(s) planifiée(s)",
                 "pieces": "pièce(s)"}


def _usage_phrase(detail: dict) -> str:
    """« 3 machines · 1 428 arrêts » — dire où sont les enregistrements qui bloquent."""
    return " · ".join(f'{fmt_num(n)} {T(_USAGE_LABELS[cle])}' for cle, n in detail.items())


@st.dialog("Nouveau département")
def dept_dialog(db):
    """Création rapide depuis le tableau de bord — mêmes règles que Paramètres."""
    nom = st.text_input(T("Nom complet"), placeholder="Ex : Menuiserie Métallique")
    c1, c2 = st.columns(2)
    court = c1.text_input(T("Code court"), max_chars=5, placeholder="MM")
    couleur = c2.color_picker(
        T("Couleur"), value=config.new_dept_color([d["couleur"] for d in DEPARTEMENTS]))
    st.caption(T("Il sera immédiatement disponible dans tous les formulaires et "
                 "prendra cette couleur dans tous les graphiques."))

    b1, b2 = st.columns(2)
    if b1.button(T("Enregistrer le département"), type="primary", key="dept_dlg_ok"):
        ok, resultat = admi_data.add_departement(db, nom, court, couleur)
        if not ok:
            st.error(T(resultat))
        else:
            st.session_state["dept_dialog"] = False
            st.rerun()
    if b2.button(T("Annuler"), key="dept_dlg_no"):
        st.session_state["dept_dialog"] = False
        st.rerun()


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
        # Un nouveau département reçoit une couleur encore libre : deux
        # départements de la même teinte rendraient les graphiques illisibles.
        couleur = c3.color_picker(
            T("Couleur"),
            value=(courant["couleur"] if courant
                   else config.new_dept_color([d["couleur"] for d in DEPARTEMENTS])))
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
            admi_data.add_departement(db, nom, court, couleur)
            st.success(T("Département ajouté."))
            st.rerun()

    if courant:
        detail = db.dept_usage_detail(cible)
        st.write("")
        if detail:
            # Supprimer laisserait ces enregistrements en base sans département
            # reconnu : ils sortiraient de tous les graphiques sans prévenir.
            st.error(
                f'**{T("Suppression impossible")}** — {_usage_phrase(detail)} '
                + T("utilisent encore ce département. Réaffectez-les à un autre "
                    "département avant de le supprimer."))
        elif st.button(T("Supprimer ce département"), key="dept_del"):
            st.session_state["dept_confirm"] = cible
        if not detail and st.session_state.get("dept_confirm") == cible:
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
        # Réinitialiser efface les départements ajoutés : même garde-fou que la
        # suppression, sinon on perdrait leurs enregistrements des graphiques.
        defauts = {d["id"] for d in config.DEPARTEMENTS_DEFAUT}
        bloquants = [d for d in DEPARTEMENTS if d["id"] not in defauts and db.dept_usage(d["id"])]
        if bloquants:
            st.error(f'**{T("Réinitialisation impossible")}** — '
                     + T("ces départements ajoutés sont encore utilisés :") + " "
                     + ", ".join(f'{d["nom"]} ({db.dept_usage(d["id"])})' for d in bloquants)
                     + ". " + T("Réaffectez leurs enregistrements avant de réinitialiser."))
            if st.button(T("Annuler"), key="dept_reset_no"):
                st.session_state["dept_reset_confirm"] = False
                st.rerun()
            return
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


def _fetch_company_logo(domain: str, timeout: float = 5.0):
    """Récupère le logo d'une entreprise via Google Favicon API (gratuit, sans clé).

    Essaie plusieurs tailles (256, 128, 64) : si le favicon du site n'existe qu'en
    petite taille, Google rétrograde silencieusement — on prend ce qu'on peut.
    Retourne (bytes_png, None) si OK, sinon (None, message_erreur).
    """
    import urllib.request
    import urllib.error

    domain = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/", 1)[0].strip()
    if not domain or "." not in domain:
        return None, T("Entrez un domaine valide (ex : acme.com)")

    last_err = None
    for size in (256, 128, 64):
        url = f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"
        req = urllib.request.Request(url, headers={"User-Agent": "AMI/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
            continue
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)[:80]
            continue
        # Google renvoie 1x1 PNG générique quand il n'a rien — on refuse.
        if 300 < len(data) < 2_000_000:
            return data, None
        last_err = T("Aucun logo trouvé pour ce domaine.")
    return None, (last_err or T("Impossible de récupérer le logo."))


def _branding_from_db(db) -> dict:
    """Lit la configuration branding (nom, domaine, logo base64) depuis la DB."""
    br = db.settings.get("branding") or {}
    return {
        "company_name": (br.get("company_name") or "").strip(),
        "domain": (br.get("domain") or "").strip(),
        "logo_png_b64": br.get("logo_png_b64") or "",
    }


def _branding_logo_bytes(br: dict) -> bytes | None:
    import base64
    b64 = (br or {}).get("logo_png_b64") or ""
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except Exception:
        return None


def _settings_branding(db):
    """Permet au client d'afficher son nom et son logo partout dans l'app."""
    if not is_admin():
        return
    import base64

    st.write("")
    section_title(T("Marque de l'entreprise"))
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; line-height:1.6; margin-bottom:12px">'
        + T("Personnalise l'app avec le nom et le logo de l'entreprise. Le logo est récupéré "
            "automatiquement si tu renseignes le site web (ex : acme.com). Il s'affiche sur l'écran "
            "de connexion, dans la barre latérale et en en-tête des rapports PDF.")
        + "</div>", unsafe_allow_html=True)

    import html as _html
    br = _branding_from_db(db)
    # Mémorise la saisie en cours pour la preview live (indépendante du formulaire).
    draft_name = st.session_state.get("brand_draft_name", br["company_name"])
    draft_domain = st.session_state.get("brand_draft_domain", br["domain"])
    draft_logo_bytes = st.session_state.get("brand_draft_logo") or _branding_logo_bytes(br)

    left, right = st.columns([1.1, 1], gap="large")

    # --- Formulaire ---------------------------------------------------------
    with left:
        name = st.text_input(T("Nom de l'entreprise"), value=draft_name,
                              placeholder=T("Ex : ACME Industries"), key="brand_name_input")
        domain = st.text_input(T("Site web (pour récupérer le logo)"),
                                value=draft_domain, placeholder="acme.com",
                                key="brand_domain_input",
                                help=T("Juste le domaine, sans http:// ni www. Laisse vide pour sans logo."))
        st.session_state["brand_draft_name"] = name
        st.session_state["brand_draft_domain"] = domain

        bc1, bc2 = st.columns(2)
        if bc1.button(T("🔎 Récupérer le logo"), width="stretch", key="brand_fetch"):
            if not domain:
                st.warning(T("Renseigne d'abord le site web."))
            else:
                with st.spinner(T("Recherche du logo…")):
                    data, err = _fetch_company_logo(domain)
                if err:
                    st.error(err)
                else:
                    st.session_state["brand_draft_logo"] = data
                    st.session_state["brand_logo_cleared"] = False
                    st.success(T("Logo récupéré — vérifie la preview à droite."))
                    st.rerun()

        up = st.file_uploader(T("…ou importer un logo (PNG, JPG, SVG — max 2 Mo)"),
                              type=["png", "jpg", "jpeg", "svg"], key="brand_upload")
        if up is not None and st.session_state.get("brand_upload_last") != up.name:
            data = up.getvalue()
            if len(data) > 2_000_000:
                st.error(T("Image trop grosse (>2 Mo)."))
            else:
                st.session_state["brand_draft_logo"] = data
                st.session_state["brand_logo_cleared"] = False
                st.session_state["brand_upload_last"] = up.name
                st.rerun()

        if bc2.button(T("🗑 Retirer le logo"), width="stretch", key="brand_clear_logo"):
            # Suppression IMMÉDIATE du logo + capture des champs courants pour
            # ne pas perdre le nom/domaine en cours de saisie.
            br_now = db.settings.get("branding") or {}
            # Priorité au champ visible à l'écran > valeur DB > chaîne vide.
            new_name = (name.strip() if name else "")[:80] or (br_now.get("company_name") or "").strip()[:80]
            new_domain = (domain.strip() if domain else "")[:120] or (br_now.get("domain") or "").strip()[:120]
            db.settings["branding"] = {
                "company_name": new_name,
                "domain": new_domain,
                "logo_png_b64": "",
            }
            save_settings(db)
            # Nettoie TOUS les drafts pour que le prochain rendu lise la BDD à jour.
            for k in ("brand_draft_logo", "brand_draft_name", "brand_draft_domain",
                      "brand_upload_last", "brand_logo_cleared"):
                st.session_state.pop(k, None)
            if new_name:
                st.success(T("Logo supprimé — le nom « {n} » est conservé.").format(n=new_name))
            else:
                st.success(T("Logo supprimé."))
            st.rerun()

        st.write("")
        a1, a2 = st.columns(2)
        if a1.button(T("💾 Enregistrer"), type="primary", width="stretch", key="brand_save"):
            # Limites : évite un payload démesuré qui casserait la mise en page.
            clean_name = name.strip()[:80]
            clean_domain = domain.strip()[:120]
            payload = {"company_name": clean_name, "domain": clean_domain, "logo_png_b64": ""}
            cleared = st.session_state.get("brand_logo_cleared", False)
            logo = st.session_state.get("brand_draft_logo")
            if logo and not cleared:
                payload["logo_png_b64"] = base64.b64encode(logo).decode("ascii")
            elif not cleared:
                # Pas de modif explicite du logo : on garde l'ancien stocké en BDD.
                payload["logo_png_b64"] = br.get("logo_png_b64") or ""
            db.settings["branding"] = payload
            save_settings(db)
            # Nettoie les drafts, la prochaine ouverture lit la BDD.
            for k in ("brand_draft_name", "brand_draft_domain", "brand_draft_logo",
                      "brand_upload_last", "brand_logo_cleared"):
                st.session_state.pop(k, None)
            st.success(T("Marque enregistrée — visible dès le prochain rafraîchissement."))
            st.rerun()
        if a2.button(T("Annuler"), width="stretch", key="brand_cancel"):
            for k in ("brand_draft_name", "brand_draft_domain", "brand_draft_logo",
                      "brand_upload_last", "brand_logo_cleared"):
                st.session_state.pop(k, None)
            st.rerun()

    # --- Preview live -------------------------------------------------------
    with right:
        st.markdown(f'<div style="font-size:10.5px; color:{THEME["muted"]}; text-transform:uppercase; '
                    f'font-weight:700; margin-bottom:6px">{T("Aperçu")}</div>', unsafe_allow_html=True)
        preview_name = (name or "").strip() or T("(Nom de l'entreprise)")
        safe_name = _html.escape(preview_name)
        logo_html = ""
        if st.session_state.get("brand_logo_cleared"):
            logo_bytes = None  # user a cliqué "Retirer le logo" : la preview reflète le choix
        else:
            logo_bytes = st.session_state.get("brand_draft_logo") or _branding_logo_bytes(br)
        if logo_bytes:
            b64 = base64.b64encode(logo_bytes).decode("ascii")
            logo_html = (f'<img src="data:image/png;base64,{b64}" '
                         f'style="max-height:72px; max-width:160px; object-fit:contain; '
                         f'background:#fff; border-radius:8px; padding:6px"/>')
        else:
            # Placeholder : initiales sur fond accent
            initials = "".join(p[0] for p in preview_name.split()[:2]).upper() or "?"
            logo_html = (f'<div style="width:72px; height:72px; border-radius:12px; '
                         f'background:{THEME["accent"]}; color:#0A1220; display:flex; '
                         f'align-items:center; justify-content:center; font-family:Oswald, sans-serif; '
                         f'font-weight:700; font-size:28px; letter-spacing:1px">{_html.escape(initials)}</div>')

        st.markdown(
            f'<div style="background:{THEME["panel"]}; border:1px solid {THEME["border"]}; '
            f'border-radius:14px; padding:18px; display:flex; align-items:center; gap:16px">'
            f'{logo_html}'
            f'<div>'
            f'  <div style="font-family:Oswald, sans-serif; text-transform:uppercase; '
            f'letter-spacing:1px; font-size:17px; color:{THEME["text"]}">{safe_name}</div>'
            f'  <div style="font-size:11.5px; color:{THEME["muted"]}; margin-top:4px">'
            f'    {T("Propulsé par AMI — Analyse de Maintenance Industrielle")}'
            f'  </div>'
            f'</div>'
            f'</div>', unsafe_allow_html=True)

        st.caption(T("La marque apparaît aussi dans la barre latérale et sur l'écran de connexion."))


# ---------------------------------------------------------------------------
# SECTION : Utilisateurs (admin uniquement)
# ---------------------------------------------------------------------------
def view_users(db):
    users = auth.list_users()
    section_title("Comptes utilisateurs")
    st.dataframe(pd.DataFrame([{"Identifiant": u, "Rôle": r} for u, r in users.items()]),
                 width="stretch", hide_index=True)
    st.caption("Rôles — **root** : technique · **admin** : tout · "
               "**operator** : saisie · **viewer** : lecture seule.")

    # Seul le root peut créer/modifier d'autres root. Un admin ne voit que
    # [admin, operator, viewer] et ne peut pas éditer un compte root existant.
    role_choices = auth.ROLES if is_root() else [r for r in auth.ROLES if r != "root"]

    section_title("Ajouter un utilisateur")
    with st.form("add_user_form", clear_on_submit=True):
        c = st.columns([2, 2, 1.4, 1.1])
        nu = c[0].text_input("Identifiant")
        npw = c[1].text_input("Mot de passe", type="password")
        default_role = "operator" if "operator" in role_choices else role_choices[-1]
        nrole = c[2].selectbox("Rôle", role_choices, index=role_choices.index(default_role))
        if c[3].form_submit_button("Ajouter", type="primary"):
            ok, msg = auth.create_user(nu, npw, nrole)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    section_title("Modifier / supprimer")
    # Un admin ne voit pas les comptes root dans le selecteur : interdiction d'y toucher.
    editable = {u: r for u, r in users.items() if is_root() or r != "root"}
    if not editable:
        st.info(T("Aucun compte modifiable à votre niveau."))
        return
    target = st.selectbox("Utilisateur", list(editable.keys()), key="user_target")
    if target:
        current_role = users[target]
        # Choix de rôles : un admin ne peut pas promouvoir en root.
        allowed = role_choices if current_role in role_choices else [current_role]
        cc = st.columns([1.6, 1, 1.6, 1, 1.2])
        role = cc[0].selectbox("Rôle", allowed,
                               index=allowed.index(current_role) if current_role in allowed else 0,
                               key="user_role")
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
# SECTION : Observabilité (root uniquement)
# ---------------------------------------------------------------------------
@st.cache_resource
def _runtime_counters():
    """Compteurs globaux partagés entre sessions (reset au reboot du process)."""
    return {"start_ts": time.time(), "reruns": 0, "logins": 0, "errors": 0}


def _probe_memory():
    """Mémoire process + système. Linux via /proc, fallback resource ailleurs."""
    out = {}
    # Process (Linux)
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
                elif line.startswith("VmSize:"):
                    out["vsize_mb"] = round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    # Process (fallback resource — macOS, BSD)
    if "rss_mb" not in out:
        try:
            import resource as _res
            r = _res.getrusage(_res.RUSAGE_SELF)
            maxrss = r.ru_maxrss
            out["rss_mb"] = round(maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
        except Exception:
            pass
    # Système (Linux)
    try:
        with open("/proc/meminfo") as f:
            data = f.read()
        import re as _re2
        def _grab(k):
            m = _re2.search(rf"^{k}:\s+(\d+) kB", data, _re2.MULTILINE)
            return round(int(m.group(1)) / 1024, 1) if m else None
        out["sys_total_mb"] = _grab("MemTotal")
        out["sys_avail_mb"] = _grab("MemAvailable")
    except Exception:
        pass
    # CPU time
    try:
        import resource as _res
        r = _res.getrusage(_res.RUSAGE_SELF)
        out["cpu_user_s"] = round(r.ru_utime, 1)
        out["cpu_sys_s"] = round(r.ru_stime, 1)
    except Exception:
        pass
    return out


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, sec = divmod(sec, 60)
    if d: return f"{d}j {h}h {m}min"
    if h: return f"{h}h {m}min"
    if m: return f"{m}min {sec}s"
    return f"{sec}s"


def view_observability(db):
    if not is_root():
        st.error(T("Accès réservé au compte root."))
        return
    section_title("Supervision technique")

    counters = _runtime_counters()
    counters["reruns"] = counters.get("reruns", 0) + 1
    t_start = time.time()

    # --- Build & backend ---------------------------------------------------
    sha = _build_sha() or "—"
    try:
        from admi import db as _dbmod
        backend = _dbmod.backend_label()
        db_url = _dbmod._database_url()
    except Exception:
        backend, db_url = "?", "?"
    import re as _re
    masked = _re.sub(r"(://[^:]+:)([^@]+)(@)", r"\1***\3", db_url or "")

    c = st.columns(4)
    with c[0]: kpi_card("Build (commit)", sha, color=THEME["accent2"], value_size=18)
    with c[1]: kpi_card("Backend DB", backend, color=THEME["success"], value_size=18)
    uptime_s = time.time() - counters.get("start_ts", time.time())
    with c[2]: kpi_card("Uptime", _fmt_duration(uptime_s), color=THEME["accent"], value_size=18)
    with c[3]: kpi_card("Reruns", fmt_num(counters.get("reruns", 0)), color=THEME["warn"])

    st.caption(f"DATABASE_URL : `{masked}`")
    st.write("")

    # --- Ressources système -----------------------------------------------
    section_title("Ressources — CPU & mémoire")
    mem = _probe_memory()
    rss_mb = mem.get("rss_mb")
    sys_total = mem.get("sys_total_mb")
    sys_avail = mem.get("sys_avail_mb")
    # Streamlit Cloud free tier = 1 GB RAM par app.
    sl_quota_mb = 1024
    rss_pct = (rss_mb / sl_quota_mb * 100) if rss_mb else None

    m = st.columns(4)
    with m[0]:
        kpi_card("Mémoire process (RSS)",
                 f"{rss_mb} Mo" if rss_mb is not None else "—",
                 color=THEME["danger"] if (rss_pct and rss_pct > 80)
                 else THEME["warn"] if (rss_pct and rss_pct > 60)
                 else THEME["success"],
                 value_size=18)
    with m[1]:
        kpi_card("% du quota 1 Go",
                 f"{round(rss_pct, 1)} %" if rss_pct is not None else "—",
                 color=THEME["accent"], value_size=18)
    with m[2]:
        kpi_card("RAM système totale",
                 f"{sys_total} Mo" if sys_total else "—",
                 color=THEME["accent2"], value_size=18)
    with m[3]:
        kpi_card("RAM système dispo",
                 f"{sys_avail} Mo" if sys_avail else "—",
                 color=THEME["success"] if (sys_avail and sys_total and sys_avail / sys_total > .3)
                 else THEME["warn"], value_size=18)

    cpu_u = mem.get("cpu_user_s")
    cpu_s = mem.get("cpu_sys_s")
    vsize = mem.get("vsize_mb")
    c2 = st.columns(4)
    with c2[0]:
        kpi_card("CPU user (cumulé)",
                 f"{cpu_u}s" if cpu_u is not None else "—",
                 color=THEME["muted"], value_size=16)
    with c2[1]:
        kpi_card("CPU sys (cumulé)",
                 f"{cpu_s}s" if cpu_s is not None else "—",
                 color=THEME["muted"], value_size=16)
    with c2[2]:
        kpi_card("Mémoire virtuelle (VSize)",
                 f"{vsize} Mo" if vsize else "—",
                 color=THEME["muted"], value_size=16)
    with c2[3]:
        kpi_card("Reruns/min",
                 f"{round(counters['reruns'] / max(uptime_s / 60, 1), 1)}",
                 color=THEME["muted"], value_size=16)
    st.caption(T("Quota Streamlit Community Cloud ≈ 1 Go RAM par app. "
                 "L'app redémarre automatiquement si on dépasse — données sauves dans Supabase."))
    st.write("")

    # --- Volumétrie BDD ----------------------------------------------------
    section_title("Volumétrie base de données")
    rows = [
        {T("Entité"): T("Machines"), T("Lignes"): len(db.machines)},
        {T("Entité"): T("Arrêts"), T("Lignes"): len(db.arrets)},
        {T("Entité"): T("Interventions"), T("Lignes"): len(db.interventions)},
        {T("Entité"): T("Énergie"), T("Lignes"): len(db.energie)},
        {T("Entité"): T("Planning"), T("Lignes"): len(db.planning)},
        {T("Entité"): T("Pièces"), T("Lignes"): len(db.pieces)},
        {T("Entité"): T("Mouvements"), T("Lignes"): len(db.mouvements)},
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.write("")

    # --- Comptes & rôles ---------------------------------------------------
    section_title("Comptes & rôles")
    users_tbl = [{T("Identifiant"): u, T("Rôle"): r} for u, r in auth.list_users().items()]
    st.dataframe(pd.DataFrame(users_tbl), width="stretch", hide_index=True)
    st.caption(T("Pour consulter les logs d'exécution (crashs, exceptions) : "
                 "Streamlit Cloud → Manage app → logs en bas de page. Les logs ne "
                 "sont pas exposés dans l'app par sécurité."))
    st.write("")

    # --- Session en cours --------------------------------------------------
    section_title("Session courante")
    import datetime as _dt
    elapsed_ms = round((time.time() - t_start) * 1000, 1)
    st.write(pd.DataFrame([{
        T("Utilisateur"): st.session_state.get("user", "—"),
        T("Rôle"): st.session_state.get("role", "—"),
        T("Langue"): st.session_state.get("lang", "fr"),
        T("Horodatage"): _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        T("Rendu (ms)"): elapsed_ms,
    }]))
    st.caption(T("💡 Streamlit redémarre le conteneur s'il dépasse 1 Go. Pour la beta, "
                 "surveille surtout la jauge « % du quota ». Au-delà de 80 %, c'est "
                 "souvent lié à un rapport PDF simultané — rien de grave, ça se relance."))


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
        cfg_test = get_alert_config()
        # Un bouton de test rend compte de l'échec ; il ne fait pas tomber l'écran.
        try:
            res = alerts.notify(
                cfg_test, T("Test de configuration"),
                T("Si vous lisez ce message, les alertes AMI sont correctement configurées."),
                {T("Envoyé le"): datetime.now().strftime("%d/%m/%Y %H:%M"),
                 T("Serveur"): cfg_test.get("smtp", {}).get("host", "—"),
                 T("Destinataires"): ", ".join(cfg_test.get("emails", [])) or "—"})
        except Exception as exc:  # noqa: BLE001
            st.error(f'{T("Échec du test")} : {exc}')
            res = {}
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
    if is_root():
        sections["Observabilité"] = view_observability
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
        "Observabilité": "Supervision technique (root uniquement)",
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
    c5, c6 = st.columns(2)
    with c5:
        seuil_maint = st.number_input(T("Seuil d'entretien (h, 0 = aucun)"), 0.0, 1_000_000.0,
                                      float(m.get("seuilMaintenanceH") or 0) if m else 0.0, 100.0)
    with c6:
        seuil_arret = st.number_input(T("Seuil d'arrêt (h, 0 = aucun)"), 0.0, 1_000_000.0,
                                      float(m.get("seuilArretH") or 0) if m else 0.0, 100.0)
    if m:
        st.caption(T("Heures d'utilisation actuelles")
                   + f" : {fmt_num(kpis.machine_usage_hours(db, m))} h")
    save, delete, cancel = _dialog_buttons(m is not None)
    if save:
        if not nom.strip():
            st.warning(T("Le nom de la machine est requis."))
        else:
            data = {"nom": nom.strip(), "departementId": deptid, "puissanceKW": kw,
                    "dateMES": mes.isoformat(), "statut": statut,
                    "seuilMaintenanceH": seuil_maint, "seuilArretH": seuil_arret}
            rec = {**m, **data} if m else {"id": uid(), **data}
            upsert_record(db, "machines", rec)
            if statut == "En panne" and (m is None or m.get("statut") != "En panne"):
                _maybe_alert(
                    f"AMI — {i18n.type_label('En panne')} : {nom.strip()}",
                    T("Cette machine vient d'être signalée en panne dans AMI."),
                    {T("Machine"): nom.strip(),
                     T("Département"): i18n.dept_label(deptid, dep(deptid)["nom"]),
                     T("Statut"): i18n.type_label("En panne")})
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
                _maybe_alert(
                    f"AMI — {i18n.t('Panne')} : {mn}",
                    T("Un arrêt de type « Panne » vient d'être enregistré dans AMI."),
                    {T("Machine"): mn,
                     T("Département"): i18n.dept_label(db.machine_dept(machine_id),
                                                       dep(db.machine_dept(machine_id))["nom"]),
                     T("Cause"): cause.strip() or "—",
                     T("Début"): debut.strftime("%d/%m/%Y %H:%M")})
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


def _hide_app_chrome_css():
    """Masque le chrome Streamlit (menu « ⋮ », Deploy/Share, footer) pour les users.
    Le propriétaire du déploiement garde « Manage app » en bas à droite — Streamlit
    ne l'injecte que pour les comptes authentifiés sur share.streamlit.io, donc
    le client ne le voit pas de son côté.
    """
    st.markdown("""<style>
      /* Menu hamburger, Deploy, Share, settings */
      [data-testid="stToolbar"], [data-testid="stDecoration"],
      [data-testid="stStatusWidget"], [data-testid="stMainMenu"],
      header[data-testid="stHeader"] button[kind="headerNoPadding"],
      header[data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"] {
        display: none !important; visibility: hidden !important;
      }
      /* Footer « Made with Streamlit » */
      footer, [data-testid="stFooter"] { display:none !important; }
      /* Le header lui-même est un bandeau transparent : on réduit sa place */
      header[data-testid="stHeader"] { height: 0 !important; background: transparent !important; }
      .block-container { padding-top: 1rem !important; }
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


def _branding_banner_html() -> str:
    """Petit bandeau 'Client — logo + nom' affiché si une marque est configurée."""
    import base64
    import html as _html
    try:
        db_tmp = load_db()
        br = _branding_from_db(db_tmp)
    except Exception:
        return ""
    name = (br.get("company_name") or "").strip()
    if not name:
        return ""
    safe_name = _html.escape(name)
    logo_bytes = _branding_logo_bytes(br)
    if logo_bytes:
        b64 = base64.b64encode(logo_bytes).decode("ascii")
        logo = (f'<img src="data:image/png;base64,{b64}" '
                f'style="max-height:48px; max-width:120px; object-fit:contain; '
                f'background:#fff; border-radius:8px; padding:4px"/>')
    else:
        initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
        logo = (f'<div style="width:48px; height:48px; border-radius:10px; '
                f'background:{THEME["accent"]}; color:#0A1220; display:flex; '
                f'align-items:center; justify-content:center; font-family:Oswald, sans-serif; '
                f'font-weight:700; font-size:20px; letter-spacing:1px">{_html.escape(initials)}</div>')
    return (f'<div style="display:flex; justify-content:center; margin-top:14px">'
            f'  <div style="display:flex; align-items:center; gap:12px; background:{THEME["panel"]}; '
            f'    border:1px solid {THEME["border"]}; border-radius:12px; padding:10px 18px">'
            f'    {logo}'
            f'    <div style="font-family:Oswald, sans-serif; text-transform:uppercase; '
            f'      letter-spacing:1px; font-size:15px; color:{THEME["text"]}">{safe_name}</div>'
            f'  </div>'
            f'</div>')


def render_login_screen():
    _hide_chrome_css()
    _lang_toggle()
    # Logo client AU-DESSUS du logo AMI (si configuré).
    banner = _branding_banner_html()
    if banner:
        st.markdown(banner, unsafe_allow_html=True)
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
                # Persiste la session dans l'URL (si une clé de signature est
                # configurée). Si pas de clé → pas de persistance, l'utilisateur
                # devra se reconnecter après un F5 — c'est le fail-closed.
                try:
                    tok = auth.make_session_token(res["username"], res["role"])
                    if tok:
                        st.query_params["tok"] = tok
                except Exception:
                    pass
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

    # Auto-login depuis un jeton signé stocké dans l'URL : survit à un F5.
    if not st.session_state.get("user"):
        try:
            tok = st.query_params.get("tok", "")
        except Exception:
            tok = ""
        if tok:
            data = auth.read_session_token(tok)
            if data:
                st.session_state.user = data["u"]
                st.session_state.role = data["r"]

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
    _hide_app_chrome_css()   # cache menu Streamlit, Deploy/Share, footer pour les users
    if not st.session_state.get("_usage_checked"):
        check_machine_usage_alerts(db)
        st.session_state["_usage_checked"] = True

    # Bandeau client en haut de page (logo + nom) si configuré en Paramètres.
    _br = _branding_from_db(db)
    _br_name = (_br.get("company_name") or "").strip()
    if _br_name:
        import base64 as _b64
        import html as _html
        _safe = _html.escape(_br_name)
        _logo_bytes = _branding_logo_bytes(_br)
        if _logo_bytes:
            _img_b64 = _b64.b64encode(_logo_bytes).decode("ascii")
            _top_logo = (f'<img src="data:image/png;base64,{_img_b64}" '
                         f'style="max-height:40px; max-width:140px; object-fit:contain; '
                         f'background:#fff; border-radius:8px; padding:4px"/>')
        else:
            _ini = "".join(p[0] for p in _br_name.split()[:2]).upper() or "?"
            _top_logo = (f'<div style="width:40px; height:40px; border-radius:9px; '
                         f'background:{THEME["accent"]}; color:#0A1220; display:flex; '
                         f'align-items:center; justify-content:center; font-family:Oswald, sans-serif; '
                         f'font-weight:700; font-size:17px">{_html.escape(_ini)}</div>')
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:14px; '
            f'padding:10px 16px; margin:0 0 14px 0; '
            f'background:linear-gradient(90deg, {THEME["panel"]}, {THEME["panel2"]}); '
            f'border:1px solid {THEME["border"]}; border-radius:12px">'
            f'  {_top_logo}'
            f'  <div style="flex:1">'
            f'    <div style="font-family:Oswald, sans-serif; text-transform:uppercase; '
            f'      letter-spacing:1px; font-size:16px; color:{THEME["text"]}">{_safe}</div>'
            f'    <div style="font-size:11px; color:{THEME["muted"]}; margin-top:2px">'
            f'      AMI — {T("Analyse de Maintenance Industrielle")}'
            f'    </div>'
            f'  </div>'
            f'</div>', unsafe_allow_html=True)

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
        _br = _branding_from_db(db)
        _br_name = (_br.get("company_name") or "").strip()
        if _br_name:
            import base64 as _b64
            import html as _html
            _safe_br_name = _html.escape(_br_name)
            _logo = _branding_logo_bytes(_br)
            if _logo:
                _img_b64 = _b64.b64encode(_logo).decode("ascii")
                _logo_html = (f'<img src="data:image/png;base64,{_img_b64}" '
                              f'style="max-height:28px; max-width:70px; object-fit:contain; '
                              f'background:#fff; border-radius:6px; padding:3px"/>')
            else:
                _ini = "".join(p[0] for p in _br_name.split()[:2]).upper() or "?"
                _logo_html = (f'<div style="width:28px; height:28px; border-radius:7px; '
                              f'background:{THEME["accent"]}; color:#0A1220; display:flex; '
                              f'align-items:center; justify-content:center; '
                              f'font-family:Oswald, sans-serif; font-weight:700; '
                              f'font-size:13px">{_html.escape(_ini)}</div>')
            st.markdown(
                f'<div style="display:flex; align-items:center; gap:10px; '
                f'margin:10px 0 4px 0; padding:8px 10px; '
                f'border:1px solid {THEME["border"]}; border-radius:10px; background:{THEME["panel"]}">'
                f'  {_logo_html}'
                f'  <div style="font-family:Oswald, sans-serif; text-transform:uppercase; '
                f'    letter-spacing:.5px; font-size:12.5px; color:{THEME["text"]}">{_safe_br_name}</div>'
                f'</div>', unsafe_allow_html=True)
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
            try:
                if "tok" in st.query_params:
                    del st.query_params["tok"]
            except Exception:
                pass
            st.rerun()
        sha = _build_sha()
        if sha:
            st.caption(f"build `{sha}`")

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
        st.iframe(admi_theme.live_clock_html(_lang()), height=62)
    st.session_state["_plot_n"] = 0   # clés de graphiques stables par run
    SECTIONS[choice](db)


if __name__ == "__main__":
    main()
