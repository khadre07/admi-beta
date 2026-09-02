"""Constructeurs de graphiques Plotly (thème sombre ADMI, bilingues FR/EN)."""
from __future__ import annotations

import plotly.graph_objects as go

from . import i18n
from .config import DEPARTEMENTS, THEME, dep
from .theme import style_fig

_t = i18n.t
_n = i18n.fmt_num

# Étiquettes posées sur les marques : l'identité vient du texte, la couleur ne
# fait que la confirmer (les 8 couleurs de départements ne sont pas toutes
# distinguables entre elles, OND et SL en particulier).
_LABEL = dict(textposition="outside", cliponaxis=False,
              textfont=dict(color=THEME["text"], size=11, family="Inter"))
# Écart de 2 px, couleur du panneau, entre deux aplats voisins.
_SPACER = dict(color=THEME["panel"], width=2)


def _labels(vals, dec: int = 0):
    """Valeurs à poser sur les marques — un zéro n'est pas étiqueté."""
    return [_n(v, dec) if v else "" for v in vals]


def _empty(msg: str, height: int = 260):
    fig = go.Figure()
    fig.add_annotation(text=f"<b>{_t('Aucune donnée')}</b><br>{_t(msg)}", showarrow=False,
                       font=dict(color=THEME["muted2"], size=13), xref="paper", yref="paper",
                       x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style_fig(fig, height=height)


def _gauge(part: float, labels, colors, centre: str, sous_titre: str,
           couleur_valeur: str, height: int = 240, cible=None):
    """Anneau à deux segments : `part` (0-100) contre son complément.

    Le chiffre au centre porte l'information ; l'anneau n'est là que pour la
    lecture d'un coup d'œil. La couleur du chiffre suit l'objectif quand il y en
    a un, sinon la couleur de l'indicateur. Si une cible est fixée, un repère la
    marque sur le pourtour — on voit *où* l'on doit être, pas seulement si on y est.
    """
    part = max(0.0, min(100.0, float(part)))
    fig = go.Figure(go.Pie(
        values=[round(part, 1), round(100 - part, 1)],
        labels=labels,
        marker=dict(colors=colors, line=dict(color=THEME["panel"], width=3)),
        hole=0.78, sort=False, direction="clockwise", rotation=0,
        textinfo="none", domain=dict(x=[0.09, 0.91], y=[0.09, 0.91]),
        hovertemplate="%{label} : %{value}%<extra></extra>",
    ))
    if cible is not None:
        c = max(0.6, min(99.4, float(cible)))
        fig.add_trace(go.Pie(
            values=[c - 0.6, 1.2, 100 - c - 0.6],
            marker=dict(colors=["rgba(0,0,0,0)", THEME["text"], "rgba(0,0,0,0)"]),
            hole=0.90, sort=False, direction="clockwise", rotation=0,
            textinfo="none", hoverinfo="skip", showlegend=False,
            domain=dict(x=[0, 1], y=[0, 1]),
        ))
        fig.add_annotation(text=f'{_t("Cible")} {_n(cible, 0)} %', showarrow=False,
                           font=dict(size=10, color=THEME["muted2"]),
                           x=0.5, y=0.02, xref="paper", yref="paper")
    fig.add_annotation(text=f"<b>{centre}</b>", showarrow=False,
                       font=dict(family="Oswald", size=34, color=couleur_valeur),
                       x=0.5, y=0.54, xref="paper", yref="paper")
    fig.add_annotation(text=sous_titre.upper(), showarrow=False,
                       font=dict(size=10, color=THEME["muted"]),
                       x=0.5, y=0.40, xref="paper", yref="paper")
    return style_fig(fig, height=height, showlegend=False, margin=dict(l=0, r=0, t=10, b=0))


def gauge_disponibilite(dispo: float, height: int = 240, couleur: str | None = None,
                        cible=None):
    return _gauge(dispo,
                  labels=[_t("Disponible"), _t("Temps d'arrêt")],
                  colors=[THEME["success"], THEME["danger"]],
                  centre=f"{dispo:.1f}%", sous_titre=_t("Disponible"),
                  couleur_valeur=couleur or THEME["success"], height=height, cible=cible)


def gauge_taux_preventif(taux, height: int = 240, couleur: str | None = None, cible=None):
    """Part des actions préventives planifiées qui ont été réalisées."""
    if taux is None:
        return _empty("Planifiez des actions préventives pour suivre leur réalisation.", height)
    return _gauge(taux,
                  labels=[_t("Réalisées"), _t("En attente / retard")],
                  colors=[THEME["success"], THEME["warn"]],
                  centre=f"{taux:.0f}%", sous_titre=_t("Réalisé"),
                  couleur_valeur=couleur or THEME["success"], height=height, cible=cible)


def _dept_series(agg: dict, only_positive: bool = True):
    """Retourne (courts, noms, valeurs, couleurs) ordonnés selon DEPARTEMENTS.
    Les codes courts (AM, OND…) sont neutres ; les noms complets sont traduits."""
    courts, noms, vals, cols = [], [], [], []
    for d in DEPARTEMENTS:
        v = agg.get(d["id"], 0)
        if only_positive and not v:
            continue
        courts.append(d["court"]); noms.append(i18n.dept_label(d["id"], d["nom"]))
        vals.append(round(v, 2)); cols.append(d["couleur"])
    return courts, noms, vals, cols


def bar_arrets_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg, only_positive=False)
    fig = go.Figure(go.Bar(
        x=courts, y=vals, marker_color=cols, marker_line_width=0,
        text=_labels(vals, 1), **_LABEL,
        customdata=noms, hovertemplate="%{customdata}<br>%{y} h<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title=_t("heures"), bargap=0.34)


def _donut(courts, noms, vals, cols, unite: str, height: int):
    """Donut à libellés extérieurs : chaque part se lit sans légende.

    Sous 4 % la part n'est plus étiquetable sans chevaucher ses voisines — elle
    reste identifiée au survol.
    """
    total = sum(vals) or 1
    textes = [f"{c} · {_n(v, 0)} {unite}<br>{v / total * 100:.0f} %"
              if v / total >= 0.04 else "" for c, v in zip(courts, vals)]
    fig = go.Figure(go.Pie(
        labels=noms, values=vals,
        marker=dict(colors=cols, line=dict(**_SPACER)),
        hole=0.62, sort=False,
        text=textes, textinfo="text", textposition="outside",
        textfont=dict(color=THEME["muted"], size=10.5, family="Inter"),
        automargin=True,
        hovertemplate="%{label}<br>%{value:,.0f} " + unite + " (%{percent})<extra></extra>",
    ))
    # Chaque part est étiquetée : une légende ferait doublon et viendrait
    # chevaucher les étiquettes extérieures.
    return style_fig(fig, height=height, showlegend=False,
                     margin=dict(l=90, r=90, t=20, b=20))


def donut_cout_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Ajoutez des rapports d'intervention pour voir la répartition des coûts.", height)
    return _donut(courts, noms, vals, cols, "FCFA", height)


def bar_energie_by_dept(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Saisissez ou importez la consommation énergétique.", height)
    fig = go.Figure(go.Bar(
        x=courts, y=vals, marker_color=cols, customdata=noms,
        text=_labels(vals), **_LABEL,
        hovertemplate="%{customdata}<br>%{y:,.0f} kWh<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title="kWh", bargap=0.34)


def pie_energie_repartition(agg: dict, height: int = 260):
    courts, noms, vals, cols = _dept_series(agg)
    if not vals:
        return _empty("Saisissez ou importez la consommation énergétique.", height)
    return _donut(courts, noms, vals, cols, "kWh", height)


def stacked_energie_mensuelle(energie_annee: list, dept: str, height: int = 320):
    """Barres empilées : consommation mensuelle par département sur l'année."""
    if not energie_annee:
        return _empty("Aucun relevé énergétique pour cette année.", height)
    months = [i18n.month(i)[:3] for i in range(12)]
    depts = DEPARTEMENTS if dept == "all" else [dep(dept)]
    fig = go.Figure()
    for d in depts:
        monthly = [0.0] * 12
        for e in energie_annee:
            if e["departementId"] == d["id"]:
                monthly[e["mois"]] += float(e.get("kwh") or 0)
        if sum(monthly) == 0:
            continue
        fig.add_bar(x=months, y=monthly, name=d["court"], marker_color=d["couleur"],
                    marker_line=dict(**_SPACER),
                    hovertemplate="%{fullData.name} : %{y:,.0f} kWh<extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified", bargap=0.3)
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
    fig.add_bar(x=courts, y=prev, name=i18n.type_label("Préventif"), marker_color=THEME["success"],
                text=_labels(prev), **_LABEL)
    fig.add_bar(x=courts, y=corr, name=_t("Correctif / autre"), marker_color=THEME["danger"],
                text=_labels(corr), **_LABEL)
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.12)
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
        name=_t(_TREND_LABELS.get(metric, metric)),
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
        text=_labels(vals), **_LABEL,
        hovertemplate="%{customdata}<br>%{x:,.0f} kW<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    fig.update_layout(yaxis=dict(autorange="reversed"), bargap=0.34,
                      margin=dict(l=48, r=54, t=30, b=10))
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
    fig = go.Figure(go.Bar(x=[i18n.type_label(t) for t in types], y=vals, marker_color=THEME["accent"],
                           text=_labels(vals, 1), **_LABEL,
                           hovertemplate="%{x}<br>%{y} h<extra></extra>"))
    fig.update_traces(marker=dict(cornerradius=5))
    return style_fig(fig, height=height, yaxis_title=_t("heures"), bargap=0.4)


def pareto_causes(arrets: list, top: int = 5, height: int = 300):
    """Top des causes d'arrêt, classées, avec le cumul écrit sur la barre.

    Le HTML d'origine superpose des occurrences et un pourcentage cumulé sur
    **deux échelles** — deux mesures de nature différente sur un même cadre se
    lisent mal et laissent croire à des croisements qui n'existent pas. Ici les
    occurrences seules portent l'échelle ; le cumul est une étiquette.
    """
    total = len(arrets)
    if not total:
        return _empty("Ajoutez des arrêts avec une cause renseignée pour voir "
                      "les causes les plus fréquentes.", height)
    compte: dict = {}
    for a in arrets:
        cause = (a.get("cause") or "").strip() or _t("Non renseigné")
        compte[cause] = compte.get(cause, 0) + 1
    classees = sorted(compte.items(), key=lambda kv: (-kv[1], kv[0]))[:top]

    cumul, textes = 0, []
    for _, n in classees:
        cumul += n
        textes.append(f"{_n(n)} · {cumul / total * 100:.0f} %")
    # Barres horizontales, la plus fréquente en haut : les causes sont du texte,
    # illisible à la verticale.
    causes = [c for c, _ in classees][::-1]
    valeurs = [n for _, n in classees][::-1]
    fig = go.Figure(go.Bar(
        y=causes, x=valeurs, orientation="h", marker_color=THEME["accent2"],
        text=textes[::-1], **_LABEL,
        hovertemplate="%{y}<br>%{x} " + _t("occurrence(s)") + f" / {total}<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    fig.update_layout(bargap=0.36, margin=dict(l=10, r=120, t=24, b=34))
    return style_fig(fig, height=height,
                     xaxis_title=f'{_t("occurrence(s)")} · % {_t("cumulé")}',
                     yaxis=dict(automargin=True))


def bar_top_machines(arrets: list, machines: list, top: int = 5, height: int = 300):
    """Machines les plus problématiques : nombre de pannes, heures au survol."""
    from .kpis import hours_between
    stats = []
    for m in machines:
        siens = [a for a in arrets if a.get("machineId") == m["id"]]
        pannes = sum(1 for a in siens if a.get("type") == "Panne")
        if not pannes:
            continue
        heures = sum(hours_between(a["dateDebut"], a["dateFin"]) for a in siens)
        stats.append((m, pannes, heures))
    if not stats:
        return _empty("Ce classement apparaîtra dès qu'un arrêt de type « Panne » sera saisi.",
                      height)
    stats.sort(key=lambda s: (-s[1], -s[2]))
    stats = stats[:top][::-1]
    fig = go.Figure(go.Bar(
        y=[m["nom"] for m, _, _ in stats], x=[p for _, p, _ in stats], orientation="h",
        marker_color=[dep(m["departementId"])["couleur"] for m, _, _ in stats],
        text=[f'{p} {_t("panne(s)")}' for _, p, _ in stats], **_LABEL,
        customdata=[[_n(h, 1), i18n.dept_label(m["departementId"], dep(m["departementId"])["nom"])]
                    for m, _, h in stats],
        hovertemplate="%{y} · %{customdata[1]}<br>%{x} " + _t("panne(s)")
                      + "<br>%{customdata[0]} h " + _t("d'arrêt cumulé") + "<extra></extra>",
    ))
    fig.update_traces(marker=dict(cornerradius=5))
    fig.update_layout(bargap=0.36, margin=dict(l=10, r=120, t=24, b=34))
    return style_fig(fig, height=height, xaxis_title=_t("panne(s)"),
                     yaxis=dict(automargin=True))
