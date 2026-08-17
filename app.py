"""ADMI — Analyse des Données de Maintenance Industrielle (application Streamlit).

Lancement :  streamlit run app.py
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_calendar import calendar as st_calendar

from admi import auth, charts, i18n, kpis, license as lic, report, update
from admi.config import (DEPARTEMENTS, DOW, MOIS, STATUTS_MACHINE, THEME,
                         TYPES_ARRET, TYPES_INTERV, TYPES_PLAN, dep)
from admi.data import (DATA_FILE, delete_record, load_db, save_db,
                       save_settings, uid, upsert_record)


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
from admi.theme import CSS, register_template

st.set_page_config(page_title="ADMI — Maintenance Industrielle",
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


def fmt_num(n, dec=0):
    s = f"{float(n or 0):,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", " ")


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

    # -- Jauge de disponibilité + MTBF / MTTR / coût --
    left, right = st.columns([1.1, 1])
    with left:
        section_title("Disponibilité")
        plot(charts.gauge_disponibilite(k["disponibilite"]))
        st.markdown(
            f'<div style="text-align:center; color:{THEME["muted2"]}; font-size:12px">'
            f'{k["nbArrets"]} arrêt(s) — {fmt_num(k["tempsArretH"],1)} h d\'arrêt sur la période</div>',
            unsafe_allow_html=True)
    with right:
        kpi_card("MTBF", fmt_num(k["mtbf"], 1) if k["mtbf"] is not None else "—",
                 "heures" if k["mtbf"] is not None else "",
                 f'Temps moyen entre pannes ({k["nbPannes"]} panne(s))', THEME["accent2"])
        st.write("")
        kpi_card("MTTR", fmt_num(k["mttr"], 1) if k["mttr"] is not None else "—",
                 "heures" if k["mttr"] is not None else "",
                 "Temps moyen de réparation", THEME["warn"])
        st.write("")
        kpi_card("Coût maintenance", fmt_money(k["coutMaint"]), "",
                 "Pièces + main d'œuvre, période sélectionnée", THEME["success"], value_size=22)

    st.write("")
    # -- 4 KPI --
    g = st.columns(4)
    with g[0]:
        kpi_card("Temps d'arrêt cumulé", fmt_num(k["tempsArretH"], 1), "heures", color=THEME["accent2"])
    with g[1]:
        kpi_card("Énergie consommée", fmt_num(k["kwh"], 0), "kWh", color=THEME["accent2"])
    with g[2]:
        kpi_card("Coût énergie", fmt_money(k["coutEnergie"]), "", color=THEME["accent"], value_size=22)
    with g[3]:
        kpi_card("Puissance installée", fmt_num(k["puissanceInstallee"], 0), "kW", color="#94A3B8")

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

    r2a, r2b = st.columns(2)
    with r2a:
        section_title("Consommation énergétique par département (kWh)")
        plot(charts.bar_energie_by_dept(kpis.energie_by_dept(energie_p)))
    with r2b:
        section_title("Répartition de la consommation énergétique")
        plot(charts.pie_energie_repartition(kpis.energie_by_dept(energie_p)))

    energie_annee = [e for e in db.energie
                     if e["annee"] == annee and (dept == "all" or e["departementId"] == dept)]
    r3a, r3b = st.columns(2)
    with r3a:
        section_title(f"Consommation énergétique mensuelle — {annee}")
        plot(charts.stacked_energie_mensuelle(energie_annee, dept))
    with r3b:
        section_title("Interventions préventif / correctif par département")
        plot(charts.grouped_interv_prevcorr(kpis.interv_prev_corr_by_dept(intervs)))

    st.write("")
    tcol1, tcol2 = st.columns([3, 1])
    with tcol2:
        metric_label = st.selectbox("Métrique de tendance",
                                    ["Temps d'arrêt (h)", "Coût maintenance (FCFA)",
                                     "Consommation énergie (kWh)", "Disponibilité (%)"],
                                    key="trend_metric")
    metric_map = {"Temps d'arrêt (h)": "tempsArretH", "Coût maintenance (FCFA)": "coutMaint",
                  "Consommation énergie (kWh)": "kwh", "Disponibilité (%)": "disponibilite"}
    with tcol1:
        section_title("Tendance pluriannuelle (depuis 2020)")
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
    rows = [{"Machine": m["nom"], "Département": dep(m["departementId"])["court"],
             "Puissance (kW)": m.get("puissanceKW", 0), "Mise en service": m.get("dateMES", ""),
             "Statut": m.get("statut", "")} for m in db.machines]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if st.session_state.get("mach_target"):
        machine_dialog(db, st.session_state.mach_target)


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

    section_title("Journal des arrêts")
    rows = [{"Machine": db.machine_name(a["machineId"]), "Dépt.": dep(a["departementId"])["court"],
             "Type": a["type"], "Début": a["dateDebut"].replace("T", " "),
             "Fin": a["dateFin"].replace("T", " "),
             "Durée (h)": round(kpis.hours_between(a["dateDebut"], a["dateFin"]), 1),
             "Cause": a.get("cause", "")} for a in arrets]
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
        rows.append({"Date": i["date"], "Machine": db.machine_name(i["machineId"]),
                     "Dépt.": dep(i["departementId"])["court"], "Type": i["type"],
                     "Technicien": i.get("technicien", ""),
                     "Durée (h)": i.get("duree", 0), "Pièces": n_pieces,
                     "Coût total (FCFA)": round(kpis.intervention_cost(i))})
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
            st.download_button("⬇ Rapport d'intervention (PDF)",
                               report.build_intervention_report(db, chosen),
                               file_name=f"ADMI_intervention_{chosen['date']}.pdf",
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
    rows = [{"Mois": MOIS[e["mois"]], "Département / Service": dep(e["departementId"])["nom"],
             "Consommation (kWh)": e["kwh"], "Montant (FCFA)": e["montant"]}
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
        st.download_button("⬇ Exporter en Excel", export_bytes(db),
                           file_name="ADMI_export.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with tpl:
        section_title("Modèle d'import")
        st.download_button("⬇ Télécharger le modèle Excel", template_bytes(),
                           file_name="ADMI_modele_import.xlsx",
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
                       "les données déjà enregistrées dans ADMI.")
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
# Navigation
# ---------------------------------------------------------------------------
def _nav():
    """Construit la navigation à l'exécution (toutes les vues sont alors définies)."""
    sections = {
        "Tableau de bord": view_dashboard,
        "Planning": view_planning,
        "Machines & Puissance": view_machines,
        "Temps d'arrêt": view_arrets,
        "Interventions": view_interventions,
        "Énergie": view_energie,
        "Rapports": view_report,
        "Import / Export": view_import,
        "Paramètres": view_settings,
    }
    if is_admin():
        sections["Utilisateurs"] = view_users
    subtitles = {
        "Tableau de bord": "Vue d'ensemble des indicateurs de maintenance",
        "Planning": "Calendrier des interventions planifiées (mois / année)",
        "Machines & Puissance": "Parc machines et puissance installée par département",
        "Temps d'arrêt": "Journal des arrêts machines par département",
        "Interventions": "Historique des interventions et coûts pièces / main d'œuvre",
        "Énergie": "Suivi par département, administration et services",
        "Rapports": "Générer un rapport complet (HTML / PDF)",
        "Import / Export": "Alimenter ADMI avec vos données, ou exporter une sauvegarde",
        "Paramètres": "Heures de travail de l'usine par département",
        "Utilisateurs": "Gestion des comptes et des rôles",
    }
    return sections, subtitles


