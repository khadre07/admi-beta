"""Modèle de données ADMI + générateur de données de démo + persistance JSON.

Les enregistrements sont conservés en listes de dictionnaires (comme dans
l'application d'origine) pour une sérialisation JSON directe. Les dates sont
stockées en chaînes ISO :
  - machines.dateMES              -> "YYYY-MM-DD"
  - arrets.dateDebut / dateFin    -> "YYYY-MM-DDTHH:MM"
  - interventions.date            -> "YYYY-MM-DD"
"""
from __future__ import annotations

import json
import os
import random
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import DEPARTEMENTS, TYPES_ARRET, TYPES_INTERV, TYPES_PLAN


def _data_dir() -> Path:
    """Dossier de stockage des données (cross-platform).

    En mode « gelé » (exécutable PyInstaller), le bundle est en lecture seule :
    on écrit dans le dossier de données utilisateur adapté à l'OS. On peut aussi
    forcer l'emplacement avec la variable d'environnement ADMI_DATA_DIR
    (utile pour un serveur / conteneur Docker). En développement, on reste dans
    le dossier `data/` du projet.
    """
    env = os.environ.get("ADMI_DATA_DIR")
    if env:
        base = Path(env)
        base.mkdir(parents=True, exist_ok=True)
        return base
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            root = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        elif sys.platform == "darwin":
            root = Path.home() / "Library" / "Application Support"
        else:  # Linux / autres
            root = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        base = Path(root) / "ADMI"
        base.mkdir(parents=True, exist_ok=True)
        return base
    base = Path(__file__).resolve().parent.parent / "data"
    base.mkdir(parents=True, exist_ok=True)   # cloud : le dossier peut ne pas exister
    return base


DATA_DIR = _data_dir()
DATA_FILE = DATA_DIR / "admi_data.json"


def uid() -> str:
    return "id" + uuid.uuid4().hex[:10]


def default_schedule() -> dict:
    """Département en marche continue par défaut (24h/24, 7j/7)."""
    return {"heuresParJour": 24, "jours": [True] * 7}


@dataclass
class Database:
    machines: list = field(default_factory=list)
    arrets: list = field(default_factory=list)
    energie: list = field(default_factory=list)
    interventions: list = field(default_factory=list)
    planning: list = field(default_factory=list)
    settings: dict = field(default_factory=lambda: {"tempsTravail": {}})

    # -- lookups -----------------------------------------------------------
    def machine(self, mid: str):
        return next((m for m in self.machines if m["id"] == mid), None)

    def machine_name(self, mid: str) -> str:
        m = self.machine(mid)
        return m["nom"] if m else "—"

    def machine_dept(self, mid: str):
        m = self.machine(mid)
        return m["departementId"] if m else None

    def dept_schedule(self, dept_id: str) -> dict:
        tt = self.settings.setdefault("tempsTravail", {})
        return tt.setdefault(dept_id, default_schedule())

    # -- (de)sérialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Database":
        return cls(
            machines=d.get("machines", []),
            arrets=d.get("arrets", []),
            energie=d.get("energie", []),
            interventions=d.get("interventions", []),
            planning=d.get("planning", []),
            settings=d.get("settings", {"tempsTravail": {}}),
        )


# ---------------------------------------------------------------------------
# Persistance (SQLite par défaut, PostgreSQL via DATABASE_URL — voir admi/db.py)
# Import paresseux de la couche db pour éviter un cycle d'import.
# ---------------------------------------------------------------------------
def _dbmod():
    from . import db as _db
    return _db


def save_db(db: Database) -> None:
    """Écrit l'intégralité de l'état (utilisé pour l'import et l'amorçage démo)."""
    d = _dbmod()
    for name in ("machines", "arrets", "energie", "interventions", "planning"):
        d.replace_all(name, getattr(db, name))
    d.set_setting("settings", db.settings)


def save_settings(db: Database) -> None:
    _dbmod().set_setting("settings", db.settings)


def get_alert_config() -> dict:
    from . import alerts
    stored = _dbmod().get_settings().get("alerts")
    return stored or alerts.default_config()


def save_alert_config(cfg: dict) -> None:
    _dbmod().set_setting("alerts", cfg)


def upsert_record(db: Database, table: str, rec: dict) -> dict:
    """Ajoute ou met à jour UNE ligne (en mémoire + en base, transactionnel)."""
    lst = getattr(db, table)
    for i, x in enumerate(lst):
        if x["id"] == rec["id"]:
            lst[i] = rec
            break
    else:
        lst.append(rec)
    _dbmod().upsert(table, rec)
    return rec


