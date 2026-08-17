"""Internationalisation ADMI (français / anglais).

Approche simple : les chaînes sources restent en français ; ``t()`` renvoie la
traduction anglaise si ``lang == "en"``, sinon la chaîne d'origine. Les valeurs
canoniques (types, départements) restent en français en base — seul l'affichage
est traduit via ``type_label`` / ``dept_label``.
"""
from __future__ import annotations

LANGS = {"fr": "Français", "en": "English"}

_EN = {
    # Navigation
    "Tableau de bord": "Dashboard",
    "Planning": "Schedule",
    "Machines & Puissance": "Machines & Power",
    "Temps d'arrêt": "Downtime",
    "Interventions": "Interventions",
    "Énergie": "Energy",
    "Rapports": "Reports",
    "Import / Export": "Import / Export",
    "Paramètres": "Settings",
    "Utilisateurs": "Users",
    # Sous-titres
    "Vue d'ensemble des indicateurs de maintenance": "Overview of maintenance indicators",
    "Calendrier des interventions planifiées (mois / année)": "Planned interventions calendar (month / year)",
    "Parc machines et puissance installée par département": "Machine fleet and installed power by department",
    "Journal des arrêts machines par département": "Machine downtime log by department",
    "Historique des interventions et coûts pièces / main d'œuvre": "Intervention history and parts / labor costs",
    "Suivi par département, administration et services": "Tracking by department, administration and services",
    "Générer un rapport complet (HTML / PDF)": "Generate a full report (HTML / PDF)",
    "Alimenter ADMI avec vos données, ou exporter une sauvegarde": "Feed ADMI with your data, or export a backup",
    "Heures de travail de l'usine par département": "Plant working hours by department",
    "Gestion des comptes et des rôles": "Accounts and roles management",
    # Titres de section
    "Disponibilité": "Availability",
    "Bilan de puissance installée": "Installed power summary",
    "Parc machines": "Machine fleet",
    "Journal des arrêts": "Downtime log",
    "Répartition des arrêts par type (h)": "Downtime by type (h)",
    "Rapports d'intervention": "Intervention reports",
    "Générer un rapport d'intervention": "Generate an intervention report",
    "Relevés détaillés": "Detailed readings",
    "Répartition par département / service": "Breakdown by department / service",
    "Part de chaque département (%)": "Share of each department (%)",
    "Temps d'arrêt par département (h)": "Downtime by department (h)",
    "Répartition du coût de maintenance": "Maintenance cost breakdown",
    "Consommation énergétique par département (kWh)": "Energy consumption by department (kWh)",
    "Répartition de la consommation énergétique": "Energy consumption breakdown",
    "Consommation énergétique mensuelle": "Monthly energy consumption",
    "Interventions préventif / correctif par département": "Preventive / corrective interventions by department",
    "Tendance pluriannuelle (depuis 2020)": "Multi-year trend (since 2020)",
    "Exporter les données actuelles": "Export current data",
    "Modèle d'import": "Import template",
    "Importer un fichier": "Import a file",
    "Aperçu": "Preview",
    "Heures de travail par département": "Working hours by department",
    "Comptes utilisateurs": "User accounts",
    "Ajouter un utilisateur": "Add a user",
    "Modifier / supprimer": "Edit / delete",
    # KPI
    "MTBF": "MTBF",
    "MTTR": "MTTR",
    "Coût maintenance": "Maintenance cost",
    "Temps d'arrêt cumulé": "Total downtime",
    "Énergie consommée": "Energy consumed",
    "Coût énergie": "Energy cost",
    "Puissance installée": "Installed power",
    "Arrêts enregistrés": "Recorded stops",
    "Coût total (pièces + MO)": "Total cost (parts + labor)",
    "Part préventif": "Preventive share",
    "Rapports": "Reports",
    "Coût énergie total": "Total energy cost",
    "Nombre de relevés": "Number of readings",
    "Erreurs": "Errors",
    # Filtres & communs
    "Période": "Period", "Mois": "Month", "Année": "Year", "Département": "Department",
    "Mensuelle": "Monthly", "Annuelle": "Yearly", "Tous les départements": "All departments",
    "Filtrer par département": "Filter by department", "Métrique de tendance": "Trend metric",
    "Machine": "Machine", "Type": "Type", "Statut": "Status", "Cause": "Cause",
    "Description": "Description", "Technicien(s)": "Technician(s)", "Technicien": "Technician",
    "Consommation": "Consumption", "Consommation totale": "Total consumption",
    "Modifier un enregistrement existant": "Edit an existing record",
    # Boutons
    "Enregistrer": "Save", "Annuler": "Cancel", "Supprimer": "Delete", "Fermer": "Close",
    "Se connecter": "Sign in", "Se déconnecter": "Sign out", "Activer la licence": "Activate license",
    "Générer le rapport": "Generate report", "＋ Ajouter une pièce": "＋ Add a part",
    "＋ Nouvelle machine": "＋ New machine", "＋ Nouvel arrêt": "＋ New downtime",
    "＋ Nouveau rapport": "＋ New report", "＋ Saisir une consommation": "＋ Add a reading",
    "＋ Planifier une intervention": "＋ Schedule an intervention",
    "Ajouter": "Add", "Appliquer": "Apply", "Réinit.": "Reset",
    "Enregistrer les horaires": "Save schedule",
    "⬇ Télécharger le rapport HTML": "⬇ Download HTML report",
    "⬇ Télécharger le rapport PDF": "⬇ Download PDF report",
    "⬇ Rapport d'intervention (PDF)": "⬇ Intervention report (PDF)",
    "⬇ Exporter en Excel": "⬇ Export to Excel",
    "⬇ Télécharger le modèle Excel": "⬇ Download Excel template",
    # Auth / licence / accueil
    "Chargement du tableau de bord": "Loading the dashboard",
    "Activation requise": "Activation required", "Connexion": "Sign in",
    "Démarrage du tableau de bord": "Starting the dashboard", "Chargement": "Loading",
    "Licence d'utilisation": "License", "Code de licence": "License code",
    "Nom / société (optionnel)": "Name / company (optional)",
    "Identifiant": "Username", "Mot de passe": "Password",
    "Maintenance Industrielle": "Industrial Maintenance",
    "Analyse des Données de Maintenance Industrielle": "Industrial Maintenance Data Analysis",
    # Rôles / utilisateurs
    "Rôle": "Role", "Nouveau mot de passe": "New password", "Utilisateur": "User",
    "admin": "admin", "operator": "operator", "viewer": "viewer",
    "Langue": "Language",
}

