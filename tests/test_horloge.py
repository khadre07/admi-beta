"""Horloge live de l'en-tête (étape D).

Elle se met à jour dans le navigateur, sans rerun Streamlit : le bloc rendu doit
donc porter son propre minuteur et rester lisible dans la charte sombre.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.theme import THEME, live_clock_html


def test_the_clock_ticks_every_second_in_the_browser():
    html = live_clock_html("fr")
    assert "setInterval" in html
    assert re.search(r"setInterval\([^)]*,\s*1000\s*\)", html), \
        "le rafraîchissement doit se faire chaque seconde côté navigateur"


def test_the_clock_shows_the_time_and_the_long_date():
    html = live_clock_html("fr")
    assert "toLocaleTimeString" in html and "toLocaleDateString" in html
    assert "weekday" in html and "month" in html, "date longue comme dans le HTML d'origine"


def test_the_clock_is_never_hidden_by_its_own_width():
    """Le bloc vit dans une iframe large comme sa colonne (~270 px) : une media
    query sur la largeur, comme dans le HTML d'origine, le masquerait toujours."""
    assert "display:none" not in live_clock_html("fr").replace(" ", "")


def test_the_clock_follows_the_selected_language():
    assert "'fr-FR'" in live_clock_html("fr")
    assert "'en-GB'" in live_clock_html("en")
    assert "'fr-FR'" not in live_clock_html("en")


def test_the_header_carries_the_clock(app):
    """L'horloge est rendue dans l'en-tête, sur toutes les sections."""
    assert app.get("iframe"), "l'en-tête doit embarquer l'horloge live"

    app.sidebar.radio[0].set_value("Machines & Puissance").run()
    assert app.get("iframe"), "l'horloge suit le changement de section"
    assert not app.exception, [str(e.value) for e in app.exception]


def test_the_clock_wears_the_charter_colours():
    html = live_clock_html("fr")
    assert THEME["accent"] in html, "l'heure porte la couleur signature"
    assert THEME["muted"] in html or THEME["muted2"] in html
    hexes = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", html)}
    assert hexes <= {v.upper() for v in THEME.values() if isinstance(v, str)}, \
        f"couleurs codées en dur hors charte : {hexes}"
