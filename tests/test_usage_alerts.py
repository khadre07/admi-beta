"""Chantier A — alertes de seuil sur le temps d'utilisation machine.

Deux briques pures testées ici :
  - kpis.machine_usage_hours : heures d'utilisation cumulées d'une machine
    = heures d'ouverture du département (dateMES -> maintenant) - arrêts.
  - kpis.usage_alert_level / kpis.pending_usage_alerts : décision d'alerte
    (niveau « approche » / « atteint ») avec anti-spam (dédup par niveau).
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi.data import Database
from admi import kpis, alerts


def _machine_db(dateMES="2026-01-01"):
    db = Database()
    db.machines.append({"id": "m1", "nom": "Presse", "departementId": "am",
                        "puissanceKW": 45, "dateMES": dateMES, "statut": "En service"})
    return db


# --- machine_usage_hours -----------------------------------------------------

def test_usage_hours_continuous_since_mes():
    db = _machine_db("2026-01-01")
    # am = planning par défaut 24h/24 7j/7, du 1er au 8 janvier = 7 jours pleins
    h = kpis.machine_usage_hours(db, db.machines[0], now=datetime(2026, 1, 8))
    assert h == 7 * 24


def test_usage_hours_deducts_stops():
    db = _machine_db("2026-01-01")
    db.arrets.append({"id": "a1", "machineId": "m1", "departementId": "am",
                      "type": "Panne", "dateDebut": "2026-01-03T08:00",
                      "dateFin": "2026-01-03T14:00"})  # 6h
    h = kpis.machine_usage_hours(db, db.machines[0], now=datetime(2026, 1, 8))
    assert h == 7 * 24 - 6


def test_usage_hours_ignores_other_machines_stops():
    db = _machine_db("2026-01-01")
    db.arrets.append({"id": "a2", "machineId": "AUTRE", "departementId": "am",
                      "type": "Panne", "dateDebut": "2026-01-03T08:00",
                      "dateFin": "2026-01-03T20:00"})  # 12h sur une autre machine
    h = kpis.machine_usage_hours(db, db.machines[0], now=datetime(2026, 1, 8))
    assert h == 7 * 24


def test_usage_hours_without_mes_is_zero():
    db = _machine_db(dateMES="")
    h = kpis.machine_usage_hours(db, db.machines[0], now=datetime(2026, 1, 8))
    assert h == 0.0


# --- usage_alert_level -------------------------------------------------------

def test_alert_level_thresholds():
    # seuil 100h, marge 90 % -> approche à 90, atteint à 100
    assert kpis.usage_alert_level(50, 100, margin_pct=90) == ""
    assert kpis.usage_alert_level(90, 100, margin_pct=90) == "approche"
    assert kpis.usage_alert_level(99, 100, margin_pct=90) == "approche"
    assert kpis.usage_alert_level(100, 100, margin_pct=90) == "atteint"
    assert kpis.usage_alert_level(130, 100, margin_pct=90) == "atteint"


def test_alert_level_no_threshold():
    assert kpis.usage_alert_level(500, 0, margin_pct=90) == ""
    assert kpis.usage_alert_level(500, None, margin_pct=90) == ""
    assert kpis.usage_alert_level(500, "", margin_pct=90) == ""


# --- pending_usage_alerts (anti-spam) ---------------------------------------

def test_pending_alert_fires_once_then_dedups():
    # usage 92h, seuil maintenance 100h -> approche
    alerts, state = kpis.pending_usage_alerts(
        usage=92, seuil_maintenance=100, seuil_arret=0, notified={}, margin_pct=90)
    assert [a["kind"] for a in alerts] == ["maintenance"]
    assert alerts[0]["level"] == "approche"
    # même usage, état déjà notifié -> plus rien
    alerts2, state2 = kpis.pending_usage_alerts(
        usage=92, seuil_maintenance=100, seuil_arret=0, notified=state, margin_pct=90)
    assert alerts2 == []
    assert state2["maintenance"] == "approche"


def test_pending_alert_escalates_approche_to_atteint():
    _, state = kpis.pending_usage_alerts(
        usage=92, seuil_maintenance=100, seuil_arret=0, notified={}, margin_pct=90)
    # l'usage franchit le seuil -> nouvelle alerte « atteint »
    alerts, state2 = kpis.pending_usage_alerts(
        usage=101, seuil_maintenance=100, seuil_arret=0, notified=state, margin_pct=90)
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "maintenance"
    assert alerts[0]["level"] == "atteint"
    assert state2["maintenance"] == "atteint"


def test_pending_alert_handles_both_thresholds():
    alerts, state = kpis.pending_usage_alerts(
        usage=105, seuil_maintenance=100, seuil_arret=110, notified={}, margin_pct=90)
    kinds = sorted(a["kind"] for a in alerts)
    assert kinds == ["arret", "maintenance"]
    levels = {a["kind"]: a["level"] for a in alerts}
    assert levels["maintenance"] == "atteint"   # 105 >= 100
    assert levels["arret"] == "approche"          # 105 >= 0.9*110 (99) mais < 110


# --- alerts.build_usage_messages (orchestration testable, sans Streamlit) ----

def _enabled_cfg():
    return {"enabled": True, "usage_margin_pct": 90}


def test_build_messages_emits_then_dedups():
    db = _machine_db("2020-01-01")               # ancienne machine -> usage énorme
    db.machines[0]["seuilMaintenanceH"] = 1       # seuil minuscule -> atteint
    msgs, dirty = alerts.build_usage_messages(db, _enabled_cfg())
    assert dirty is True
    assert len(msgs) == 1
    assert msgs[0]["kind"] == "maintenance"
    assert msgs[0]["level"] == "atteint"
    assert "Presse" in msgs[0]["subject"]
    assert msgs[0]["details"]                      # tableau de détails non vide
    # 2e passage : l'état anti-spam est mémorisé dans db.settings -> plus rien
    msgs2, dirty2 = alerts.build_usage_messages(db, _enabled_cfg())
    assert msgs2 == []
    assert dirty2 is False


def test_build_messages_skips_machine_without_threshold():
    db = _machine_db("2020-01-01")                 # aucun seuil défini
    msgs, dirty = alerts.build_usage_messages(db, _enabled_cfg())
    assert msgs == []
    assert dirty is False
