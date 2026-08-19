# AMI — Instructions projet & charte visuelle

> Ce fichier est lu automatiquement par Claude Code au démarrage. Il garantit
> que **la même identité visuelle est respectée sur n'importe quelle machine**.
> Ne pas s'en écarter sans demande explicite de l'utilisateur.

**AMI — Analyse de Maintenance Industrielle** : tableau de bord de maintenance
industrielle (Streamlit + Plotly), thème sombre, bilingue FR/EN, licence + rôles.

## Règle d'or
La charte vit **dans le code** — ne jamais coder « en dur » une couleur ou une
police : réutiliser les sources ci-dessous.
- Palette + template de graphiques : `admi/theme.py` (dict `THEME`, `register_template()`).
- Couleurs des départements : `admi/config.py` (`DEPARTEMENTS`, `--c-*`).
- Logo animé : `logo_svg()` / `logo_block()` dans `app.py`.
- Traductions : `admi/i18n.py` (toujours passer les libellés par `T()` / `TT()` / `TD()`).

## Palette (source : admi/theme.py → THEME)
| Rôle | Hex |
|---|---|
| Fond | `#0A1220` / `#0D1626` |
| Cartes / panneaux | `#121C2E` / `#17233A` |
| Bordures | `#243250` / `#2E3E60` |
| Texte | `#E7ECF3` · atténué `#8CA0BC` · discret `#5E7195` |
| **Accent (jaune, couleur signature)** | **`#F2A93B`** |
| Accent 2 (teal) | `#2BC7BE` |
| Succès / Danger / Warn | `#48D48A` / `#EF5B5B` / `#F2A93B` |

Départements (8) : AM `#7C83FD`, OND `#38BDF8`, PT `#FF6B6B`, CHI `#FFD166`,
SAC `#06D6A0`, SL `#22D3EE`, ADM `#F472B6`, SRV `#FB923C`.

## Typographie
- Titres / logo : **Oswald** (700, majuscules, letter-spacing léger).
- Texte courant : **Inter**. Chiffres/mono : **JetBrains Mono**.

## Logo AMI (source : `logo_svg()` dans app.py)
Engrenage **jaune `#F2A93B`** (le cercle) + éléments techniques **cyan `#22D3EE`** :
tracé ECG animé, balayage radar, ondes de signal pulsées, hub central à halo.
Wordmark **AMI** avec le « A » en cyan, « MI » en clair. Toujours réutiliser
`logo_svg(size)` / `logo_block(label)` — ne pas redessiner un autre logo.
Sous-titre officiel : **« Analyse de Maintenance Industrielle »**.

## Conventions UI
- Graphiques via `admi/charts.py` uniquement (thème sombre « admi », axes lisibles,
  modebar au survol). Chaque `st.plotly_chart` doit avoir une `key` unique (voir `plot()`).
- Cartes KPI : `kpi_card()` ; titres de section : `section_title()`.
- Écrans licence / connexion / démarrage : logo animé + fond sombre (déjà en place).
- Tout texte visible passe par `T(...)` (FR par défaut, EN via le sélecteur de langue).

## Stack & données
Python 3.11+, Streamlit + Plotly + pandas + SQLAlchemy (SQLite par défaut,
PostgreSQL via `DATABASE_URL`) + reportlab + pymupdf + python-docx + streamlit-calendar.
Données persistées hors du code (dossier utilisateur ou `ADMI_DATA_DIR`).

## Reprise sur une autre machine
```bash
git clone https://github.com/khadre07/admi-beta.git
cd admi-beta
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Le rendu (logo, couleurs, thème) est identique : tout est versionné dans ce dépôt.
Voir aussi `README.md`, `DEPLOIEMENT.md`, `SIGNATURE.md`.
