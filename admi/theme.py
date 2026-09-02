"""Thème sombre ADMI pour Streamlit et Plotly."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from .config import THEME

# ---------------------------------------------------------------------------
# CSS injecté dans l'app Streamlit (reproduit la charte ADMI)
# ---------------------------------------------------------------------------
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

.stApp {{
  background:
    radial-gradient(1200px 700px at 100% -10%, #14233d 0%, transparent 60%),
    radial-gradient(1000px 600px at -10% 110%, #12203a 0%, transparent 55%),
    {THEME['bg']};
  color: {THEME['text']};
  font-family: 'Inter', sans-serif;
}}
h1, h2, h3, .disp {{ font-family: 'Oswald', sans-serif; letter-spacing: .03em; }}
h1, h2, h3 {{ text-transform: uppercase; color: {THEME['text']}; }}

/* Sidebar */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, {THEME['bg2']}, {THEME['bg']});
  border-right: 1px solid {THEME['border']};
}}
section[data-testid="stSidebar"] * {{ color: {THEME['text']}; }}

/* En-tête de marque dans la sidebar */
.admi-brand {{ display:flex; align-items:center; gap:9px; font-family:'Oswald';
  font-weight:700; font-size:26px; letter-spacing:.06em; }}
.admi-brand .dot {{ width:12px; height:12px; background:{THEME['accent']};
  box-shadow:0 0 12px {THEME['accent']}; border-radius:3px; display:inline-block; }}
.admi-sub {{ font-size:11px; color:{THEME['muted']}; letter-spacing:.03em; margin:-4px 0 8px 22px; }}

/* Cartes KPI */
.kpi-card {{
  position:relative; overflow:hidden;
  background: linear-gradient(180deg, {THEME['panel']}, {THEME['panel2']} 140%);
  border: 1px solid {THEME['border']}; border-radius: 12px;
  padding: 16px 18px; height: 100%;
}}
.kpi-card .bar {{ position:absolute; left:0; top:0; bottom:0; width:4px; }}
.kpi-card .label {{ font-size:11px; color:{THEME['muted']}; text-transform:uppercase;
  letter-spacing:.08em; font-weight:600; }}
.kpi-card .value {{ font-family:'Oswald'; font-size:30px; margin-top:6px; color:{THEME['text']}; }}
.kpi-card .value .unit {{ font-size:13px; color:{THEME['muted']}; font-weight:400; }}
.kpi-card .delta {{ font-size:11px; color:{THEME['muted2']}; margin-top:6px; }}

/* Bandeau de section du tableau de bord */
.dash-section {{ display:flex; align-items:center; gap:12px; margin: 18px 0 10px 0; }}
.dash-section .label {{ font-family:'Oswald'; font-size:13px; letter-spacing:.12em;
  text-transform:uppercase; color:{THEME['muted']}; white-space:nowrap; }}
.dash-section .line {{ flex:1; height:1px;
  background:linear-gradient(90deg, {THEME['border_light']}, transparent); }}

/* Bandeau d'alerte stock */
.stock-alert {{ display:flex; align-items:center; gap:12px; margin-bottom:6px;
  padding:12px 16px; border-radius:12px;
  border:1px solid rgba(242,169,59,.4);
  background:linear-gradient(180deg, rgba(242,169,59,.10), {THEME['panel2']}); }}
.stock-alert .ico {{ font-size:20px; }}
.stock-alert b {{ color:{THEME['text']}; }}
.stock-alert .hint {{ color:{THEME['muted']}; font-size:12px; margin-top:2px; }}

/* Légende sous les jauges */
.gauge-foot {{ display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin-top:-4px; }}
.gauge-foot .chip {{ font-size:11px; font-weight:600; padding:3px 9px; border-radius:20px;
  background:{THEME['panel2']}; border:1px solid {THEME['border']}; }}
.gauge-foot .chip.good {{ color:{THEME['success']}; }}
.gauge-foot .chip.bad {{ color:{THEME['danger']}; }}
.gauge-foot .chip.warn {{ color:{THEME['warn']}; }}
.gauge-note {{ text-align:center; color:{THEME['muted2']}; font-size:12px; margin-top:8px; }}

/* Titres de section */
.section-title {{ font-family:'Oswald'; font-size:15px; letter-spacing:.04em;
  text-transform:uppercase; color:{THEME['text']}; margin: 6px 0 6px 0;
  display:flex; align-items:center; gap:10px; }}
.section-title .line {{ flex:1; height:1px; background:{THEME['border']}; }}

/* Tableaux Streamlit */
[data-testid="stDataFrame"] {{ border:1px solid {THEME['border']}; border-radius:10px; }}

/* Onglets */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{ color:{THEME['muted']}; }}
.stTabs [aria-selected="true"] {{ color:{THEME['accent']}; }}

/* Boutons */
.stButton > button, .stDownloadButton > button {{
  background: {THEME['panel2']}; border:1px solid {THEME['border_light']};
  color:{THEME['text']}; border-radius:7px; font-weight:600;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color:{THEME['accent']}; color:{THEME['accent']};
}}

/* on masque seulement le menu et le pied de page — surtout PAS le header,
   qui contient le bouton pour rouvrir la barre latérale une fois repliée */
#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stAppDeployButton"] {{ display: none; }}
header[data-testid="stHeader"] {{ background: transparent; }}
/* bouton d'ouverture/fermeture de la sidebar bien visible */
[data-testid="stSidebarCollapsedControl"] {{ color: {THEME['accent']}; }}
[data-testid="stSidebarCollapseButton"] button, [data-testid="collapsedControl"] {{ color: {THEME['accent']}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1400px; }}
</style>
"""


