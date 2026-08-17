"""Système de licence AMI (validation hors ligne par code signé HMAC).

Un code de licence a la forme AMI-XXXX-XXXX-XXXX-XXXX. Il encode un numéro de
série aléatoire signé par une clé secrète intégrée à l'application : seuls les
codes produits par la commande `licgen` (qui connaît la clé) sont valides.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets

from .data import DATA_DIR

# Clé secrète intégrée (partagée avec licgen). Pour un vrai déploiement,
# remplacez-la par votre propre valeur et gardez-la confidentielle.
_SECRET = b"ADMI-industrial-maintenance-2026-license-signing-key-\x9f\x12\xab"
LIC_FILE = DATA_DIR / "license.json"


def _mac(payload: bytes) -> bytes:
    return hmac.new(_SECRET, payload, hashlib.sha256).digest()


def generate_license() -> str:
    serial = secrets.token_bytes(5)
    raw = serial + _mac(serial)[:5]            # 10 octets
    b32 = base64.b32encode(raw).decode().rstrip("=")   # 16 caractères
    groups = "-".join(b32[i:i + 4] for i in range(0, len(b32), 4))
    return "AMI-" + groups


def _decode(code: str):
    body = (code or "").strip().upper().replace("AMI-", "").replace("ADMI-", "").replace("-", "").replace(" ", "")
    if not body:
        return None
    pad = "=" * ((8 - len(body) % 8) % 8)
    try:
        raw = base64.b32decode(body + pad)
    except Exception:
        return None
    if len(raw) != 10:
        return None
    return raw[:5], raw[5:]


def verify_license(code: str) -> bool:
    d = _decode(code)
    if not d:
        return False
    serial, mac = d
    return hmac.compare_digest(_mac(serial)[:5], mac)


def activate(code: str, name: str = "") -> bool:
    if not verify_license(code):
        return False
    LIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIC_FILE.write_text(json.dumps({"code": code.strip().upper(), "name": name}),
                        encoding="utf-8")
    return True


def stored_license():
    try:
        d = json.loads(LIC_FILE.read_text(encoding="utf-8"))
        if verify_license(d.get("code", "")):
            return d
    except Exception:
        return None
    return None


def is_activated() -> bool:
    return stored_license() is not None
