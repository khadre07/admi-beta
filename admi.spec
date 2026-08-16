# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller pour ADMI — exécutable autonome (macOS / Windows / Linux).

macOS  -> dist/ADMI.app        Windows -> dist/ADMI/ADMI.exe
Linux  -> dist/ADMI/ADMI       (dossier autonome)
"""
import sys as _sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Paquets dont il faut embarquer code + données + imports dynamiques.
# (app.py est exécuté par Streamlit comme un script « data » : ses imports ne
#  sont pas vus par l'analyse de launch.py, d'où la collecte explicite.)
PACKAGES = [
    "streamlit", "streamlit_calendar", "plotly", "pandas", "numpy",
    "openpyxl", "pymupdf", "docx", "reportlab", "narwhals", "altair",
    "pyarrow", "pydeck", "tornado", "watchdog", "dateutil", "pytz", "jinja2",
]
for pkg in PACKAGES:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect_all ignoré: {pkg} ({exc})")

# Métadonnées (Streamlit et d'autres lisent leur version via importlib.metadata)
for pkg in ["streamlit", "streamlit_calendar", "plotly", "pandas", "numpy",
            "altair", "pyarrow", "pydeck", "tornado", "watchdog", "openpyxl",
            "pymupdf", "packaging"]:
    try:
        datas += copy_metadata(pkg)
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] copy_metadata ignoré: {pkg} ({exc})")

# Sous-modules reportlab.graphics importés dynamiquement par admi/report.py
hiddenimports += [
    "reportlab.graphics.shapes",
    "reportlab.graphics.charts.barcharts",
    "reportlab.graphics.charts.piecharts",
    "reportlab.graphics.charts.linecharts",
    "reportlab.graphics.charts.legends",
    "reportlab.graphics.renderPDF",
]

# Code source de l'application (importé/exécuté à l'exécution, via sys.path).
datas += [
    ("app.py", "admi_app"),
    ("admi", "admi_app/admi"),
    (".streamlit", "admi_app/.streamlit"),
]

a = Analysis(
    ["launch.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PyInstaller", "pandas.tests", "numpy.tests", "numpy.random.tests",
        "matplotlib", "IPython", "pytest", "_pytest", "notebook", "sphinx",
        "reportlab.graphics.testshapes",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
# NB : PyInstaller Splash() n'est PAS supporté sur macOS — on affiche à la place
# une notification macOS au démarrage (voir launch.py), et l'écran d'accueil animé
# s'affiche dans le navigateur.
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="ADMI",
    console=False, disable_windowed_traceback=False, target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ADMI")

# Le bundle .app n'existe que sur macOS ; sur Windows/Linux, COLLECT suffit
# (dist/ADMI/ADMI.exe ou dist/ADMI/ADMI).
if _sys.platform == "darwin":
    app = BUNDLE(
        coll, name="ADMI.app", icon=None, bundle_identifier="sn.artp.admi",
        info_plist={
            "CFBundleName": "ADMI",
            "CFBundleDisplayName": "ADMI",
            "CFBundleShortVersionString": "1.0",
            "LSMinimumSystemVersion": "10.15",
            "NSHighResolutionCapable": True,
        },
    )
