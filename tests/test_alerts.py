"""Tests des alertes (SMTP simulé)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import alerts


class _FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, pwd):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


def test_send_email_ok(monkeypatch):
    _FakeSMTP.sent.clear()
    monkeypatch.setattr(alerts.smtplib, "SMTP", _FakeSMTP)
    cfg = {"emails": ["a@b.com", "c@d.com"],
           "smtp": {"host": "smtp.test", "port": 587, "user": "u", "password": "p",
                    "from": "admi@test", "tls": True}}
    ok, msg = alerts.send_email(cfg, "Sujet", "Corps")
    assert ok, msg
    assert len(_FakeSMTP.sent) == 1
    sent = _FakeSMTP.sent[0]
    assert sent["Subject"] == "Sujet"
    assert "a@b.com" in sent["To"] and "c@d.com" in sent["To"]


def test_the_email_is_sent_in_both_text_and_html(monkeypatch):
    """Un client qui refuse le HTML doit quand même lire l'alerte."""
    _FakeSMTP.sent.clear()
    monkeypatch.setattr(alerts.smtplib, "SMTP", _FakeSMTP)
    cfg = {"emails": ["a@b.com"],
           "smtp": {"host": "smtp.test", "port": 587, "from": "ami@test"}}
    alerts.send_email(cfg, "Nouvelle panne", "Presse à injection AM-1 est en panne.")
    sent = _FakeSMTP.sent[0]

    types = [p.get_content_type() for p in sent.walk()]
    assert "text/plain" in types and "text/html" in types
    assert "image/png" in types, "le logo voyage avec le message"

    texte = sent.get_body(("plain",)).get_content()
    assert "Presse à injection AM-1" in texte and "<" not in texte


def test_the_logo_travels_with_the_message(monkeypatch):
    """Un logo appelé par URL serait bloqué par Gmail ; il est joint au message."""
    _FakeSMTP.sent.clear()
    monkeypatch.setattr(alerts.smtplib, "SMTP", _FakeSMTP)
    alerts.send_email({"emails": ["a@b.com"], "smtp": {"host": "s", "from": "f"}}, "S", "B")
    sent = _FakeSMTP.sent[0]

    image = next(p for p in sent.walk() if p.get_content_type() == "image/png")
    assert image["Content-ID"] == f"<{alerts.LOGO_CID}>"
    html = sent.get_body(("html",)).get_content()
    assert f"cid:{alerts.LOGO_CID}" in html
    assert "http://" not in html and "https://" not in html


def test_the_html_wears_the_ami_identity():
    texte, html = alerts.render_email("Nouvelle panne", "Machine X arrêtée.")
    assert "AMI" in html and "Analyse de Maintenance Industrielle" in html
    assert "#F2A93B" in html, "la couleur signature"
    assert "Nouvelle panne" in html and "Machine X arrêtée." in html
    assert "<script" not in html
    assert "style=" in html, "styles en ligne : les clients mail suppriment les feuilles"


def test_the_headline_does_not_repeat_the_brand():
    """Le bandeau porte déjà « AMI » : le titre n'a pas à le redire."""
    _, html = alerts.render_email("AMI — Panne : Presse AM-1", "Corps")
    titre = html.split("<h1")[1].split("</h1>")[0]
    assert "Panne : Presse AM-1" in titre and "AMI" not in titre


def test_the_details_are_laid_out_as_rows():
    _, html = alerts.render_email("Panne", "Message",
                                  details={"Machine": "Presse AM-1", "Département": "AM"})
    assert "Machine" in html and "Presse AM-1" in html and "Département" in html


def test_send_email_not_configured():
    ok, msg = alerts.send_email({"emails": [], "smtp": {}}, "s", "b")
    assert ok is False


def test_notify_dispatches_email(monkeypatch):
    _FakeSMTP.sent.clear()
    monkeypatch.setattr(alerts.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    cfg = {"enabled": True, "emails": ["x@y.com"],
           "smtp": {"host": "smtp.test", "port": 587, "from": "a@b"}}
    res = alerts.notify(cfg, "Panne", "Machine X")
    assert "email" in res and res["email"][0] is True


def test_sms_not_configured():
    ok, msg = alerts.send_sms({"twilio": {}, "sms_numbers": []}, "hello")
    assert ok is False
