<div align="center">

# ⚙️ AMI — Analyse des Machines Industrielles

**Tableau de bord de maintenance industrielle** — indicateurs (disponibilité, MTBF, MTTR),
graphiques interactifs, planning, saisie des données et génération de rapports.

Application **Streamlit + Plotly**, thème sombre, multi‑plateforme (macOS · Windows · Linux),
avec **écran de licence**, **connexion** et **exécutable autonome**.

</div>

---

## ✨ Aperçu

| Connexion | Tableau de bord |
|---|---|
| ![Connexion](assets/login.png) | ![Dashboard](assets/dashboard.png) |

| Graphiques | Planning |
|---|---|
| ![Graphiques](assets/charts.png) | ![Planning](assets/planning.png) |

| Rapport (HTML/PDF) | Activation de licence |
|---|---|
| ![Rapport](assets/report.png) | ![Licence](assets/license.png) |

---

## 🚀 Fonctionnalités

- **Tableau de bord** — 8 KPI (disponibilité, MTBF, MTTR, coûts, énergie, puissance),
  8 graphiques Plotly interactifs et une **tendance pluriannuelle**.
- **Planning** — calendrier interactif (mois / année), création / édition / répétition.
- **Saisie complète** — ajout / modification / suppression des **machines**, **arrêts**,
  **interventions** (avec pièces, boutons ＋ / −) et **consommations énergétiques**.
- **Rapports** — rapport global **HTML autonome** (graphiques interactifs) et **PDF**
  (graphiques natifs), plus une **fiche PDF par intervention**.
- **Import / Export** — Excel, CSV, **Word (.docx)** et **PDF** (reconnaissance souple des tableaux).
- **Paramètres** — heures de travail par département (base des calculs de disponibilité).
- **Sécurité produit** — **licence** (codes générés par `licgen`) + **connexion** avec
  **rôles** (admin / operator / viewer) et **gestion des utilisateurs**.
- **Multi-utilisateurs** — données rechargées en direct depuis la base partagée.
- **Rendu soigné** — charte sombre, écran d'accueil et loaders animés (engrenages).

---

## ▶️ Démarrage rapide (développement)

Prérequis : **Python 3.11+**.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py             # http://localhost:8501
```

Au premier lancement : **licence** (générez un code, voir ci‑dessous) puis **connexion**
(`admin` / `admin` par défaut). Un jeu de **données de démo** est généré automatiquement.

---

## 🔑 Licence & connexion

Générer des codes de licence avec `licgen` :

```bash
python licgen.py                 # 1 code
python licgen.py -n 5            # 5 codes
python licgen.py --check ADMI-XXXX-XXXX-XXXX-XXXX
```

Les codes (`ADMI-XXXX-XXXX-XXXX-XXXX`) sont validés **hors ligne** (signature HMAC).
Personnalisez la clé secrète dans `admi/license.py` avant diffusion.

Connexion par défaut : **`admin` / `admin`** — à changer :
`python -c "from admi import auth; auth.set_password('admin','nouveau_mdp')"`.

---

## 🗄️ Stockage des données

Les données sont dans une **base SQLite** par défaut (`admi.db`, transactionnelle,
migre automatiquement l'ancien format JSON au premier lancement). Pour un serveur
**multi‑utilisateurs**, basculez sur **PostgreSQL** sans changer le code, via une
variable d'environnement :

```bash
export DATABASE_URL="postgresql+psycopg2://user:pwd@host:5432/admi"
pip install psycopg2-binary
```

## 📦 Déploiement multi‑plateforme

Voir **[DEPLOIEMENT.md](DEPLOIEMENT.md)** pour le détail. En résumé :

| Cible | Méthode |
|---|---|
| **macOS** | `pyinstaller admi.spec` → `dist/ADMI.app` (double‑cliquable, autonome) |
| **Windows** | sur un PC Windows : `pyinstaller admi.spec` → `dist\ADMI\ADMI.exe` |
| **Linux serveur** | **Docker** : `docker compose up -d --build` → `http://<serveur>:8501` |
| **Les 3 sans machine dédiée** | **GitHub Actions** (`.github/workflows/build.yml`) compile Windows + Linux + macOS et fournit les exécutables en artefacts |

> ⚠️ PyInstaller ne fait **pas** de compilation croisée : chaque exécutable se
> construit sur son propre système (d'où l'intérêt du build cloud GitHub Actions).

---

## 🗂️ Structure

```
admi/
  config.py     départements, couleurs, types, thème
  data.py       modèle, générateur de démo, persistance (cross‑platform)
  kpis.py       calculs (disponibilité, MTBF, MTTR, tendance…)
  db.py         couche de stockage SQLAlchemy (SQLite / PostgreSQL)
  charts.py     graphiques Plotly (thème sombre)
  report.py     rapports HTML + PDF (global et par intervention)
  io_excel.py   import/export Excel · Word · PDF
  license.py    licences (HMAC) · auth.py  connexion
  theme.py      CSS + template Plotly
app.py          interface Streamlit (login, sections, dialogues de saisie)
launch.py       point d'entrée de l'exécutable autonome
licgen.py       générateur de codes de licence (CLI)
admi.spec       recette PyInstaller (macOS/Windows/Linux)
Dockerfile      image serveur Linux
tests/          tests pytest
```

---

## ✅ Tests

```bash
python -m pytest tests/ -q
```

---

<div align="center">
<sub>ADMI — Analyse des Données de Maintenance Industrielle</sub>
</div>
