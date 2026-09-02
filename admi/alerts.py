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
import sys
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

from . import i18n
from .config import THEME

# Le logo voyage avec le message : une image appelée par URL serait bloquée par
# Gmail tant que le destinataire n'a pas cliqué « afficher les images ».
LOGO_CID = "ami-logo"
_TAGLINE = "Analyse de Maintenance Industrielle"
# Corps du mail en clair (l'app est sombre, les boîtes mail ne le sont pas).
_ENCRE = "#0A1220"
_ENCRE_DOUCE = "#5A6B85"
_FOND = "#F4F6FA"
_TRAIT = "#E2E8F2"


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


def _logo_bytes() -> bytes | None:
    """PNG du logo, produit depuis le SVG par tools/render_logo_png.py."""
    racines = [Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parent.parent]
    for racine in racines:
        chemin = racine / "assets" / "ami_logo_email.png"
        if chemin.is_file():
            return chemin.read_bytes()
    return None


def _ligne_detail(cle: str, valeur: str) -> str:
    return (f'<tr>'
            f'<td style="padding:7px 0; font-size:13px; color:{_ENCRE_DOUCE}; '
            f'white-space:nowrap; vertical-align:top">{cle}</td>'
            f'<td style="padding:7px 0 7px 18px; font-size:13px; color:{_ENCRE}; '
            f'font-weight:600; vertical-align:top">{valeur}</td></tr>')


def render_email(subject: str, message: str, details: dict | None = None) -> tuple[str, str]:
    """Rend l'alerte en (texte brut, HTML).

    Tout est en styles *en ligne* et en tableaux : les clients mail suppriment
    les feuilles de style, et Outlook ne connaît pas la mise en page moderne.
    """
    # Le bandeau porte déjà la marque : inutile de la répéter dans le titre.
    titre = subject.removeprefix("AMI — ").removeprefix("AMI - ").strip() or subject
    _t = i18n.t
    lignes = [f"AMI — {_t(_TAGLINE)}", "", titre, "", message]
    if details:
        lignes += [""] + [f"{c} : {v}" for c, v in details.items()]
    lignes += ["", _t("Message automatique envoyé par AMI. Ne pas répondre.")]
    texte = "\n".join(lignes)

    tableau = ""
    if details:
        tableau = ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
                   f'style="width:100%; margin-top:18px; border-top:1px solid {_TRAIT}">'
                   + "".join(_ligne_detail(c, v) for c, v in details.items())
                   + "</table>")

    html = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0; padding:0; background:{_FOND};">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"
       style="width:100%; background:{_FOND}; padding:28px 12px;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"
           style="width:100%; max-width:560px; background:#FFFFFF; border:1px solid {_TRAIT};
                  border-radius:14px; overflow:hidden;
                  font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
      <tr><td style="background:{THEME['bg2']}; padding:22px 26px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding-right:14px; line-height:0;">
              <img src="cid:{LOGO_CID}" width="46" height="46" alt="AMI"
                   style="display:block; border:0; border-radius:9px;"></td>
            <td style="vertical-align:middle;">
              <div style="font-size:23px; font-weight:700; letter-spacing:.14em; line-height:1;">
                <span style="color:{THEME['accent2']}">A</span><span style="color:#FFFFFF">MI</span>
              </div>
              <div style="color:{THEME['muted']}; font-size:10.5px; letter-spacing:.06em;
                          margin-top:5px;">{_t(_TAGLINE)}</div></td>
          </tr></table></td></tr>
      <tr><td style="height:3px; background:{THEME['accent']}; line-height:0;">&nbsp;</td></tr>
      <tr><td style="padding:26px;">
        <div style="font-size:10.5px; letter-spacing:.16em; text-transform:uppercase;
                    color:{THEME['accent']}; font-weight:700;">{_t("Alerte maintenance")}</div>
        <h1 style="margin:8px 0 0; font-size:20px; line-height:1.3; color:{_ENCRE};
                   font-weight:700;">{titre}</h1>
        <p style="margin:12px 0 0; font-size:14.5px; line-height:1.65; color:#33455F;">{message}</p>
        {tableau}
      </td></tr>
      <tr><td style="padding:16px 26px 22px; border-top:1px solid {_TRAIT};
                     font-size:11.5px; line-height:1.6; color:{_ENCRE_DOUCE};">
        {_t("Message automatique envoyé par")} <b style="color:{_ENCRE}">AMI</b> — {_t(_TAGLINE)}.<br>
        {_t("Ne pas répondre à cet e-mail.")}</td></tr>
    </table>
  </td></tr>
</table></body></html>"""
    return texte, html


def send_email(cfg: dict, subject: str, body: str, details: dict | None = None) -> tuple[bool, str]:
    smtp = cfg.get("smtp", {})
    to = cfg.get("emails", [])
    if not smtp.get("host") or not to:
        return False, "SMTP non configuré ou aucun destinataire."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from") or smtp.get("user")
    msg["To"] = ", ".join(to)
    texte, html = render_email(subject, body, details)
    msg.set_content(texte)                       # repli pour les clients sans HTML
    msg.add_alternative(html, subtype="html")
    logo = _logo_bytes()
    if logo:
        msg.get_payload()[1].add_related(logo, maintype="image", subtype="png",
                                         cid=f"<{LOGO_CID}>")
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


def notify(cfg: dict, subject: str, message: str, details: dict | None = None) -> dict:
    """Envoie e-mail + SMS selon la config. Best-effort ; renvoie les statuts."""
    cfg = _merge(config_from_env(), cfg or {})
    res = {}
    if cfg.get("emails"):
        ok, msg = send_email(cfg, subject, message, details)
        res["email"] = (ok, msg)
    if cfg.get("sms_numbers"):
        # Le SMS reste une seule ligne : pas de mise en forme, et 160 caractères.
        plat = " · ".join(f"{c} {v}" for c, v in (details or {}).items())
        res["sms"] = send_sms(cfg, f"{subject} — {message}{' · ' + plat if plat else ''}")
    return res
