"""Alertes ADMI — envoi par e-mail (SMTP) et SMS (Twilio), best-effort.

La configuration est stockée dans la base (réglage « alerts ») ou, à défaut,
lue depuis des variables d'environnement. Rien n'est envoyé si ce n'est pas
configuré ; toutes les erreurs sont capturées (jamais de plantage de l'app).
"""
from __future__ import annotations

import base64
import os
import smtplib
import ssl
import urllib.parse
import urllib.request
from email.message import EmailMessage


def default_config() -> dict:
    return {
        "enabled": False,          # alertes automatiques (ex : nouvelle panne)
        "emails": [],              # destinataires e-mail
        "smtp": {"host": "", "port": 587, "user": "", "password": "", "from": "", "tls": True},
        "sms_numbers": [],         # destinataires SMS
        "twilio": {"sid": "", "token": "", "from": ""},
    }


def config_from_env() -> dict:
    """Complète la config avec les variables d'environnement (si présentes)."""
    cfg = default_config()
    e = os.environ
    if e.get("SMTP_HOST"):
        cfg["smtp"].update(host=e["SMTP_HOST"], port=int(e.get("SMTP_PORT", 587)),
                           user=e.get("SMTP_USER", ""), password=e.get("SMTP_PASSWORD", ""),
                           **{"from": e.get("ALERT_FROM", e.get("SMTP_USER", ""))})
    if e.get("ALERT_EMAILS"):
        cfg["emails"] = [x.strip() for x in e["ALERT_EMAILS"].split(",") if x.strip()]
    if e.get("TWILIO_SID"):
        cfg["twilio"].update(sid=e["TWILIO_SID"], token=e.get("TWILIO_TOKEN", ""),
                             **{"from": e.get("TWILIO_FROM", "")})
    if e.get("ALERT_SMS"):
        cfg["sms_numbers"] = [x.strip() for x in e["ALERT_SMS"].split(",") if x.strip()]
    return cfg


def _merge(base: dict, override: dict) -> dict:
    out = default_config()
    for k, v in base.items():
        out[k] = v
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def send_email(cfg: dict, subject: str, body: str) -> tuple[bool, str]:
    smtp = cfg.get("smtp", {})
    to = cfg.get("emails", [])
    if not smtp.get("host") or not to:
        return False, "SMTP non configuré ou aucun destinataire."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from") or smtp.get("user")
    msg["To"] = ", ".join(to)
    msg.set_content(body)
    try:
        port = int(smtp.get("port", 587))
        if port == 465:
            with smtplib.SMTP_SSL(smtp["host"], port, context=ssl.create_default_context(), timeout=15) as s:
                if smtp.get("user"):
                    s.login(smtp["user"], smtp.get("password", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(smtp["host"], port, timeout=15) as s:
                if smtp.get("tls", True):
                    s.starttls(context=ssl.create_default_context())
                if smtp.get("user"):
                    s.login(smtp["user"], smtp.get("password", ""))
                s.send_message(msg)
        return True, f"E-mail envoyé à {len(to)} destinataire(s)."
    except Exception as exc:  # noqa: BLE001
        return False, f"Échec e-mail : {exc}"


def send_sms(cfg: dict, body: str) -> tuple[bool, str]:
    tw = cfg.get("twilio", {})
    numbers = cfg.get("sms_numbers", [])
    if not tw.get("sid") or not tw.get("from") or not numbers:
        return False, "Twilio non configuré ou aucun numéro."
    url = f"https://api.twilio.com/2010-04-01/Accounts/{tw['sid']}/Messages.json"
    auth = base64.b64encode(f"{tw['sid']}:{tw.get('token','')}".encode()).decode()
    sent, errors = 0, []
    for number in numbers:
        data = urllib.parse.urlencode({"To": number, "From": tw["from"], "Body": body}).encode()
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", "Basic " + auth)
        try:
            urllib.request.urlopen(req, timeout=15)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    if sent:
        return True, f"SMS envoyé à {sent} numéro(s)." + (f" Erreurs : {errors}" if errors else "")
    return False, f"Échec SMS : {errors}"


def notify(cfg: dict, subject: str, message: str) -> dict:
    """Envoie e-mail + SMS selon la config. Best-effort ; renvoie les statuts."""
    cfg = _merge(config_from_env(), cfg or {})
    res = {}
    if cfg.get("emails"):
        ok, msg = send_email(cfg, subject, message)
        res["email"] = (ok, msg)
    if cfg.get("sms_numbers"):
        ok, msg = send_sms(cfg, f"{subject} — {message}")
        res["sms"] = (ok, msg)
    return res