# ---------------------------------------------------------------------------
# SECTION : Rapports
# ---------------------------------------------------------------------------
def view_report(db):
    st.markdown(
        f'<div style="color:{THEME["muted2"]}; font-size:12.5px; margin-bottom:10px">'
        "Générez un rapport complet (indicateurs, graphiques, synthèse par département) au format "
        "<b>HTML autonome</b> (interactif, imprimable en PDF depuis le navigateur) ou <b>PDF</b>.</div>",
        unsafe_allow_html=True)

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
    if st.button("⚙ Générer le rapport", type="primary"):
        with st.spinner("Génération du rapport en cours…"):
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
            st.download_button("⬇ Télécharger le rapport HTML", st.session_state.rep_html,
                               file_name=f"ADMI_rapport_{lab}.html", mime="text/html", width="stretch")
        with d2:
            if st.session_state.get("rep_pdf"):
                st.download_button("⬇ Télécharger le rapport PDF", st.session_state.rep_pdf,
                                   file_name=f"ADMI_rapport_{lab}.pdf", mime="application/pdf",
                                   width="stretch")
            else:
                st.button("PDF indisponible", disabled=True, width="stretch")
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
      <div class="logo"><span class="sq"></span>ADMI</div>
      <div class="sub">Analyse des Données de Maintenance Industrielle</div>
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
    nom = st.text_input("Nom de la machine", value=(m["nom"] if m else ""),
                        placeholder="Ex : Presse à injection AM-3")
    c1, c2 = st.columns(2)
    with c1:
        deptid = _dept_picker("Département", (m["departementId"] if m else "am"), key="mach_dlg_dept")
    with c2:
        kw = st.number_input("Puissance (kW)", 0.0, 100000.0,
                             float(m["puissanceKW"]) if m else 0.0, 0.5)
    c3, c4 = st.columns(2)
    with c3:
        mes = st.date_input("Mise en service", format="DD/MM/YYYY",
                            value=date.fromisoformat(m["dateMES"]) if (m and m.get("dateMES")) else date.today())
    with c4:
        statut = st.selectbox("Statut", STATUTS_MACHINE,
                              index=STATUTS_MACHINE.index(m["statut"]) if (m and m["statut"] in STATUTS_MACHINE) else 0)
    save, delete, cancel = _dialog_buttons(m is not None)
    if save:
        if not nom.strip():
            st.warning("Le nom de la machine est requis.")
        else:
            data = {"nom": nom.strip(), "departementId": deptid, "puissanceKW": kw,
                    "dateMES": mes.isoformat(), "statut": statut}
            rec = {**m, **data} if m else {"id": uid(), **data}
            upsert_record(db, "machines", rec)
            _close_dialog("mach"); st.rerun()
    if delete and m:
        delete_record(db, "machines", m["id"])
        _close_dialog("mach"); st.rerun()
    if cancel:
        _close_dialog("mach"); st.rerun()