_DEPT_EN = {
    "am": "Household Goods", "ond": "Corrugations (Zinc Roofing)", "pt": "Paint",
    "chi": "Chemistry (Wood Glue)", "sac": "Bagging", "sl": "Light Structures",
    "adm": "Administration", "srv": "General Services",
}

_TYPE_EN = {
    # arrêts
    "Panne": "Breakdown", "Arrêt préventif": "Preventive stop", "Arrêt programmé": "Scheduled stop",
    "Changement de production": "Production change", "Manque matière": "Material shortage", "Autre": "Other",
    # interventions
    "Préventif": "Preventive", "Correctif": "Corrective", "Curatif d'urgence": "Emergency repair",
    "Inspection / Contrôle": "Inspection / Check", "Amélioration": "Improvement",
    # planning
    "Inspection": "Inspection", "Lubrification": "Lubrication",
    "Contrôle réglementaire": "Regulatory check", "Révision générale": "Overhaul",
    # statuts machine / planning
    "En service": "In service", "En panne": "Broken down", "En maintenance": "Under maintenance",
    "Hors service": "Out of service",
    "Planifié": "Planned", "Réalisé": "Done", "En retard": "Overdue", "Annulé": "Cancelled",
}

MOIS_EN = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def t(s, lang="fr"):
    return _EN.get(s, s) if lang == "en" else s


def dept_label(dept_id, nom_fr, lang="fr"):
    return _DEPT_EN.get(dept_id, nom_fr) if lang == "en" else nom_fr


def type_label(value, lang="fr"):
    return _TYPE_EN.get(value, value) if lang == "en" else value
