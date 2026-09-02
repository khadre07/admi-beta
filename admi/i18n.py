"""Internationalisation ADMI (français / anglais).

Approche simple : les chaînes sources restent en français ; ``t()`` renvoie la
traduction anglaise si ``lang == "en"``, sinon la chaîne d'origine. Les valeurs
canoniques (types, départements) restent en français en base — seul l'affichage
est traduit via ``type_label`` / ``dept_label``.
"""
from __future__ import annotations

from .config import MOIS as _MOIS_FR

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
    "Alimenter AMI avec vos données, ou exporter une sauvegarde": "Feed AMI with your data, or export a backup",
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
    "Machines Industrielles": "Industrial Machines",
    "Analyse des Machines Industrielles": "Industrial Machines Analysis",
    "Analyse de Maintenance Industrielle": "Industrial Maintenance Analysis",
    # Rôles / utilisateurs
    "Rôle": "Role", "Nouveau mot de passe": "New password", "Utilisateur": "User",
    "admin": "admin", "operator": "operator", "viewer": "viewer",
    "Langue": "Language",
    # Graphiques
    "heures": "hours", "Disponible": "Available", "Aucune donnée": "No data",
    "Consommation (kWh)": "Consumption (kWh)", "Correctif / autre": "Corrective / other",
    "Ajoutez des rapports d'intervention pour voir la répartition des coûts.":
        "Add intervention reports to see the cost breakdown.",
    "Saisissez ou importez la consommation énergétique.":
        "Enter or import energy consumption.",
    "Aucun relevé énergétique pour cette année.": "No energy reading for this year.",
    "Ajoutez des rapports d'intervention pour cette période.":
        "Add intervention reports for this period.",
    "Aucun arrêt sur ce filtre.": "No downtime for this filter.",
    # Lisibilité des graphiques : cible, Pareto, top machines
    "Cible": "Target", "cumulé": "cumulative", "occurrence(s)": "occurrence(s)",
    "d'arrêt cumulé": "of cumulative downtime", "Non renseigné": "Not specified",
    "Top 5 des machines les plus problématiques": "Top 5 most problematic machines",
    "Top 5 des causes d'arrêt (Pareto)": "Top 5 downtime causes (Pareto)",
    "Classées par nombre de pannes ; le temps d'arrêt cumulé apparaît au survol.":
        "Ranked by number of breakdowns; cumulative downtime shows on hover.",
    "Barres = occurrences ; le pourcentage cumulé est écrit sur chaque barre.":
        "Bars = occurrences; the cumulative percentage is written on each bar.",
    "Ajoutez des arrêts avec une cause renseignée pour voir les causes les plus fréquentes.":
        "Add downtime events with a cause to see the most frequent causes.",
    "Ce classement apparaîtra dès qu'un arrêt de type « Panne » sera saisi.":
        "This ranking appears as soon as a downtime event of type “Breakdown” is recorded.",
    # Départements (paramétrage)
    "Départements de l'usine": "Plant departments",
    "Un département ajouté ici devient immédiatement disponible dans tous les formulaires "
    "(machines, arrêts, énergie, interventions, planning, pièces) et prend sa couleur dans "
    "tous les graphiques.":
        "A department added here becomes immediately available in every form (machines, "
        "downtime, energy, interventions, schedule, parts) and carries its colour into every chart.",
    "Nom": "Name", "Code": "Code", "Couleur": "Colour", "Enregistrements": "Records",
    "Département à modifier": "Department to edit", "＋ Nouveau département": "＋ New department",
    "Nom complet": "Full name", "Code court": "Short code",
    "Enregistrer le département": "Save department",
    "Le nom et le code court sont requis.": "Name and short code are required.",
    "Département enregistré.": "Department saved.", "Département ajouté.": "Department added.",
    "Supprimer ce département": "Delete this department",
    "Suppression impossible": "Cannot delete",
    "utilisent encore ce département. Réaffectez-les à un autre "
    "département avant de le supprimer.":
        "still use this department. Reassign them to another department before deleting it.",
    "Réinitialisation impossible": "Cannot reset",
    "ces départements ajoutés sont encore utilisés :":
        "these added departments are still in use:",
    "Réaffectez leurs enregistrements avant de réinitialiser.":
        "Reassign their records before resetting.",
    "machine(s)": "machine(s)", "arrêt(s)": "downtime event(s)",
    "relevé(s) d'énergie": "energy reading(s)", "intervention(s)": "intervention(s)",
    "pièce(s)": "part(s)",
    "enregistrement(s) utilisent ce département. Si vous le supprimez, "
    "ils resteront en base mais n'afficheront plus de département reconnu.":
        "record(s) use this department. If you delete it they stay in the database but will no "
        "longer show a recognised department.",
    "Confirmez la suppression :": "Confirm deletion:", "Oui, supprimer": "Yes, delete",
    "Réinitialiser les 8 départements d'usine": "Reset to the 8 factory departments",
    "Vos ajouts et modifications de départements seront perdus. "
    "Les machines, arrêts, énergie, interventions, planning et pièces restent intacts.":
        "Your added and edited departments will be lost. Machines, downtime, energy, "
        "interventions, schedule and parts are left untouched.",
    "Oui, réinitialiser": "Yes, reset",
    # Pièces de rechange
    "Pièces de rechange": "Spare parts",
    "Stock de pièces détachées, seuils d'alerte et mouvements":
        "Spare parts stock, alert thresholds and movements",
    "＋ Nouvelle pièce": "＋ New part", "↕ Mouvement de stock": "↕ Stock movement",
    "Références en stock": "Parts in catalogue", "Valeur totale du stock": "Total stock value",
    "Sous le seuil d'alerte": "Below alert threshold", "En rupture": "Out of stock",
    "Afficher uniquement les alertes et ruptures": "Show only alerts and shortages",
    "Catalogue des pièces": "Parts catalogue", "référence(s)": "part(s)",
    "Aucune pièce ne correspond à ce filtre. Ajoutez une référence pour suivre son stock.":
        "No part matches this filter. Add a part to start tracking its stock.",
    "Historique des mouvements de stock": "Stock movement history",
    "Les entrées, sorties et ajustements de stock apparaîtront ici.":
        "Stock entries, withdrawals and adjustments will appear here.",
    "Désignation": "Description", "Réf.": "Ref.", "Emplacement": "Location",
    "Quantité": "Quantity", "Seuil": "Threshold", "Statut": "Status",
    "Coût unit.": "Unit cost", "Valeur": "Value", "Motif": "Reason",
    "Pièce": "Part", "Pièce supprimée": "Deleted part",
    "OK": "OK", "Stock bas": "Low stock", "Rupture": "Out of stock",
    "Référence (optionnel)": "Reference (optional)",
    "Département associé": "Related department", "— Non spécifié —": "— Not specified —",
    "Quantité en stock": "Quantity in stock", "Unité": "Unit",
    "Seuil d'alerte": "Alert threshold", "Coût unitaire (FCFA)": "Unit cost (FCFA)",
    "Fournisseur (optionnel)": "Supplier (optional)",
    "La désignation est requise.": "A description is required.",
    "Type de mouvement": "Movement type", "Entrée": "Entry", "Sortie": "Withdrawal",
    "Ajustement": "Adjustment", "stock actuel": "current stock",
    "Pour un ajustement, indiquez la nouvelle quantité totale.":
        "For an adjustment, enter the new total quantity.",
    "Quantité entrée ou sortie du magasin.": "Quantity entering or leaving the store.",
    "Ajoutez d'abord une pièce au catalogue.": "Add a part to the catalogue first.",
    "Fermer": "Close",
    "pièce(s) de rechange sous le seuil d'alerte": "spare part(s) below the alert threshold",
    "Voir le stock →": "View stock →", "et": "and", "autre(s)": "other(s)",
    "Planifiez des actions préventives pour suivre leur réalisation.":
        "Schedule preventive actions to track their completion.",
    # Tableau de bord — sections, jauges et objectifs
    "Performance de la maintenance": "Maintenance performance",
    "Énergie & puissance": "Energy & power",
    "Tendance pluriannuelle": "Multi-year trend",
    "Depuis 2020": "Since 2020",
    "Vue annuelle calculée sur toutes les données saisies ou importées depuis 2020, "
    "pour le département sélectionné plus haut.":
        "Yearly view computed from all data entered or imported since 2020, "
        "for the department selected above.",
    "Réalisation du préventif": "Preventive completion",
    "Réalisées": "Completed", "Réalisé": "Completed", "Arrêt": "Downtime",
    "En attente / retard": "Pending / overdue",
    "arrêt(s) sur la période": "downtime event(s) in the period",
    "action(s) planifiée(s)": "scheduled action(s)", "panne(s)": "breakdown(s)",
    "Temps moyen de réparation": "Mean time to repair",
    "Objectif": "Target", "Cible": "Target", "Indicateur": "Indicator",
    "Objectif non défini dans Paramètres": "No target set in Settings",
    "Objectifs de performance": "Performance targets",
    "Taux préventif": "Preventive rate",
    "Chaque objectif s'affiche sous son indicateur au tableau de bord, en vert s'il est tenu "
    "et en rouge sinon. Laissez un champ vide pour ne pas fixer de cible.":
        "Each target appears under its indicator on the dashboard, green when met and red "
        "otherwise. Leave a field empty to set no target.",
    "aucune": "none",
    "Valeur non numérique pour :": "Not a number for:",
    "Enregistrer les objectifs": "Save targets",
    "Objectifs enregistrés — ils apparaissent sous les indicateurs du tableau de bord.":
        "Targets saved — they now appear under the dashboard indicators.",
    # Rapports
    "Rapport de maintenance industrielle": "Industrial maintenance report",
    "AMI — Rapport de maintenance industrielle": "AMI — Industrial maintenance report",
    "Rapport de maintenance industrielle · rapport généré automatiquement":
        "Industrial maintenance report · automatically generated",
    "Période :": "Period:", "Périmètre :": "Scope:", "Généré le :": "Generated on:",
    "Généré le": "Generated on", "Indicateurs clés": "Key indicators",
    "Synthèse par département": "Summary by department", "Graphiques": "Charts",
    "Département": "Department", "Arrêt (h)": "Downtime (h)",
    "Coût maintenance": "Maintenance cost", "Énergie (kWh)": "Energy (kWh)",
    "Tendance de disponibilité": "Availability trend",
    "Tendance de disponibilité (%)": "Availability trend (%)",
    "Énergie par département (kWh)": "Energy by department (kWh)",
    # Rapport d'intervention
    "AMI — Rapport d'intervention": "AMI — Intervention report",
    "Rapport d'intervention": "Intervention report",
    "Date": "Date", "Durée": "Duration", "Travaux réalisés": "Work performed",
    "Pièces changées / réparées": "Parts replaced / repaired",
    "Désignation": "Designation", "Qté": "Qty", "Coût unit.": "Unit cost", "Total": "Total",
    "Aucune pièce": "No part", "Coût pièces": "Parts cost",
    "Coût main d'œuvre": "Labor cost", "COÛT TOTAL": "TOTAL COST",
    "Générez un rapport complet (indicateurs, graphiques, synthèse par département) au format":
        "Generate a complete report (indicators, charts, summary by department) as",
    "HTML autonome": "standalone HTML", "interactif, imprimable en PDF depuis le navigateur":
        "interactive, printable to PDF from the browser",
    "Génération du rapport en cours…": "Generating the report…",
    "⚙ Générer le rapport": "⚙ Generate report", "Intervention": "Intervention",
    "PDF indisponible": "PDF unavailable",
    # Libellés de tendance / métriques
    "Temps d'arrêt (h)": "Downtime (h)", "Coût maintenance (FCFA)": "Maintenance cost (FCFA)",
    "Consommation énergie (kWh)": "Energy consumption (kWh)", "Disponibilité (%)": "Availability (%)",
    "Métrique de tendance": "Trend metric",
    # divers UI
    "Tous les départements": "All departments",
    "Rapports d'intervention": "Intervention reports",
    "Générer un rapport d'intervention": "Generate an intervention report",
    "Répartition des arrêts par type (h)": "Downtime by type (h)",
    "Répartition par département / service": "Breakdown by department / service",
    "Part de chaque département (%)": "Share of each department (%)",
    "Relevés détaillés": "Detailed readings",
    "Bilan de puissance installée": "Installed power summary",
    "Parc machines": "Machine fleet",
    "Journal des arrêts": "Downtime log",
    # Alertes
    "Alertes": "Alerts", "Alertes e-mail / SMS en cas de panne": "Email / SMS alerts on breakdown",
    "Notifications par e-mail": "Email notifications",
    "Recevez une alerte (e-mail / SMS) en cas de nouvelle panne. Configurez le serveur d'envoi ci-dessous.":
        "Receive an alert (email / SMS) on a new breakdown. Configure the sending server below.",
    "Alertes automatiques (nouvelle panne / machine en panne)":
        "Automatic alerts (new breakdown / broken-down machine)",
    "Destinataires e-mail (séparés par des virgules)": "Email recipients (comma-separated)",
    "Utilisateur": "User", "Numéro Twilio (From)": "Twilio number (From)",
    "Numéros SMS (séparés par des virgules)": "SMS numbers (comma-separated)",
    "Enregistrer la configuration": "Save configuration", "Configuration enregistrée.": "Configuration saved.",
    "Envoyer une alerte de test": "Send a test alert",
    "Ceci est un test d'alerte AMI.": "This is an AMI test alert.",
    "Aucun canal configuré (e-mail ou SMS).": "No channel configured (email or SMS).",
    # En-têtes de tableaux & champs
    "Puissance (kW)": "Power (kW)", "Mise en service": "Commissioned", "Dépt.": "Dept.",
    "Début": "Start", "Fin": "End", "Durée (h)": "Duration (h)", "Pièces": "Parts",
    "Coût total (FCFA)": "Total cost (FCFA)", "Département / Service": "Department / Service",
    "Consommation (kWh)": "Consumption (kWh)", "Montant (FCFA)": "Amount (FCFA)",
    "Nom de la machine": "Machine name", "Type d'arrêt": "Downtime type",
    "Date de début": "Start date", "Heure de début": "Start time",
    "Date de fin": "End date", "Heure de fin": "End time",
    "Type d'intervention": "Intervention type", "Durée (h)": "Duration (h)",
    "Coût main d'œuvre (FCFA)": "Labor cost (FCFA)", "Description des travaux": "Work description",
    "Mois": "Month", "Consommation (kWh)": "Consumption (kWh)",
    "Montant facturé (FCFA)": "Billed amount (FCFA)",
    "Titre": "Title", "Répétition": "Repetition", "Machine": "Machine",
    "Filtrer par département": "Filter by department",
    "Heures / jour": "Hours / day", "Total / semaine": "Total / week", "Heures/j": "Hours/day",
    "Total/sem": "Total/week", "Rapports": "Reports", "Coût énergie total": "Total energy cost",
    "Nombre de relevés": "Number of readings",
    "Aperçu de l'import": "Import preview",
    "Confirmer l'import": "Confirm import", "Ajouter aux données existantes": "Add to existing data",
    "Remplacer les données existantes": "Replace existing data", "Mode d'import": "Import mode",
    "Machine name": "Machine name",
    "Le nom de la machine est requis.": "Machine name is required.",
    "La date de fin doit être après le début.": "End date must be after start date.",
    "Ajoutez d'abord au moins une machine (onglet Machines).":
        "Add at least one machine first (Machines tab).",
    "Le titre est requis.": "Title is required.",
    "Description des travaux": "Work description", "Coût main d'œuvre (FCFA)": "Labor cost (FCFA)",
    "Type d'arrêt": "Downtime type", "Type d'intervention": "Intervention type",
    "Aucune / ponctuelle": "None / one-off",
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


# Langue « courante » (globale) : permet à charts.py / report.py de traduire
# sans qu'on ait à leur passer la langue partout. Fixée au début de chaque run.
_CURRENT = "fr"


def set_lang(lang):
    global _CURRENT
    _CURRENT = lang if lang in LANGS else "fr"


def get_lang():
    return _CURRENT


def t(s, lang=None):
    lang = lang or _CURRENT
    return _EN.get(s, s) if lang == "en" else s


def dept_label(dept_id, nom_fr, lang=None):
    lang = lang or _CURRENT
    return _DEPT_EN.get(dept_id, nom_fr) if lang == "en" else nom_fr


def type_label(value, lang=None):
    lang = lang or _CURRENT
    return _TYPE_EN.get(value, value) if lang == "en" else value


def month(index, lang=None):
    lang = lang or _CURRENT
    return (MOIS_EN if lang == "en" else _MOIS_FR)[index]


def fmt_num(n, dec: int = 0) -> str:
    """Nombre au format français : « 12 345,7 ».

    Source unique pour les tableaux, les graphiques et les rapports — le même
    format que `separators` du template Plotly (voir `theme.register_template`).
    """
    s = f"{float(n or 0):,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", " ")
