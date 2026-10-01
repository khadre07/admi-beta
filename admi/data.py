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

from . import config
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


# ---------------------------------------------------------------------------
# Dossier de sauvegarde (R2) — configurable, avec repli par défaut.
# La base vit dans PostgreSQL/SQLite (DATABASE_URL) ; ce chemin ne sert qu'aux
# fichiers de sauvegarde (admi-backup-*.json).
# ---------------------------------------------------------------------------
def resolve_backup_dir(configured: str | None, base: Path | None = None) -> Path:
    """Chemin de sauvegarde effectif : le réglage s'il est renseigné, sinon
    <base>/backups (base = dossier de données, qui respecte déjà ADMI_DATA_DIR)."""
    base = base or DATA_DIR
    if configured and str(configured).strip():
        return Path(str(configured).strip()).expanduser()
    return base / "backups"


def validate_backup_dir(path: str) -> tuple[bool, str]:
    """Vérifie qu'un dossier de sauvegarde est utilisable (créable + écriture)."""
    try:
        p = Path(str(path)).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            return False, f"{p} n'est pas un dossier."
        tmp = p / ".admi_write_test"
        tmp.write_text("ok", encoding="utf-8")
        tmp.unlink()
        return True, f"Dossier de sauvegarde valide : {p}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Dossier inutilisable : {exc}"


def get_backup_dir(db: "Database") -> Path:
    """Dossier de sauvegarde courant (réglage de l'app, ou repli par défaut)."""
    configured = (db.settings.get("stockage") or {}).get("backupDir")
    return resolve_backup_dir(configured)


def set_backup_dir(db: "Database", path: str) -> None:
    """Enregistre le dossier de sauvegarde dans les réglages (persisté)."""
    db.settings.setdefault("stockage", {})["backupDir"] = str(path or "").strip()
    save_settings(db)


# ---------------------------------------------------------------------------
# Sauvegarde / restauration (R3) — passe par la couche data, donc indépendant
# du moteur (SQLite comme PostgreSQL). Une sauvegarde = toutes les tables + les
# réglages dans un seul fichier JSON.
# ---------------------------------------------------------------------------
def export_backup(db: "Database") -> dict:
    """Sérialise l'intégralité de l'état (tables + réglages) pour sauvegarde."""
    return {"format": "admi-backup", "version": 1,
            "exportedAt": datetime.now().isoformat(timespec="seconds"),
            "data": db.to_dict()}


def backup_to_db(payload: dict) -> "Database":
    """Reconstruit une Database depuis une sauvegarde (valide le format)."""
    if not isinstance(payload, dict) or payload.get("format") != "admi-backup":
        raise ValueError("Fichier de sauvegarde AMI invalide ou non reconnu.")
    return Database.from_dict(payload.get("data") or {})


def restore_backup(db: "Database", payload: dict) -> "Database":
    """Restaure une sauvegarde — DESTRUCTIF : remplace toutes les données."""
    nouveau = backup_to_db(payload)
    save_db(nouveau)
    return nouveau


def write_backup(db: "Database", directory=None) -> Path:
    """Écrit une sauvegarde horodatée dans le dossier (ou celui des réglages)."""
    directory = Path(directory) if directory else get_backup_dir(db)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"admi-backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(export_backup(db), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_backups(directory) -> list:
    """Sauvegardes présentes dans un dossier, de la plus récente à la plus ancienne."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("admi-backup-*.json"), reverse=True)


def read_backup(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    pieces: list = field(default_factory=list)
    mouvements: list = field(default_factory=list)
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

    def _dept_collections(self):
        return {"machines": self.machines, "arrets": self.arrets, "energie": self.energie,
                "interventions": self.interventions, "planning": self.planning,
                "pieces": self.pieces}

    def dept_usage(self, dept_id: str) -> int:
        """Nombre d'enregistrements rattachés à un département, tous types confondus."""
        return sum(self.dept_usage_detail(dept_id).values())

    def dept_usage_detail(self, dept_id: str) -> dict:
        """Ce qui rattache encore des données à un département, type par type.

        Sert à expliquer un refus de suppression : sans ce détail, l'utilisateur
        ne sait pas où aller réaffecter ses enregistrements.
        """
        detail = {}
        for nom, coll in self._dept_collections().items():
            n = sum(1 for rec in coll if rec.get("departementId") == dept_id)
            if n:
                detail[nom] = n
        return detail

    def objectifs(self) -> dict:
        return self.settings.setdefault("objectifs", {})

    def objectif(self, metric: str):
        """Cible fixée pour un indicateur, ou None si aucune (champ vide inclus)."""
        v = self.objectifs().get(metric)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

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
            pieces=d.get("pieces", []),
            mouvements=d.get("mouvements", []),
            settings=d.get("settings", {"tempsTravail": {}}),
        )


# ---------------------------------------------------------------------------
# Persistance (SQLite par défaut, PostgreSQL via DATABASE_URL — voir admi/db.py)
# Import paresseux de la couche db pour éviter un cycle d'import.
# ---------------------------------------------------------------------------
def _dbmod():
    from . import db as _db
    return _db