def delete_record(db: Database, table: str, rid: str) -> None:
    setattr(db, table, [x for x in getattr(db, table) if x["id"] != rid])
    _dbmod().delete(table, rid)


def _load_json_legacy():
    """Lit l'ancien fichier JSON (pour migration), sinon None."""
    if DATA_FILE.exists():
        try:
            return Database.from_dict(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_db() -> Database:
    """Charge depuis la base. Première fois : migre l'ancien JSON s'il existe,
    sinon génère des données de démo."""
    d = _dbmod()
    d.engine()  # crée les tables si nécessaire
    if d.is_empty():
        migrated = _load_json_legacy()
        db = migrated if migrated else generate_demo()
        save_db(db)
        if migrated and DATA_FILE.exists():
            try:
                DATA_FILE.rename(DATA_FILE.with_name(DATA_FILE.name + ".migrated"))
            except OSError:
                pass
        return db
    settings = d.get_settings().get("settings") or {"tempsTravail": {}}
    if "tempsTravail" not in settings:
        settings = {"tempsTravail": {}}
    return Database(
        machines=d.list_records("machines"),
        arrets=d.list_records("arrets"),
        energie=d.list_records("energie"),
        interventions=d.list_records("interventions"),
        planning=d.list_records("planning"),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Générateur de données de démo (réaliste, multi-années 2022 -> aujourd'hui)
# ---------------------------------------------------------------------------
_SEED_MACHINES = [
    ("Presse à injection AM-1", "am", 45), ("Extrudeuse plastique AM-2", "am", 30),
    ("Onduleuse Zinc ON-1", "ond", 55), ("Cisaille-Profileuse ON-2", "ond", 15),
    ("Mélangeur Peinture PT-1", "pt", 20), ("Remplisseuse PT-2", "pt", 10),
    ("Réacteur Colle CH-1", "chi", 35), ("Cuve Chauffante CH-2", "chi", 18),
    ("Extrudeuse Sacherie SC-1", "sac", 60), ("Imprimeuse Flexo SC-2", "sac", 25),
    ("Ligne de Profilage SL-1", "sl", 50), ("Poste à Souder SL-2", "sl", 22),
    ("Groupe Climatisation ADM-1", "adm", 12),
    ("Groupe Électrogène SRV-1", "srv", 200), ("Compresseur d'air SRV-2", "srv", 40),
]

_TECHNICIENS = ["Ousmane Diop", "Mamadou Fall", "Awa Ndiaye", "Cheikh Sarr", "Fatou Ba", "Ibrahima Sow"]
_CAUSES = [
    "Rupture courroie", "Surchauffe moteur", "Fuite hydraulique", "Capteur défaillant",
    "Roulement usé", "Court-circuit", "Blocage mécanique", "Usure normale",
]
_PIECES = [
    ("Courroie trapézoïdale", 12000), ("Roulement 6205", 4500), ("Joint torique", 800),
    ("Contacteur 25A", 9500), ("Fusible 32A", 1200), ("Vérin pneumatique", 28000),
    ("Filtre à huile", 3500), ("Capteur de proximité", 15000), ("Courroie crantée", 8000),
]


def generate_demo(seed: int = 20260811) -> Database:
    """Produit un jeu de données cohérent : le taux d'arrêt décroît avec les
    années (tendance de disponibilité en hausse) pour rendre les graphiques
    parlants."""
    rng = random.Random(seed)
    db = Database()

    # Machines
    for nom, dept, kw in _SEED_MACHINES:
        db.machines.append({
            "id": uid(), "nom": nom, "departementId": dept,
            "puissanceKW": kw, "dateMES": "2019-06-01", "statut": "En service",
        })

    today = date.today()
    years = list(range(2020, today.year + 1))

    for yi, year in enumerate(years):
        # Indisponibilité cible décroissante : ~11 % en 2022 -> ~4 % ensuite,
        # ce qui rend la jauge de disponibilité lisible et la tendance parlante.
        target_unavail = max(0.035, 0.11 - 0.016 * yi)
        for month in range(12):
            first = date(year, month + 1, 1)
            if first > today:
                continue
            days_in_month = (date(year + 1, 1, 1) if month == 11
                             else date(year, month + 2, 1)) - first
            month_hours = days_in_month.days * 24

            # ---- Arrêts : budget d'indisponibilité réparti par machine/mois ----
            for m in db.machines:
                budget = month_hours * target_unavail * rng.uniform(0.4, 1.6)
                guard = 0
                while budget > 1 and guard < 12:
                    guard += 1
                    day = rng.randint(1, 27)
                    hour = rng.randint(6, 20)
                    start = datetime(year, month + 1, day, hour, rng.choice([0, 15, 30, 45]))
                    if start > datetime.now():
                        break
                    dur_h = round(min(budget, rng.uniform(1.0, 10.0)), 1)
                    budget -= dur_h
                    end = start + timedelta(hours=dur_h)
                    typ = rng.choices(TYPES_ARRET, weights=[38, 18, 14, 12, 10, 8])[0]
                    db.arrets.append({
                        "id": uid(), "machineId": m["id"], "departementId": m["departementId"],
                        "type": typ, "cause": rng.choice(_CAUSES),
                        "dateDebut": start.strftime("%Y-%m-%dT%H:%M"),
                        "dateFin": end.strftime("%Y-%m-%dT%H:%M"),
                        "description": "",
                    })

            # ---- Énergie : un relevé par département et par mois ----
            for d in DEPARTEMENTS:
                dept_power = sum(x["puissanceKW"] for x in db.machines if x["departementId"] == d["id"])
                if dept_power == 0:
                    dept_power = 8
                base = dept_power * rng.uniform(180, 320)  # kWh mensuels
                kwh = round(base * rng.uniform(0.85, 1.15))
                db.energie.append({
                    "id": uid(), "departementId": d["id"], "mois": month, "annee": year,
                    "kwh": kwh, "montant": round(kwh * rng.uniform(115, 145)),
                })

            # ---- Interventions : réparties sur les machines ----
            n_interv = rng.randint(3, 8)
            for _ in range(n_interv):
                m = rng.choice(db.machines)
                day = rng.randint(1, 27)
                idate = date(year, month + 1, day)
                if idate > today:
                    continue
                typ = rng.choices(TYPES_INTERV, weights=[42, 30, 10, 12, 6])[0]
                n_pieces = rng.choices([0, 1, 2, 3], weights=[25, 40, 25, 10])[0]
                pieces = []
                for _ in range(n_pieces):
                    nom_p, cout = rng.choice(_PIECES)
                    pieces.append({"designation": nom_p, "qte": rng.randint(1, 3),
                                   "cout": int(cout * rng.uniform(0.9, 1.1))})
                db.interventions.append({
                    "id": uid(), "machineId": m["id"], "departementId": m["departementId"],
                    "date": idate.strftime("%Y-%m-%d"), "type": typ,
                    "technicien": rng.choice(_TECHNICIENS),
                    "duree": round(rng.uniform(0.5, 6), 1),
                    "coutMainOeuvre": rng.choice([8000, 12000, 15000, 20000, 25000]),
                    "description": "", "pieces": pieces,
                })

    # ---- Planning : tâches préventives autour de la période courante ----
    _plan_titles = {
        "Préventif": "Maintenance préventive", "Inspection": "Inspection de sécurité",
        "Lubrification": "Graissage / lubrification", "Contrôle réglementaire": "Contrôle réglementaire",
        "Révision générale": "Révision générale", "Autre": "Opération planifiée",
    }
    for offset in range(-2, 3):  # de 2 mois avant à 2 mois après
        base_month = today.month - 1 + offset
        y = today.year + (base_month // 12)
        mth = base_month % 12
        for m in rng.sample(db.machines, k=rng.randint(5, 9)):
            day = rng.randint(1, 27)
            pdate = date(y, mth + 1, day)
            ptype = rng.choices(TYPES_PLAN, weights=[30, 25, 25, 10, 5, 5])[0]
            if pdate < today:
                statut = rng.choices(["Réalisé", "En retard"], weights=[80, 20])[0]
            else:
                statut = "Planifié"
            db.planning.append({
                "id": uid(), "machineId": m["id"], "departementId": m["departementId"],
                "titre": f"{_plan_titles[ptype]} — {m['nom']}", "date": pdate.strftime("%Y-%m-%d"),
                "type": ptype, "statut": statut, "description": "",
            })

    # Horaires : Administration = 8h/j du lundi au vendredi (le reste en continu)
    db.dept_schedule("adm").update({"heuresParJour": 8, "jours": [True] * 5 + [False, False]})
    return db
