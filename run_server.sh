#!/usr/bin/env bash
# Lance AMI en serveur partagé sur le réseau local (multi-utilisateurs).
#
# Base de données : définissez DATABASE_URL vers PostgreSQL pour un vrai
# multi-utilisateur (écritures simultanées fiables). Sans DATABASE_URL, AMI
# utilise un fichier SQLite local (concurrence limitée).
#
#   export DATABASE_URL="postgresql://admi:motdepasse@localhost:5432/admi"
#   export ADMI_DATA_DIR="/var/lib/admi"      # dossier de données/sauvegardes
#   ./run_server.sh
#
# L'application est alors accessible depuis les autres postes du réseau sur
#   http://<ip-du-serveur>:8501
set -euo pipefail
cd "$(dirname "$0")"

HOST="${ADMI_HOST:-0.0.0.0}"
PORT="${ADMI_PORT:-8501}"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec streamlit run app.py \
  --server.address "$HOST" \
  --server.port "$PORT" \
  --server.headless true
