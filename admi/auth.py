"""Authentification simple (compte administrateur, mots de passe hachés PBKDF2).

Au premier lancement, un compte par défaut **admin / admin** est créé dans le
dossier de données. À changer en production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from .data import DATA_DIR

USERS_FILE = DATA_DIR / "users.json"


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000).hex()


def _save(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users), encoding="utf-8")


def _load() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    salt = os.urandom(16)
    users = {"admin": {"salt": salt.hex(), "hash": _hash("admin", salt)}}
    _save(users)
    return users


def verify_login(username: str, password: str) -> bool:
    u = _load().get((username or "").strip())
    if not u:
        return False
    return hmac.compare_digest(u["hash"], _hash(password or "", bytes.fromhex(u["salt"])))


def set_password(username: str, password: str) -> None:
    users = _load()
    salt = os.urandom(16)
    users[username.strip()] = {"salt": salt.hex(), "hash": _hash(password, salt)}
    _save(users)
