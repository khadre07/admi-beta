"""Authentification & rôles ADMI (mots de passe hachés PBKDF2).

Rôles :
  - ``admin``    : tout (données, réglages, gestion des utilisateurs)
  - ``operator`` : saisie des données (pas de réglages ni gestion des comptes)
  - ``viewer``   : lecture seule

Au premier lancement, un compte **admin / admin** (rôle admin) est créé dans le
dossier de données. À changer en production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from .data import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"
ROLES = ["admin", "operator", "viewer"]


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000).hex()


_SETTINGS_KEY = "users"


def _save(users: dict) -> None:
    """Écrit les comptes dans la base. Les erreurs remontent — pas de fallback
    silencieux : si la révocation d'un compte échoue, l'appelant doit le savoir.
    """
    from . import db
    db.set_setting(_SETTINGS_KEY, users)


def _read_users_from_db() -> dict | None:
    """Lit la ligne `users` depuis la base. Retourne None si la ligne n'existe
    pas (1er démarrage). Les erreurs de connexion/BDD **remontent** : on ne
    confond jamais « DB en panne » avec « 1er démarrage » (sinon on recréerait
    admin/admin par-dessus les vrais comptes).
    """
    from . import db
    s = db.get_settings()
    u = s.get(_SETTINGS_KEY)
    if isinstance(u, dict) and u:
        return u
    return None


def _load_legacy_file() -> dict | None:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _mark_legacy_migrated() -> None:
    """Renomme users.json en users.json.migrated pour qu'il ne soit plus rechargé."""
    if USERS_FILE.exists():
        try:
            USERS_FILE.rename(USERS_FILE.with_suffix(USERS_FILE.suffix + ".migrated"))
        except Exception:
            pass


def _load() -> dict:
    users = _read_users_from_db()   # peut lever ; on NE ré-initialise pas en silence

    if users is None:
        # 1er démarrage (DB OK mais aucune ligne users) : migre l'éventuel
        # fichier local, sinon crée admin/admin.
        legacy = _load_legacy_file()
        if legacy is not None:
            _save(legacy)
            _mark_legacy_migrated()
            return legacy
        salt = os.urandom(16)
        users = {"admin": {"salt": salt.hex(), "hash": _hash("admin", salt), "role": "admin"}}
        _save(users)
        return users

    # DB OK et une ligne existe : migration des rôles le cas échéant, puis renvoi.
    changed = False
    for u in users.values():
        if "role" not in u:
            u["role"] = "admin"
            changed = True
    if changed:
        _save(users)
    _mark_legacy_migrated()
    return users


def verify_login(username: str, password: str):
    """Retourne {'username', 'role'} si OK, sinon None."""
    u = _load().get((username or "").strip())
    if not u:
        return None
    if hmac.compare_digest(u["hash"], _hash(password or "", bytes.fromhex(u["salt"]))):
        return {"username": username.strip(), "role": u.get("role", "viewer")}
    return None


def list_users() -> dict:
    """Retourne {username: role}."""
    return {name: u.get("role", "viewer") for name, u in _load().items()}


def create_user(username: str, password: str, role: str = "viewer") -> tuple[bool, str]:
    username = (username or "").strip()
    if not username:
        return False, "Identifiant requis."
    if not password:
        return False, "Mot de passe requis."
    if role not in ROLES:
        role = "viewer"
    users = _load()
    if username in users:
        return False, "Cet identifiant existe déjà."
    salt = os.urandom(16)
    users[username] = {"salt": salt.hex(), "hash": _hash(password, salt), "role": role}
    _save(users)
    return True, "Utilisateur créé."


def set_password(username: str, password: str) -> None:
    users = _load()
    u = users.get(username.strip())
    salt = os.urandom(16)
    entry = {"salt": salt.hex(), "hash": _hash(password, salt), "role": (u or {}).get("role", "viewer")}
    users[username.strip()] = entry
    _save(users)


def set_role(username: str, role: str) -> tuple[bool, str]:
    if role not in ROLES:
        return False, "Rôle invalide."
    users = _load()
    if username not in users:
        return False, "Utilisateur introuvable."
    if users[username].get("role") == "admin" and role != "admin" and _count_admins(users) <= 1:
        return False, "Impossible de rétrograder le dernier administrateur."
    users[username]["role"] = role
    _save(users)
    return True, "Rôle mis à jour."