@st.dialog("Arrêt de maintenance")
def arret_dialog(db, target):
    mode, val = target
    a = next((x for x in db.arrets if x["id"] == val), None) if mode == "edit" else None
    names, ids = _machine_opts(db)
    if not names:
        st.warning("Ajoutez d'abord au moins une machine (onglet Machines).")
        if st.button("Fermer"):
            _close_dialog("arret"); st.rerun()
        return
    midx = ids.index(a["machineId"]) if (a and a["machineId"] in ids) else 0
    machine_id = ids[names.index(st.selectbox("Machine", names, index=midx))]
    typ = st.selectbox("Type d'arrêt", TYPES_ARRET,
                       index=TYPES_ARRET.index(a["type"]) if (a and a["type"] in TYPES_ARRET) else 0)
    cause = st.text_input("Cause", value=(a.get("cause", "") if a else ""), placeholder="Ex : Rupture courroie")
    dd0 = datetime.fromisoformat(a["dateDebut"]) if a else datetime.now().replace(second=0, microsecond=0)
    df0 = datetime.fromisoformat(a["dateFin"]) if a else dd0
    c1, c2 = st.columns(2)
    d_deb = c1.date_input("Date de début", value=dd0.date(), format="DD/MM/YYYY")
    t_deb = c2.time_input("Heure de début", value=dd0.time())
    c3, c4 = st.columns(2)
    d_fin = c3.date_input("Date de fin", value=df0.date(), format="DD/MM/YYYY")
    t_fin = c4.time_input("Heure de fin", value=df0.time())
    desc = st.text_area("Description", value=(a.get("description", "") if a else ""))
    save, delete, cancel = _dialog_buttons(a is not None)
    if save:
        debut = datetime.combine(d_deb, t_deb)
        fin = datetime.combine(d_fin, t_fin)
        if fin < debut:
            st.warning("La date de fin doit être après le début.")
        else:
            data = {"machineId": machine_id, "departementId": db.machine_dept(machine_id), "type": typ,
                    "cause": cause.strip(), "dateDebut": debut.strftime("%Y-%m-%dT%H:%M"),
                    "dateFin": fin.strftime("%Y-%m-%dT%H:%M"), "description": desc.strip()}
            rec = {**a, **data} if a else {"id": uid(), **data}
            upsert_record(db, "arrets", rec)
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
        st.warning("Ajoutez d'abord au moins une machine (onglet Machines).")
        if st.button("Fermer"):
            _close_dialog("interv"); st.rerun()
        return
    c1, c2 = st.columns(2)
    idate = c1.date_input("Date", format="DD/MM/YYYY",
                          value=date.fromisoformat(it["date"]) if it else date.today())
    midx = ids.index(it["machineId"]) if (it and it["machineId"] in ids) else 0
    machine_id = ids[names.index(c2.selectbox("Machine", names, index=midx))]
    c3, c4 = st.columns(2)
    typ = c3.selectbox("Type d'intervention", TYPES_INTERV,
                       index=TYPES_INTERV.index(it["type"]) if (it and it["type"] in TYPES_INTERV) else 0)
    tech = c4.text_input("Technicien(s)", value=(it.get("technicien", "") if it else ""))
    c5, c6 = st.columns(2)
    duree = c5.number_input("Durée (h)", 0.0, 1000.0, float(it["duree"]) if it else 0.0, 0.5)
    cout_mo = c6.number_input("Coût main d'œuvre (FCFA)", 0.0, 1e9, float(it["coutMainOeuvre"]) if it else 0.0, 1000.0)
    desc = st.text_area("Description des travaux", value=(it.get("description", "") if it else ""))

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
    if st.button("＋ Ajouter une pièce", key="interv_addpiece"):
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
      <div class="word"><span>A</span><span>D</span><span>M</span><span>I</span></div>
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
    st.markdown(f'<div style="min-height:50vh; display:flex; align-items:center; justify-content:center">'
                f'{gears_html("Chargement", small=True)}</div>', unsafe_allow_html=True)