def add_departement(db: Database, nom: str, court: str, couleur: str | None = None):
    """Ajoute un département, l'active partout et le persiste.

    Chemin unique, partagé par l'écran Paramètres et le raccourci du tableau de
    bord. Retourne (True, département) ou (False, message d'erreur).
    """
    nom, court = str(nom or "").strip(), str(court or "").strip()
    if not nom or not court:
        return False, "Le nom et le code court sont requis."
    couleurs = [d["couleur"] for d in config.DEPARTEMENTS]
    nouveau = {"id": config.new_dept_id(nom, [d["id"] for d in config.DEPARTEMENTS]),
               "nom": nom, "court": court.upper(),
               "couleur": couleur or config.new_dept_color(couleurs)}
    config.set_departements([*config.DEPARTEMENTS, nouveau])
    db.settings["departements"] = [dict(d) for d in config.DEPARTEMENTS]
    save_settings(db)
    return True, nouveau


def save_db(db: Database) -> None:
    """Écrit l'intégralité de l'état (utilisé pour l'import et l'amorçage démo)."""
    d = _dbmod()
    for name in d.ENTITIES:
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


# Phrase à recopier pour confirmer un effacement total : un bouton se clique par
# réflexe, une phrase se tape volontairement.
PHRASE_SUPPRESSION = "supprimer la base"


def confirmation_suppression(saisie: str) -> bool:
    """Vrai si la phrase de confirmation est écrite (casse et espaces tolérés)."""
    return " ".join(str(saisie or "").lower().split()) == PHRASE_SUPPRESSION


def load_demo() -> Database:
    """Remplace le contenu par le jeu de démonstration (bouton des Paramètres)."""
    _dbmod().engine()   # la base peut n'avoir jamais été ouverte
    config.reset_departements()
    db = generate_demo()
    save_db(db)
    return db


def wipe_all(garder_departements: bool = False) -> Database:
    """Efface les enregistrements, et selon le cas le paramétrage.

    `garder_departements` conserve la liste des départements et les horaires de
    travail : à la mise en service, on jette les données d'essai mais on garde
    un paramétrage souvent long à ressaisir.

    Les réglages sont réécrits (même vides) plutôt que supprimés : c'est ce qui
    marque la base comme initialisée et empêche la démo de revenir au lancement
    suivant.
    """
    d = _dbmod()
    d.engine()
    for name in d.ENTITIES:
        d.replace_all(name, [])
    vide = Database()
    if garder_departements:
        ancien = d.get_settings().get("settings") or {}
        for cle in ("departements", "tempsTravail"):
            if ancien.get(cle):
                vide.settings[cle] = ancien[cle]
    else:
        config.reset_departements()
    d.set_setting("settings", vide.settings)
    return vide


def load_db() -> Database:
    """Charge depuis la base.

    Première ouverture : migre l'ancien JSON s'il existe. Sinon l'application
    démarre **vide** — un logiciel livré ne s'ouvre pas sur des données
    inventées. Le jeu de démonstration s'amorce seulement si `ADMI_DEMO=1`, et
    reste chargeable à la demande depuis Paramètres.
    """
    d = _dbmod()
    d.engine()  # crée les tables si nécessaire
    if d.is_empty() and not d.get_settings().get("settings"):
        migrated = _load_json_legacy()
        if migrated is None and os.environ.get("ADMI_DEMO") != "1":
            vide = Database()
            save_settings(vide)      # marque la base : la démo ne s'invitera pas
            return vide
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
    # Les départements personnalisés priment sur la liste d'usine.
    if settings.get("departements"):
        config.set_departements(settings["departements"])
    return Database(
        machines=d.list_records("machines"),
        arrets=d.list_records("arrets"),
        energie=d.list_records("energie"),
        interventions=d.list_records("interventions"),
        planning=d.list_records("planning"),
        pieces=d.list_records("pieces"),
        mouvements=d.list_records("mouvements"),
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


# Catalogue de départ du magasin (repris de l'application d'origine) :
# désignation, département, quantité, seuil d'alerte, unité, coût unitaire, emplacement
_SEED_STOCK = [
    ("Courroie trapézoïdale A32", "am", 12, 3, "unité", 8500, "Magasin A - Rayon 2"),
    ("Roulement 6205-2RS", "sl", 20, 5, "unité", 4500, "Magasin A - Rayon 4"),
    ("Filtre à air compresseur", "srv", 6, 2, "unité", 15000, "Magasin B - Rayon 1"),
    ("Résistance chauffante 2kW", "chi", 4, 1, "unité", 22000, "Magasin B - Rayon 3"),
    ("Cylindre imprimeuse flexo", "sac", 2, 1, "unité", 180000, "Magasin A - Rayon 6"),
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

    # Magasin : catalogue de pièces de rechange
    for designation, dept, qte, seuil, unite, cout, emplacement in _SEED_STOCK:
        db.pieces.append({
            "id": uid(), "reference": "", "designation": designation, "departementId": dept,
            "quantite": qte, "seuilAlerte": seuil, "unite": unite, "coutUnitaire": cout,
            "emplacement": emplacement, "fournisseur": "",
        })

    # Horaires : Administration = 8h/j du lundi au vendredi (le reste en continu)
    db.dept_schedule("adm").update({"heuresParJour": 8, "jours": [True] * 5 + [False, False]})
    return db
