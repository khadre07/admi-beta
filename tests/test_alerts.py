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
