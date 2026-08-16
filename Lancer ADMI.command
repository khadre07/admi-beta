#!/bin/bash
# Double-cliquez ce fichier pour lancer ADMI (une fenêtre Terminal s'ouvre avec les journaux).
cd "$(dirname "$0")"
PORT=8533

if curl -s "http://localhost:$PORT/_stcore/health" 2>/dev/null | grep -q ok; then
  open "http://localhost:$PORT"; exit 0
fi

PY=""
for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 python3; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -z "$PY" ] && { echo "Python 3 introuvable. Installez-le depuis python.org."; read -r _; exit 1; }

if [ ! -x ".venv/bin/streamlit" ]; then
  echo "→ Premier lancement : installation des composants…"
  "$PY" -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

echo "→ ADMI démarre sur http://localhost:$PORT (fermez cette fenêtre pour arrêter)"
( for i in $(seq 1 80); do curl -s "http://localhost:$PORT/_stcore/health" 2>/dev/null | grep -q ok && { open "http://localhost:$PORT"; break; }; sleep 0.5; done ) &
exec ./.venv/bin/streamlit run app.py --server.port "$PORT" --browser.gatherUsageStats false
