# ADMI — image serveur (Linux). Sert le tableau de bord Streamlit sur le réseau.
FROM python:3.13-slim

# Dépendances système utiles (fontconfig pour un rendu de texte propre)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6 fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY admi ./admi
COPY app.py .
COPY .streamlit ./.streamlit

# Données persistées hors de l'image (licence, comptes, saisies)
ENV ADMI_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8501
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
