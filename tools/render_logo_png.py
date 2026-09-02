"""Rend le logo AMI en PNG pour les e-mails (aucun client mail n'affiche un SVG).

    python tools/render_logo_png.py

Le dessin n'est pas redessiné ici : il vient de `admi.logo.logo_svg`, la source
unique. Le rendu se fait dans Chrome via Playwright, sur le fond sombre de
l'en-tête du mail, puis est écrit dans assets/ami_logo_email.png.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from admi.logo import logo_svg  # noqa: E402

FOND = "#0D1626"          # bande d'en-tête du mail
TAILLE = 96               # affiché à 48 px : x2 pour les écrans à haute densité
SORTIE = RACINE / "assets" / "ami_logo_email.png"


def main():
    from playwright.sync_api import sync_playwright

    page_html = (f'<body style="margin:0;background:{FOND};">'
                 f'<div id="logo" style="display:inline-block;line-height:0">'
                 f'{logo_svg(TAILLE, animated=False)}</div></body>')
    with sync_playwright() as p:
        navigateur = p.chromium.launch(channel="chrome", args=["--disable-dev-shm-usage"])
        page = navigateur.new_page(viewport={"width": TAILLE, "height": TAILLE})
        page.set_content(page_html)
        page.wait_for_timeout(500)
        page.locator("#logo").screenshot(path=str(SORTIE))
        navigateur.close()
    print(f"→ {SORTIE.relative_to(RACINE)} ({SORTIE.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main()
