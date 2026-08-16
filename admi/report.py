"""Génération de rapports complets ADMI.

HTML autonome (graphiques Plotly interactifs) et PDF (graphiques dessinés
nativement avec reportlab). Les deux rapports partagent exactement les mêmes
sections et les mêmes 6 graphiques, pour un contenu cohérent.
"""
from __future__ import annotations

import io
from datetime import date

from . import charts, kpis
from .config import DEPARTEMENTS, THEME, dep


def _fmt(n, dec=0):
    s = f"{float(n or 0):,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", " ")


def _money(n):
    return _fmt(n, 0) + " FCFA"


def _period_label(periode, annee, mois):
    from .config import MOIS
    return f"{MOIS[mois]} {annee}" if periode == "mois" else f"Année {annee}"


def _gather(db, periode, annee, mois, dept):
    k = kpis.compute_kpis(db, periode, annee, mois, dept)
    start, end = kpis.period_bounds(periode, annee, mois)
    arrets = kpis.filter_arrets(db, start, end, dept)
    intervs = kpis.filter_interventions(db, start, end, dept)
    energie = kpis.filter_energie(db, periode, annee, mois, dept)
    return k, arrets, intervs, energie


def _kpi_pairs(k):
    return [
        ("Disponibilité", f'{_fmt(k["disponibilite"],1)} %'),
        ("MTBF", f'{_fmt(k["mtbf"],1)} h' if k["mtbf"] is not None else "—"),
        ("MTTR", f'{_fmt(k["mttr"],1)} h' if k["mttr"] is not None else "—"),
        ("Coût maintenance", _money(k["coutMaint"])),
        ("Temps d'arrêt", f'{_fmt(k["tempsArretH"],1)} h'),
        ("Énergie", f'{_fmt(k["kwh"])} kWh'),
        ("Coût énergie", _money(k["coutEnergie"])),
        ("Puissance installée", f'{_fmt(k["puissanceInstallee"])} kW'),
    ]


def _dept_rows(arrets, intervs, energie):
    ad = kpis.arrets_by_dept(arrets)
    cd = kpis.cout_by_dept(intervs)
    ed = kpis.energie_by_dept(energie)
    return [(d, ad.get(d["id"], 0), cd.get(d["id"], 0), ed.get(d["id"], 0)) for d in DEPARTEMENTS]


# ===========================================================================
# Rapport HTML autonome (Plotly interactif)
# ===========================================================================
def build_html_report(db, periode, annee, mois, dept) -> bytes:
    k, arrets, intervs, energie = _gather(db, periode, annee, mois, dept)

    figs = [
        ("Disponibilité", charts.gauge_disponibilite(k["disponibilite"])),
        ("Temps d'arrêt par département (h)", charts.bar_arrets_by_dept(kpis.arrets_by_dept(arrets))),
        ("Répartition du coût de maintenance", charts.donut_cout_by_dept(kpis.cout_by_dept(intervs))),
        ("Énergie par département (kWh)", charts.bar_energie_by_dept(kpis.energie_by_dept(energie))),
        ("Interventions préventif / correctif", charts.grouped_interv_prevcorr(kpis.interv_prev_corr_by_dept(intervs))),
        ("Tendance de disponibilité (%)", charts.line_trend(kpis.yearly_trend(db, dept), "disponibilite")),
    ]
    chart_html = []
    for i, (t, fig) in enumerate(figs):
        div = fig.to_html(include_plotlyjs=("inline" if i == 0 else False), full_html=False,
                          config={"displayModeBar": False})
        chart_html.append(f'<div class="card"><div class="ct">{t}</div>{div}</div>')

    dept_name = "Tous les départements" if dept == "all" else dep(dept)["nom"]
    kpi_html = "".join(f'<div class="kpi"><div class="lab">{lab}</div><div class="val">{val}</div></div>'
                       for lab, val in _kpi_pairs(k))
    rows = "".join(
        f"<tr><td><b style='color:{d['couleur']}'>{d['nom']}</b></td>"
        f"<td>{_fmt(a,1)}</td><td>{_money(c)}</td><td>{_fmt(e)}</td></tr>"
        for d, a, c, e in _dept_rows(arrets, intervs, energie))
    table_html = ("<table><thead><tr><th>Département</th><th>Arrêt (h)</th>"
                  "<th>Coût maintenance</th><th>Énergie (kWh)</th></tr></thead>"
                  f"<tbody>{rows}</tbody></table>")

    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport ADMI — {_period_label(periode, annee, mois)}</title>
