"""Couche de stockage ADMI — SQLAlchemy (SQLite par défaut, PostgreSQL en option).

L'emplacement / le moteur est choisi par la variable d'environnement
``DATABASE_URL`` :

    (défaut)                      sqlite:///<dossier_données>/admi.db
    PostgreSQL                    postgresql+psycopg2://user:pwd@host/admi

Chaque type de donnée est stocké dans une table ``id`` + ``payload`` (JSON), ce
qui reste simple et portable entre SQLite et PostgreSQL. Les écritures sont
transactionnelles et **au niveau de la ligne** (pas de réécriture globale),
ce qui évite les écrasements entre utilisateurs.
"""
from __future__ import annotations

import os

from sqlalchemy import (Column, JSON, MetaData, String, Table, create_engine,
                        delete as sql_delete, select)

from .data import DATA_DIR

ENTITIES = ["machines", "arrets", "energie", "interventions", "planning"]

_meta = MetaData()
_tables: dict = {}
_engine = None


def _database_url() -> str:
    env = os.environ.get("DATABASE_URL")
    if env:
        return env
    return "sqlite:///" + (DATA_DIR / "admi.db").as_posix()


def _define_tables():
    if _tables:
        return
    for name in ENTITIES:
        _tables[name] = Table(name, _meta,
                              Column("id", String, primary_key=True),
                              Column("payload", JSON, nullable=False))
    _tables["settings"] = Table("settings", _meta,
                                Column("skey", String, primary_key=True),
                                Column("value", JSON, nullable=False))


def engine():
    global _engine
    if _engine is None:
        _define_tables()
        url = _database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, connect_args=connect_args)
        _meta.create_all(_engine)
    return _engine


# ---------------------------------------------------------------------------
# Opérations
# ---------------------------------------------------------------------------
def list_records(name: str) -> list:
    t = _tables[name]
    with engine().connect() as c:
        return [row[0] for row in c.execute(select(t.c.payload)).fetchall()]


def upsert(name: str, rec: dict) -> None:
    t = _tables[name]
    with engine().begin() as c:
        c.execute(sql_delete(t).where(t.c.id == rec["id"]))
        c.execute(t.insert().values(id=rec["id"], payload=rec))


def delete(name: str, rid: str) -> None:
    t = _tables[name]
    with engine().begin() as c:
        c.execute(sql_delete(t).where(t.c.id == rid))


def replace_all(name: str, recs: list) -> None:
    t = _tables[name]
    with engine().begin() as c:
        c.execute(sql_delete(t))
        if recs:
            c.execute(t.insert(), [{"id": r["id"], "payload": r} for r in recs])


def get_settings() -> dict:
    t = _tables["settings"]
    with engine().connect() as c:
        rows = c.execute(select(t.c.skey, t.c.value)).fetchall()
    return {k: v for k, v in rows}


def set_setting(key: str, value) -> None:
    t = _tables["settings"]
    with engine().begin() as c:
        c.execute(sql_delete(t).where(t.c.skey == key))
        c.execute(t.insert().values(skey=key, value=value))


def is_empty() -> bool:
    """Vrai si la base ne contient aucune machine (base neuve)."""
    return len(list_records("machines")) == 0