# ---------------------------------------------------------------------------
# Template Plotly sombre
# ---------------------------------------------------------------------------
def register_template() -> str:
    tmpl = go.layout.Template()
    tmpl.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color=THEME["muted"]),
        # Nombres au format français : virgule décimale, espace pour les milliers
        # (sans quoi Plotly écrit « 1,234.5 » dans une application française).
        separators=", ",
        title=dict(font=dict(family="Oswald, sans-serif", color=THEME["text"], size=15)),
        legend=dict(font=dict(color=THEME["muted"], size=11), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=56, r=18, t=34, b=44),
        colorway=[d for d in (
            "#7C83FD", "#38BDF8", "#FF6B6B", "#FFD166",
            "#06D6A0", "#22D3EE", "#F472B6", "#FB923C")],
        xaxis=dict(
            gridcolor=THEME["grid"], zerolinecolor=THEME["border_light"],
            linecolor=THEME["border_light"], showline=True, ticks="outside",
            ticklen=5, tickcolor=THEME["border_light"],
            tickfont=dict(color="#C3D0E4", size=12.5),
            title=dict(font=dict(color=THEME["text"], size=13)),
        ),
        yaxis=dict(
            gridcolor=THEME["grid"], zerolinecolor=THEME["border_light"],
            linecolor=THEME["border_light"], showline=True, ticks="outside",
            ticklen=5, tickcolor=THEME["border_light"],
            tickfont=dict(color="#C3D0E4", size=12.5),
            title=dict(font=dict(color=THEME["text"], size=13)),
        ),
        hoverlabel=dict(bgcolor=THEME["panel2"], bordercolor=THEME["border_light"],
                        font=dict(color=THEME["text"], family="Inter")),
    )
    pio.templates["admi"] = tmpl
    return "admi"


def style_fig(fig, height: int = 280, **layout):
    fig.update_layout(template="admi", height=height, **layout)
    return fig


# Enregistre le template dès l'import, pour que les graphiques (et les rapports
# générés hors application Streamlit) trouvent toujours le template « admi ».
register_template()


# ---------------------------------------------------------------------------
# Horloge live de l'en-tête (reprise du HTML d'origine : heure + date longue)
# ---------------------------------------------------------------------------
_CLOCK_LOCALES = {"fr": "fr-FR", "en": "en-GB"}


def live_clock_html(lang: str = "fr") -> str:
    """Bloc autonome pour `components.html` : il se rafraîchit dans le navigateur.

    Le minuteur vit dans la page — aucun rerun Streamlit, donc aucun recalcul des
    graphiques ni perte des filtres en cours.
    """
    locale = _CLOCK_LOCALES.get(lang, _CLOCK_LOCALES["fr"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@600&family=Inter:wght@500&family=JetBrains+Mono:wght@700&display=swap');
html, body {{ margin:0; background:transparent; }}
.live-clock {{ text-align:right; line-height:1.35; white-space:nowrap;
  font-family:'Inter', sans-serif; padding-top:6px; }}
.lc-time {{ font-family:'JetBrains Mono', monospace; font-size:16px; font-weight:700;
  color:{THEME['accent']}; letter-spacing:.03em; }}
.lc-date {{ font-size:10.5px; color:{THEME['muted']}; text-transform:capitalize; }}
</style></head><body>
<div id="liveClock" class="live-clock"></div>
<script>
function updateLiveClock() {{
  var el = document.getElementById('liveClock');
  if (!el) return;
  var now = new Date();
  var dateStr = now.toLocaleDateString('{locale}',
    {{weekday:'long', day:'numeric', month:'long', year:'numeric'}});
  var timeStr = now.toLocaleTimeString('{locale}');
  el.innerHTML = '<div class="lc-time">' + timeStr + '</div>'
               + '<div class="lc-date">' + dateStr + '</div>';
}}
updateLiveClock();
setInterval(updateLiveClock, 1000);
</script></body></html>"""
