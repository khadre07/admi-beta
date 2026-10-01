"""R2 / R3 — dossier de sauvegarde configurable, puis export/restauration.

R2 ici : résolution d'un chemin de sauvegarde (réglage, repli par défaut) et
validation (dossier créable + accessible en écriture).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admi import data
from admi.data import Database


def _sample_db():
    db = Database()
    db.machines.append({"id": "m1", "nom": "Presse", "departementId": "am",
                        "puissanceKW": 45, "dateMES": "2025-01-01", "statut": "En service"})
    db.arrets.append({"id": "a1", "machineId": "m1", "departementId": "am", "type": "Panne",
                      "cause": "x", "dateDebut": "2026-01-03T08:00", "dateFin": "2026-01-03T14:00"})
    db.settings = {"objectifs": {"disponibilite": 95}, "stockage": {"backupDir": ""}}
    return db


def test_resolve_backup_dir_default(tmp_path):
    # sans réglage, on retombe sur <base>/backups
    assert data.resolve_backup_dir(None, base=tmp_path) == tmp_path / "backups"
    assert data.resolve_backup_dir("", base=tmp_path) == tmp_path / "backups"


def test_resolve_backup_dir_configured(tmp_path):
    custom = tmp_path / "mes_sauvegardes"
    assert data.resolve_backup_dir(str(custom), base=tmp_path) == custom


def test_validate_backup_dir_ok(tmp_path):
    cible = tmp_path / "bk"
    ok, msg = data.validate_backup_dir(str(cible))
    assert ok is True
    assert cible.is_dir()           # créé au besoin


def test_validate_backup_dir_rejects_a_file(tmp_path):
    f = tmp_path / "pas_un_dossier.txt"
    f.write_text("x", encoding="utf-8")
    ok, msg = data.validate_backup_dir(str(f))
    assert ok is False


# --- R3 : export / reconstruction / fichiers ---------------------------------

def test_export_backup_has_marker_and_data():
    db = _sample_db()
    payload = data.export_backup(db)
    assert payload.get("format") == "admi-backup"
    assert payload.get("version") == 1
    assert payload["data"]["machines"] == db.machines


def test_backup_roundtrip_reconstructs_everything():
    db = _sample_db()
    payload = data.export_backup(db)
    db2 = data.backup_to_db(payload)
    assert db2.machines == db.machines
    assert db2.arrets == db.arrets
    assert db2.settings == db.settings


def test_backup_to_db_rejects_foreign_payload():
    with pytest.raises(ValueError):
        data.backup_to_db({"nope": True})


def test_write_list_read_backup(tmp_path):
    db = _sample_db()
    path = data.write_backup(db, directory=tmp_path)
    assert path.exists()
    assert path.name.startswith("admi-backup-") and path.suffix == ".json"
    listing = data.list_backups(tmp_path)
    assert path in listing
    reread = data.read_backup(path)
    assert reread["data"]["machines"] == db.machines


def test_settings_storage_section_renders(app):
    app.sidebar.radio[0].set_value("Paramètres").run()
    assert not app.exception, [str(e.value) for e in app.exception]
    md = " ".join(str(m.value) for m in app.markdown)
    assert "Stockage & sauvegarde" in md
