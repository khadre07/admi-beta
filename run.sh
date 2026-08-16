#!/usr/bin/env bash
# Lance ADMI (installe les dépendances au premier lancement).
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "→ Création de l'environnement virtuel..."
  python3 -m venv .venv
fi

echo "→ Installation / mise à jour des dépendances..."
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

echo "→ Lancement d'ADMI sur http://localhost:8501"
./.venv/bin/streamlit run app.py
