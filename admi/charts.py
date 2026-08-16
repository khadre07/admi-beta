"""Constructeurs de graphiques Plotly (thème sombre ADMI)."""
from __future__ import annotations

import plotly.graph_objects as go

from .config import DEPARTEMENTS, MOIS_COURT, THEME, dep
from .theme import style_fig


def _empty(msg: str, height: int = 260):
    fig = go.Figure()
    fig.add_annotation(text=f"<b>Aucune donnée</b><br>{msg}", showarrow=False,
                       font=dict(color=THEME["muted2"], size=13), xref="paper", yref="paper",
                       x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style_fig(fig, height=height)


def gauge_disponibilite(dispo: float, height: int = 240):
    reste = round(100 - dispo, 1)
    fig = go.Figure(go.Pie(
        values=[round(dispo, 1), reste],
        labels=["Disponible", "Temps d'arrêt"],
        marker=dict(colors=[THEME["success"], THEME["danger"]],
                    line=dict(color=THEME["panel"], width=3)),
        hole=0.78, sort=False, direction="clockwise", rotation=0,
        textinfo="none",
        hovertemplate="%{label} : %{value}%<extra></extra>",
    ))
    fig.add_annotation(text=f"<b>{dispo:.1f}%</b>", showarrow=False,
                       font=dict(family="Oswald", size=34, color=THEME["success"]),
                       x=0.5, y=0.54, xref="paper", yref="paper")
    fig.add_annotation(text="DISPONIBLE", showarrow=False,
                       font=dict(size=10, color=THEME["muted"]),
                       x=0.5, y=0.40, xref="paper", yref="paper")
    return style_fig(fig, height=height, showlegend=False, margin=dict(l=0, r=0, t=10, b=0))


def _dept_series(agg: dict, only_positive: bool = True):
    """Retourne (courts, noms, valeurs, couleurs) ordonnés selon DEPARTEMENTS."""
    courts, noms, vals, cols = [], [], [], []
    for d in DEPARTEMENTS:
        v = agg.get(d["id"], 0)
        if only_positive and not v:
            continue
        courts.append(d["court"]); noms.append(d["nom"])
        vals.append(round(v, 2)); cols.append(d["couleur"])
    return courts, noms, vals, cols


def bar_arrets_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg, only_positive=False)
    fig = go.Figure(go.Bar(
        x=courts, y=vals, marker_color=cols, marker_line_width=0,
        customdata=noms, hovertemplate="%{customdata}<br>%{y} h<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title="heures")


def donut_cout_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Ajoutez des rapports d'intervention pour voir la répartition des coûts.", height)
    fig = go.Figure(go.Pie(
        labels=noms, values=vals, marker=dict(colors=cols, line=dict(color=THEME["panel"], width=2)),
        hole=0.62, sort=False, textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} FCFA (%{percent})<extra></extra>",
    ))
    return style_fig(fig, height=height,
                     legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=10)))


def bar_energie_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Saisissez ou importez la consommation énergétique.", height)
    fig = go.Figure(go.Bar(
        x=courts, y=vals, marker_color=cols, customdata=noms,
        hovertemplate="%{customdata}<br>%{y:,.0f} kWh<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title="kWh")


def pie_energie_repartition(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Saisissez ou importez la consommation énergétique.", height)
    fig = go.Figure(go.Pie(
        labels=noms, values=vals, marker=dict(colors=cols, line=dict(color=THEME["panel"], width=2)),
        hole=0.58, sort=False, textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} kWh (%{percent})<extra></extra>",
    ))
    return style_fig(fig, height=height,
                     legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center", font=dict(size=10)))


def stacked_energie_mensuelle(energie_annee: list, dept: str, height: int = 320):
    """Barres empilées : consommation mensuelle par département sur l'année."""
    if not energie_annee:
        return _empty("Aucun relevé énergétique pour cette année.", height)
    depts = DEPARTEMENTS if dept == "all" else [dep(dept)]
    fig = go.Figure()
    for d in depts:
        monthly = [0.0] * 12
        for e in energie_annee:
            if e["departementId"] == d["id"]:
                monthly[e["mois"]] += float(e.get("kwh") or 0)
        if sum(monthly) == 0:
            continue
        fig.add_bar(x=MOIS_COURT, y=monthly, name=d["court"], marker_color=d["couleur"])
    fig.update_layout(barmode="stack", hovermode="x unified")
    return style_fig(fig, height=height, yaxis_title="kWh",
                     legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center", font=dict(size=10)))


def grouped_interv_prevcorr(agg: dict, height: int = 320):
    """agg = {deptId: (preventif, correctif)}."""
    courts, prev, corr = [], [], []
    for d in DEPARTEMENTS:
        p, c = agg.get(d["id"], (0, 0))
        if p + c == 0:
            continue
        courts.append(d["court"]); prev.append(p); corr.append(c)
    if not courts:
        return _empty("Ajoutez des rapports d'intervention pour cette période.", height)
    fig = go.Figure()
    fig.add_bar(x=courts, y=prev, name="Préventif", marker_color=THEME["success"])
    fig.add_bar(x=courts, y=corr, name="Correctif / autre", marker_color=THEME["danger"])
    fig.update_layout(barmode="group")
    return style_fig(fig, height=height,
                     legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center", font=dict(size=10)))


_TREND_LABELS = {
    "tempsArretH": "Temps d'arrêt (h)",
    "coutMaint": "Coût maintenance (FCFA)",
    "kwh": "Consommation énergie (kWh)",
    "disponibilite": "Disponibilité (%)",
}


def line_trend(trend: list, metric: str, height: int = 320):
    years = [r["year"] for r in trend]
    vals = [round(r.get(metric, 0), 2) for r in trend]
    fig = go.Figure(go.Scatter(
        x=years, y=vals, mode="lines+markers", fill="tozeroy",
        line=dict(color=THEME["accent"], width=3, shape="spline"),
        marker=dict(color=THEME["accent"], size=8),
        fillcolor="rgba(242,169,59,0.15)",
        name=_TREND_LABELS.get(metric, metric),
        hovertemplate="%{x}<br>%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(showlegend=False, hovermode="x unified")
    fig.update_xaxes(dtick=1)
    return style_fig(fig, height=height)


def bar_puissance_by_dept(db, height: int = 300):
    agg = {}
    for m in db.machines:
        agg[m["departementId"]] = agg.get(m["departementId"], 0) + float(m.get("puissanceKW") or 0)
    courts, noms, vals, cols = _dept_series(agg, only_positive=False)
    fig = go.Figure(go.Bar(
        y=courts, x=vals, orientation="h", marker_color=cols, customdata=noms,
        hovertemplate="%{customdata}<br>%{x:,.0f} kW<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=48, r=10, t=30, b=10))
    return style_fig(fig, height=height, xaxis_title="kW")


def bar_arrets_by_type(arrets: list, height: int = 260):
    from .config import TYPES_ARRET
    from .kpis import hours_between
    agg = {t: 0.0 for t in TYPES_ARRET}
    for a in arrets:
        agg[a["type"]] = agg.get(a["type"], 0.0) + hours_between(a["dateDebut"], a["dateFin"])
    types = [t for t in TYPES_ARRET if agg.get(t, 0)]
    vals = [round(agg[t], 1) for t in types]
    if not types:
        return _empty("Aucun arrêt sur ce filtre.", height)
    fig = go.Figure(go.Bar(x=types, y=vals, marker_color=THEME["accent"],
                           hovertemplate="%{x}<br>%{y} h<extra></extra>"))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title="heures")
