"""Lisibilité des graphiques (étape E).

Les règles vérifiées ici viennent du skill dataviz : un seul axe, l'identité
portée par le texte et non par la couleur seule, des nombres au format français,
un écart entre les aplats voisins, et des états vides qui disent quoi faire.
"""
import sys
from pathlib import Path

import plotly.io as pio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import charts
from admi.config import THEME


def _json(fig):
    return fig.to_plotly_json()


def _traces(fig):
    return _json(fig)["data"]


# --- format des nombres ----------------------------------------------------
def test_the_template_formats_numbers_the_french_way():
    """1 234,5 et non 1,234.5 — l'app est française."""
    assert pio.templates["admi"].layout.separators == ", "


def test_numbers_are_formatted_in_one_place():
    """Le même formatage sert aux graphiques, aux tableaux et aux rapports."""
    from admi.i18n import fmt_num
    assert fmt_num(12345.67, 1) == "12 345,7"
    assert fmt_num(0) == "0" and fmt_num(None) == "0"


# --- étiquettes directes ---------------------------------------------------
def test_bars_carry_their_own_value():
    fig = charts.bar_arrets_by_dept({"am": 12.5, "ond": 4})
    bar = _traces(fig)[0]
    assert bar.get("text"), "chaque barre porte sa valeur, la couleur ne fait que confirmer"
    assert bar.get("textposition") == "outside"
    assert bar["textfont"]["color"] in (THEME["text"], THEME["muted"]), \
        "le texte porte l'encre du thème, jamais la couleur de la série"


def test_the_energy_donut_labels_its_slices_outside():
    fig = charts.pie_energie_repartition({"am": 12400, "ond": 3000, "pt": 200})
    part = _traces(fig)[0]
    assert part.get("textposition") == "outside"
    assert "AM" in part["text"][0] and "12 400" in part["text"][0], \
        "la part porte son département et sa valeur, pas seulement une couleur de légende"
    assert part["text"][-1] == "", "sous 4 %, pas d'étiquette : elle chevaucherait ses voisines"


# --- écart entre aplats voisins -------------------------------------------
def test_stacked_segments_are_separated_by_the_panel_colour():
    energie = [{"departementId": "am", "mois": i, "kwh": 100} for i in range(12)]
    energie += [{"departementId": "ond", "mois": i, "kwh": 60} for i in range(12)]
    for trace in _traces(charts.stacked_energie_mensuelle(energie, "all")):
        ligne = trace["marker"].get("line", {})
        assert ligne.get("width") == 2 and ligne.get("color") == THEME["panel"]


def test_adjacent_bars_keep_a_gap():
    fig = charts.grouped_interv_prevcorr({"am": (3, 2), "ond": (1, 4)})
    layout = _json(fig)["layout"]
    assert layout.get("bargroupgap", 0) > 0


# --- repère de cible sur les jauges ---------------------------------------
def test_the_gauge_shows_the_target_when_one_is_set():
    sans = charts.gauge_disponibilite(96.3)
    avec = charts.gauge_disponibilite(96.3, cible=90)
    assert len(_traces(avec)) == len(_traces(sans)) + 1, "un repère de cible s'ajoute à l'anneau"
    assert any("90" in (a.get("text") or "") for a in _json(avec)["layout"]["annotations"]), \
        "la valeur de la cible est écrite, pas seulement dessinée"


# --- Pareto : un seul axe --------------------------------------------------
def _arret(cause):
    return {"cause": cause, "dateDebut": "2026-01-01T08:00", "dateFin": "2026-01-01T10:00",
            "machineId": "m1", "departementId": "am", "type": "Panne"}


def test_the_pareto_ranks_causes_and_keeps_a_single_axis():
    arrets = [_arret("Roulement HS")] * 3 + [_arret("Courroie")] * 2 + [_arret("Surchauffe")]
    fig = charts.pareto_causes(arrets)
    layout = _json(fig)["layout"]
    assert "yaxis2" not in layout and "xaxis2" not in layout, \
        "deux échelles sur un même graphique : l'anti-pattern n°1"
    assert len(_traces(fig)) == 1

    trace = _traces(fig)[0]
    assert list(trace["y"]) == ["Surchauffe", "Courroie", "Roulement HS"], \
        "les causes sont classées, la plus fréquente en tête"
    assert "50" in trace["text"][-1] and "100" in trace["text"][0], \
        "le cumul est écrit sur la barre au lieu d'une seconde échelle"


def test_the_pareto_names_the_unfilled_cause():
    fig = charts.pareto_causes([_arret(""), _arret("")])
    assert "Non renseigné" in list(_traces(fig)[0]["y"])[0]


def test_the_pareto_says_what_to_do_when_there_is_nothing():
    fig = charts.pareto_causes([])
    textes = " ".join(a.get("text", "") for a in _json(fig)["layout"]["annotations"])
    assert "cause" in textes.lower(), "un état vide dit quoi faire, il ne constate pas"


# --- Top 5 des machines ----------------------------------------------------
def test_the_worst_machines_are_ranked_by_breakdowns():
    machines = [{"id": "m1", "nom": "Presse 1", "departementId": "am"},
                {"id": "m2", "nom": "Four 2", "departementId": "ond"}]
    arrets = [{**_arret("x"), "machineId": "m2"}] * 3 + [{**_arret("x"), "machineId": "m1"}]
    trace = _traces(charts.bar_top_machines(arrets, machines))[0]
    assert list(trace["y"]) == ["Presse 1", "Four 2"]
    assert trace.get("text"), "le nombre de pannes est écrit sur la barre"