def delete_user(username: str) -> tuple[bool, str]:
    users = _load()
    if username not in users:
        return False, "Utilisateur introuvable."
    if users[username].get("role") == "admin" and _count_admins(users) <= 1:
        return False, "Impossible de supprimer le dernier administrateur."
    del users[username]
    _save(users)
    return True, "Utilisateur supprimé."


def _count_admins(users: dict) -> int:
    return sum(1 for u in users.values() if u.get("role") == "admin")


# ---------------------------------------------------------------------------
# Jetons de session (persistance à travers les rafraîchissements de page)
# ---------------------------------------------------------------------------
#
# Streamlit perd `st.session_state` à chaque reload. Pour éviter que le client
# soit déconnecté quand il fait F5, on écrit un jeton signé HMAC dans l'URL
# (`?tok=…`). Au prochain chargement, l'app relit le jeton, vérifie la signature
# et restaure la session. Le jeton expire au bout de 7 jours.
#
# ⚠️ Compromis : ce jeton est dans l'URL ; partager le lien équivaut à partager
# la session. Acceptable pour une beta à 5 utilisateurs de confiance ; en prod
# on bougerait vers un cookie HttpOnly.
import base64 as _b64
import time as _time

_SESSION_TTL = 7 * 24 * 3600


def _session_secret() -> bytes | None:
    """Clé HMAC pour signer les jetons de session.

    Ordre de résolution :
      1. ADMI_SESSION_SECRET (env ou st.secrets) — recommandé en prod.
      2. Dérivée via SHA-256 de la clé licence (séparation cryptographique :
         compromettre l'une ne compromet pas l'autre).
      3. **None** si on est encore sur la clé licence par défaut (hardcodée) —
         dans ce cas on refuse de signer / lire des jetons (fail-closed).

    Jamais de fallback vers une constante connue.
    """
    direct = os.environ.get("ADMI_SESSION_SECRET")
    if not direct:
        try:
            import streamlit as st  # type: ignore
            val = st.secrets.get("ADMI_SESSION_SECRET") if hasattr(st, "secrets") else None
            if val:
                direct = str(val)
        except Exception:
            pass
    if direct:
        return direct.encode("utf-8") if isinstance(direct, str) else direct

    try:
        from . import license as _lic
    except Exception:
        return None
    base = getattr(_lic, "_SECRET", None)
    default = getattr(_lic, "_DEFAULT_SECRET", None)
    if not base or (default is not None and base == default):
        # Clé licence par défaut (hardcodée) → on refuse d'émettre un jeton :
        # sinon un attaquant lisant le code pourrait forger des sessions.
        return None
    return hashlib.sha256(base + b"|ami-session|v1").digest()


def make_session_token(username: str, role: str, ttl: int = _SESSION_TTL) -> str:
    """Retourne un jeton signé, ou "" si aucune clé de signature n'est configurée."""
    key = _session_secret()
    if not key:
        return ""
    exp = int(_time.time()) + int(ttl)
    body = json.dumps({"u": username, "r": role, "e": exp}, separators=(",", ":")).encode("utf-8")
    body_b64 = _b64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    sig = hmac.new(key, body_b64.encode("ascii"), hashlib.sha256).hexdigest()[:24]
    return f"{body_b64}.{sig}"


def read_session_token(token: str):
    """Retourne {'u','r','e'} si le jeton est signé et non expiré, sinon None.

    Le rôle (`r`) est toujours re-dérivé depuis la base au moment de la lecture :
    on ne fait pas confiance au rôle gelé dans le jeton — sinon un admin
    rétrogradé garderait ses privilèges jusqu'à expiration (7 jours).
    """
    if not token or "." not in token:
        return None
    key = _session_secret()
    if not key:
        return None
    try:
        body_b64, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(key, body_b64.encode("ascii"), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        pad = "=" * ((4 - len(body_b64) % 4) % 4)
        payload = json.loads(_b64.urlsafe_b64decode(body_b64 + pad).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("e", 0)) < _time.time():
        return None
    # Re-dérive le rôle depuis la source de vérité : si l'admin a supprimé le
    # compte OU changé son rôle, le jeton reflète immédiatement l'état courant.
    try:
        users = _load()
    except Exception:
        return None
    u = users.get(payload.get("u"))
    if not u:
        return None
    payload["r"] = u.get("role", "viewer")
    return payload
