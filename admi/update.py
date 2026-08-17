"""Vérification de mise à jour (best-effort, hors ligne-safe).

Définissez la variable d'environnement ``ADMI_UPDATE_URL`` vers un fichier JSON :

    { "version": "1.1.0", "url": "https://exemple/telecharger" }

L'application compare avec sa version courante et, si une version plus récente
existe, affiche une bannière avec le lien. Sans cette variable, aucune requête
réseau n'est faite.
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import __version__


def _parse(v: str):
    parts = []
    for p in str(v).split("."):
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    return tuple(parts)


def check():
    """Retourne (version_courante, version_dispo, url) si mise à jour, sinon None."""
    url = os.environ.get("ADMI_UPDATE_URL")
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        latest = str(data.get("version", "")).strip()
        if latest and _parse(latest) > _parse(__version__):
            return __version__, latest, data.get("url", "")
    except Exception:
        return None
    return None
