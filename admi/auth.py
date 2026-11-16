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