<style>
  body{{margin:0;background:{THEME['bg']};color:{THEME['text']};font-family:'Segoe UI',Arial,sans-serif;padding:32px;}}
  .head{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid {THEME['accent']};padding-bottom:14px;margin-bottom:22px;}}
  .brand{{font-size:34px;font-weight:800;letter-spacing:.04em;}} .brand .d{{color:{THEME['accent']};}}
  .meta{{text-align:right;color:{THEME['muted']};font-size:13px;line-height:1.6;}}
  .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px;}}
  .kpi{{background:{THEME['panel']};border:1px solid {THEME['border']};border-radius:10px;padding:14px 16px;}}
  .kpi .lab{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:{THEME['muted']};}}
  .kpi .val{{font-size:22px;font-weight:700;margin-top:6px;}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
  .card{{background:{THEME['panel']};border:1px solid {THEME['border']};border-radius:12px;padding:14px 16px;margin-bottom:16px;}}
  .ct{{font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:13px;margin-bottom:8px;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;}}
  th{{text-align:left;color:{THEME['muted']};font-size:11px;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid {THEME['border']};}}
  td{{padding:8px 10px;border-bottom:1px solid {THEME['border']};}}
  .foot{{margin-top:20px;color:{THEME['muted2']};font-size:11px;text-align:center;}}
  @media print{{ body{{background:#fff;color:#111;}} .card,.kpi{{border-color:#ccc;background:#fff;}} }}
</style></head><body>
  <div class="head">
    <div><div class="brand"><span class="d">●</span> ADMI</div>
      <div style="color:{THEME['muted']};font-size:13px">Rapport de maintenance industrielle</div></div>
    <div class="meta"><b>Période :</b> {_period_label(periode, annee, mois)}<br>
      <b>Périmètre :</b> {dept_name}<br><b>Généré le :</b> {date.today().strftime('%d/%m/%Y')}</div>
  </div>
  <div class="kpis">{kpi_html}</div>
  <div class="card"><div class="ct">Synthèse par département</div>{table_html}</div>
  <div class="grid2">{''.join(chart_html[:4])}</div>
  <div class="grid2">{''.join(chart_html[4:])}</div>
  <div class="foot">ADMI — Analyse des Données de Maintenance Industrielle · rapport généré automatiquement</div>
</body></html>"""
    return html.encode("utf-8")


# ===========================================================================
# Rapport PDF (reportlab) — mêmes sections + graphiques natifs
# ===========================================================================
def _rl_color(hexstr):
    from reportlab.lib import colors
    return colors.HexColor(hexstr)


def _bar_drawing(labels, values, hexcolors, width=460, height=175, ytitle=""):
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y = 34, 26
    bc.width, bc.height = width - 54, height - 46
    bc.data = [list(values)]
    bc.categoryAxis.categoryNames = labels
    bc.valueAxis.valueMin = 0
    bc.barWidth = 10
    bc.groupSpacing = 8
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.labels.fontSize = 8
    for i, c in enumerate(hexcolors):
        bc.bars[(0, i)].fillColor = _rl_color(c)
        bc.bars[(0, i)].strokeColor = None
    d.add(bc)
    return d


def _grouped_bar_drawing(labels, series1, series2, c1, c2, width=460, height=175):
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y = 34, 26
    bc.width, bc.height = width - 54, height - 52
    bc.data = [list(series1), list(series2)]
    bc.categoryAxis.categoryNames = labels
    bc.valueAxis.valueMin = 0
    bc.categoryAxis.labels.fontSize = 8
    bc.valueAxis.labels.fontSize = 8
    bc.bars[0].fillColor = _rl_color(c1)
    bc.bars[1].fillColor = _rl_color(c2)
    d.add(bc)
    leg = Legend()
    leg.x, leg.y = 40, height - 6
    leg.fontSize = 8
    leg.alignment = "right"
    leg.columnMaximum = 1
    leg.colorNamePairs = [(_rl_color(c1), "Préventif"), (_rl_color(c2), "Correctif / autre")]
    d.add(leg)
    return d


def _pie_drawing(labels, values, hexcolors, width=460, height=185):
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.legends import Legend
    d = Drawing(width, height)
    if not values:
        return d
    pie = Pie()
    pie.x, pie.y = 18, 16
    pie.width, pie.height = height - 30, height - 30
    pie.data = list(values)
    pie.labels = None
    pie.slices.strokeColor = _rl_color("#FFFFFF")
    pie.slices.strokeWidth = 0.5
    for i, c in enumerate(hexcolors):
        pie.slices[i].fillColor = _rl_color(c)
    d.add(pie)
    leg = Legend()
    leg.x, leg.y = height, height - 24
    leg.fontSize = 8
    leg.dxTextSpace = 5
    leg.deltay = 12
    leg.colorNamePairs = [(_rl_color(hexcolors[i]), labels[i]) for i in range(len(labels))]
    d.add(leg)
    return d


def _line_drawing(years, values, width=460, height=175):
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    d = Drawing(width, height)
    lc = HorizontalLineChart()
    lc.x, lc.y = 34, 26
    lc.width, lc.height = width - 54, height - 46
    lc.data = [list(values)]
    lc.categoryAxis.categoryNames = [str(y) for y in years]
    lc.categoryAxis.labels.fontSize = 8
    lc.valueAxis.labels.fontSize = 8
    lc.lines[0].strokeColor = _rl_color(THEME["accent"])
    lc.lines[0].strokeWidth = 2
    lc.lines.symbol = None
    d.add(lc)
    return d


def build_intervention_report(db, interv) -> bytes:
    """Rapport PDF pour UNE intervention (fiche imprimable)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    accent = _rl_color(THEME["accent"])
    dark = _rl_color("#1A2438")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=dark, fontSize=20)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=dark, spaceBefore=6)
    small = ParagraphStyle("sm", parent=styles["Normal"], textColor=colors.grey, fontSize=9)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)

    d = dep(interv["departementId"])
    pieces = interv.get("pieces") or []
    cout_pieces = sum((float(p.get("cout") or 0) * float(p.get("qte") or 1)) for p in pieces)
    cout_mo = float(interv.get("coutMainOeuvre") or 0)
    total = cout_pieces + cout_mo

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title="Rapport d'intervention")
    story = [
        Paragraph("ADMI — Rapport d'intervention", h1),
        Paragraph(f"Généré le {date.today().strftime('%d/%m/%Y')}", small),
        Spacer(1, 8 * mm),
    ]

    info = [
        ["Date", interv.get("date", "—"), "Type", interv.get("type", "—")],
        ["Machine", db.machine_name(interv["machineId"]), "Département", d["nom"]],
        ["Technicien(s)", interv.get("technicien", "—") or "—", "Durée",
         f'{_fmt(interv.get("duree", 0),1)} h'],
    ]
    it = Table(info, colWidths=[30 * mm, 62 * mm, 30 * mm, 52 * mm])
    it.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), dark), ("BACKGROUND", (2, 0), (2, -1), dark),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white), ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [it, Spacer(1, 6 * mm)]

    story.append(Paragraph("Travaux réalisés", h2))
    story.append(Paragraph((interv.get("description") or "—").replace("\n", "<br/>"), body))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Pièces changées / réparées", h2))
    prows = [["Désignation", "Qté", "Coût unit.", "Total"]]
    for p in pieces:
        q = float(p.get("qte") or 1)
        cu = float(p.get("cout") or 0)
        prows.append([p.get("designation", "—"), _fmt(q), _money(cu), _money(cu * q)])
    if not pieces:
        prows.append(["Aucune pièce", "", "", ""])
    pt = Table(prows, colWidths=[86 * mm, 20 * mm, 34 * mm, 34 * mm])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), dark), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
    story += [pt, Spacer(1, 6 * mm)]

    totals = [["Coût pièces", _money(cout_pieces)],
              ["Coût main d'œuvre", _money(cout_mo)],
              ["COÛT TOTAL", _money(total)]]
    tt = Table(totals, colWidths=[120 * mm, 54 * mm])
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2), accent), ("LINEABOVE", (0, 2), (-1, 2), 0.6, dark),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(tt)

    doc.build(story)
    return buf.getvalue()


