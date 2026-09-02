"""Logo AMI — source unique.

Le dessin vit ici et nulle part ailleurs : l'application l'affiche en SVG animé,
et `tools/render_logo_png.py` en tire le PNG utilisé dans les e-mails d'alerte
(aucun client mail ne sait afficher un SVG).
"""
from __future__ import annotations

import math

NAVY = "#F2A93B"      # jaune/orangé de l'app (l'engrenage)
NAVY_D = "#8A6423"
CYAN = "#22D3EE"
CYAN2 = "#38BDF8"
GOLD = "#F5C36B"
GRAY = "#7C8AA0"


def arc_path(r, a0, a1, cx=60, cy=60) -> str:
    p0 = (cx + r * math.cos(math.radians(a0)), cy - r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1)))
    return f"M {p0[0]:.1f} {p0[1]:.1f} A {r} {r} 0 0 0 {p1[0]:.1f} {p1[1]:.1f}"


def logo_svg(size=120, animated=True) -> str:
    teeth = "".join(f'<rect x="56.7" y="4.5" width="6.6" height="13" rx="1.6" '
                    f'transform="rotate({k*30} 60 60)"/>' for k in range(12))
    ecg_pts = [(22, 60), (41, 60), (46, 60), (49, 55), (52, 60), (55, 41), (60, 81),
               (64, 49), (67, 60), (73, 60), (98, 60)]
    ecg = " ".join(f"{x},{y}" for x, y in ecg_pts)
    gray = arc_path(33, -70, -18)
    rx, ry = 60 + 32 * math.cos(math.radians(42)), 60 - 32 * math.sin(math.radians(42))
    a = (lambda css: css) if animated else (lambda css: "")
    return f'''<svg viewBox="0 0 120 120" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AMI">
      <defs><filter id="glow"><feGaussianBlur stdDeviation="1.1" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      <style>
        @keyframes spin{{to{{transform:rotate(360deg)}}}}
        @keyframes draw{{0%{{stroke-dashoffset:280}}55%{{stroke-dashoffset:0}}100%{{stroke-dashoffset:-280}}}}
        @keyframes sig{{0%,100%{{opacity:.18}}50%{{opacity:1}}}}
        @keyframes hub{{0%,100%{{opacity:1}}50%{{opacity:.55}}}}
        .gear{{transform-origin:60px 60px;{a("animation:spin 26s linear infinite;")}}}
        .sweep{{transform-origin:60px 60px;{a("animation:spin 4.6s linear infinite;")}}}
        .ecg{{stroke-dasharray:280;{a("animation:draw 2.8s linear infinite;")}}}
        .s1{{{a("animation:sig 1.7s ease-in-out infinite;")}}}
        .s2{{{a("animation:sig 1.7s ease-in-out .22s infinite;")}}}
        .s3{{{a("animation:sig 1.7s ease-in-out .44s infinite;")}}}
        .hub{{{a("animation:hub 1.7s ease-in-out infinite;")}}}
      </style>
      <g class="gear" fill="{NAVY}"><circle cx="60" cy="60" r="43.5" fill="none"
         stroke="{NAVY}" stroke-width="12"/>{teeth}</g>
      <circle cx="60" cy="60" r="37" fill="#0A1220"/>
      <circle cx="60" cy="60" r="32" fill="none" stroke="{GOLD}" stroke-width="2.4"
              stroke-dasharray="150 62" transform="rotate(-96 60 60)"/>
      <path d="{gray}" fill="none" stroke="{GRAY}" stroke-width="2.4" stroke-linecap="round"/>
      <g class="sweep"><line x1="60" y1="60" x2="{rx:.1f}" y2="{ry:.1f}"
         stroke="{CYAN}" stroke-width="2" stroke-linecap="round" filter="url(#glow)"/></g>
      <g fill="none" stroke="{CYAN2}" stroke-width="2.6" stroke-linecap="round" filter="url(#glow)">
        <path class="s1" d="{arc_path(13, 18, 66)}"/>
        <path class="s2" d="{arc_path(20, 18, 66)}"/>
        <path class="s3" d="{arc_path(27, 18, 66)}"/></g>
      <polyline class="ecg" points="{ecg}" fill="none" stroke="{CYAN}" stroke-width="2.7"
                stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>
      <circle class="hub" cx="60" cy="60" r="5.6" fill="{NAVY}" stroke="{CYAN}" stroke-width="1.4"/>
      <circle cx="60" cy="60" r="2.4" fill="{CYAN}"/>
    </svg>'''