def _hide_chrome_css():
    st.markdown("""<style>
      section[data-testid="stSidebar"], header[data-testid="stHeader"] { display:none !important; }
      .block-container { padding-top: 2vh !important; }
    </style>""", unsafe_allow_html=True)


def render_license_screen():
    _hide_chrome_css()
    _lang_toggle()
    st.markdown(f'<div style="display:flex;justify-content:center;margin-top:2vh">{gears_html("Activation requise")}</div>',
                unsafe_allow_html=True)
    col = st.columns([1, 1.25, 1])[1]
    en = _lang() == "en"
    with col:
        st.markdown("### " + T("Licence d'utilisation"))
        st.caption("Enter your ADMI license code to activate the software (provided by your reseller, generated with `licgen`)."
                   if en else
                   "Entrez votre code de licence ADMI pour activer le logiciel. "
                   "Un code est fourni par votre revendeur (généré via `licgen`).")
        code = st.text_input(T("Code de licence"), placeholder="ADMI-XXXX-XXXX-XXXX-XXXX", key="lic_code")
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
    st.markdown(f'<div style="display:flex;justify-content:center;margin-top:2vh">{gears_html("Connexion")}</div>',
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
    # 1) licence  2) connexion  3) démarrage animé  4) application
    if not lic.is_activated():
        render_license_screen()
        return
    if not st.session_state.get("user"):
        render_login_screen()
        return
    if not st.session_state.get("booted"):
        ph = st.empty()
        with ph.container():
            st.markdown('<div style="min-height:70vh; display:flex; align-items:center; '
                        f'justify-content:center">{gears_html("Démarrage du tableau de bord")}</div>',
                        unsafe_allow_html=True)
        time.sleep(1.1)
        st.session_state.booted = True
        ph.empty()

    db = get_db()
    SECTIONS, SUBTITLES = _nav()
    lbl = {"en": "Machines: {m} · stops: {a} · interventions: {i}",
           "fr": "{m} machines · {a} arrêts · {i} interventions"}[_lang()]
    with st.sidebar:
        st.markdown(f'<div class="admi-brand"><span class="dot"></span>ADMI</div>'
                    f'<div class="admi-sub">{T("Maintenance Industrielle")}</div>', unsafe_allow_html=True)
        st.write("")
        choice = st.radio("Navigation", list(SECTIONS.keys()), format_func=T,
                          label_visibility="collapsed")
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

    st.markdown(f"# {T(choice)}")
    st.markdown(f'<div style="color:{THEME["muted2"]}; font-size:12px; margin-top:-12px; '
                f'margin-bottom:16px">{T(SUBTITLES[choice])}</div>', unsafe_allow_html=True)
    st.session_state["_plot_n"] = 0   # clés de graphiques stables par run
    SECTIONS[choice](db)


if __name__ == "__main__":
    main()