def build_pdf_report(db, periode, annee, mois, dept) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    k, arrets, intervs, energie = _gather(db, periode, annee, mois, dept)
    accent = _rl_color(THEME["accent"])
    dark = _rl_color("#1A2438")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=dark, fontSize=22)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=dark, spaceBefore=6)
    h3 = ParagraphStyle("h3", parent=styles["Heading4"], textColor=colors.HexColor("#334155"), spaceBefore=4)
    small = ParagraphStyle("sm", parent=styles["Normal"], textColor=colors.grey, fontSize=9)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=14 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="Rapport ADMI")
    dept_name = "Tous les départements" if dept == "all" else dep(dept)["nom"]
    story = [
        Paragraph("ADMI — Rapport de maintenance industrielle", h1),
        Paragraph(f"Période : <b>{_period_label(periode, annee, mois)}</b> &nbsp;·&nbsp; "
                  f"Périmètre : <b>{dept_name}</b> &nbsp;·&nbsp; "
                  f"Généré le {date.today().strftime('%d/%m/%Y')}", small),
        Spacer(1, 8 * mm),
    ]

    # KPI (mêmes 8 que le HTML)
    pairs = _kpi_pairs(k)
    kpi_data = [[pairs[0][0], pairs[0][1], pairs[1][0], pairs[1][1]],
                [pairs[2][0], pairs[2][1], pairs[3][0], pairs[3][1]],
                [pairs[4][0], pairs[4][1], pairs[5][0], pairs[5][1]],
                [pairs[6][0], pairs[6][1], pairs[7][0], pairs[7][1]]]
    kt = Table(kpi_data, colWidths=[38 * mm, 46 * mm, 38 * mm, 46 * mm])
    kt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), dark), ("BACKGROUND", (2, 0), (2, -1), dark),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white), ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
        ("TEXTCOLOR", (1, 0), (1, -1), accent), ("TEXTCOLOR", (3, 0), (3, -1), accent),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story += [Paragraph("Indicateurs clés", h2), Spacer(1, 2 * mm), kt, Spacer(1, 6 * mm)]

    # Synthèse par département
    drows = _dept_rows(arrets, intervs, energie)
    trows = [["Département", "Arrêt (h)", "Coût maintenance", "Énergie (kWh)"]]
    for d, a, c, e in drows:
        trows.append([d["nom"], _fmt(a, 1), _money(c), _fmt(e)])
    dt = Table(trows, colWidths=[62 * mm, 28 * mm, 44 * mm, 34 * mm])
    dt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), dark), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [Paragraph("Synthèse par département", h2), Spacer(1, 2 * mm), dt, Spacer(1, 6 * mm)]

    # --- Graphiques (mêmes que le HTML) ---
    story.append(Paragraph("Graphiques", h2))
    courts = [d["court"] for d in DEPARTEMENTS]
    cols = [d["couleur"] for d in DEPARTEMENTS]

    # Disponibilité (camembert dispo / arrêt)
    story.append(Paragraph("Disponibilité", h3))
    story.append(_pie_drawing(["Disponible", "Temps d'arrêt"],
                              [round(k["disponibilite"], 1), round(100 - k["disponibilite"], 1)],
                              [THEME["success"], THEME["danger"]]))
    story.append(Spacer(1, 3 * mm))

    ad = kpis.arrets_by_dept(arrets)
    story.append(Paragraph("Temps d'arrêt par département (h)", h3))
    story.append(_bar_drawing(courts, [round(ad.get(d["id"], 0), 1) for d in DEPARTEMENTS], cols))
    story.append(Spacer(1, 3 * mm))

    cd = kpis.cout_by_dept(intervs)
    cd_items = [(d, cd.get(d["id"], 0)) for d in DEPARTEMENTS if cd.get(d["id"], 0) > 0]
    story.append(Paragraph("Répartition du coût de maintenance", h3))
    if cd_items:
        story.append(_pie_drawing([d["nom"] for d, _ in cd_items], [v for _, v in cd_items],
                                  [d["couleur"] for d, _ in cd_items]))
    else:
        story.append(Paragraph("Aucune donnée de coût sur la période.", small))
    story.append(Spacer(1, 3 * mm))

    ed = kpis.energie_by_dept(energie)
    story.append(Paragraph("Énergie par département (kWh)", h3))
    story.append(_bar_drawing(courts, [round(ed.get(d["id"], 0)) for d in DEPARTEMENTS], cols))
    story.append(Spacer(1, 3 * mm))

    pc = kpis.interv_prev_corr_by_dept(intervs)
    story.append(Paragraph("Interventions préventif / correctif", h3))
    story.append(_grouped_bar_drawing(courts, [pc.get(d["id"], (0, 0))[0] for d in DEPARTEMENTS],
                                      [pc.get(d["id"], (0, 0))[1] for d in DEPARTEMENTS],
                                      THEME["success"], THEME["danger"]))
    story.append(Spacer(1, 3 * mm))

    trend = kpis.yearly_trend(db, dept)
    story.append(Paragraph("Tendance de disponibilité (%)", h3))
    story.append(_line_drawing([r["year"] for r in trend], [round(r["disponibilite"], 1) for r in trend]))

    doc.build(story)
    return buf.getvalue()
