# Déploiement ADMI — Windows, Linux, macOS

Le code est **cross-platform**. Selon la cible, trois façons de livrer.

---

## A. Obtenir les exécutables Windows / Linux / macOS SANS posséder ces machines
### (build automatique dans le cloud — recommandé)

PyInstaller **ne peut pas** construire un `.exe` Windows depuis un Mac (ni
l'inverse) : chaque exécutable doit être compilé **sur son propre système**.
La solution la plus simple est **GitHub Actions**, qui compile les trois à votre
place.

1. Mettez ce projet sur GitHub :
   ```bash
   git init && git add -A && git commit -m "ADMI"
   git branch -M main
   git remote add origin https://github.com/<vous>/admi.git
   git push -u origin main
   ```
2. Le workflow `.github/workflows/build.yml` se lance automatiquement (ou
   onglet **Actions → Build ADMI → Run workflow**).
3. En fin de build, téléchargez les **artefacts** :
   - `ADMI-windows`  → dossier avec **`ADMI.exe`**
   - `ADMI-linux`    → dossier autonome Linux
   - `ADMI-macos-intel` → `ADMI.app`

C'est la voie conseillée si vous n'avez pas de PC Windows / serveur Linux sous la main.

---

## B. Windows — construire localement (si vous avez un PC Windows)

Sur le PC Windows, avec **Python 3.11+** installé (cochez « Add to PATH ») :

```bat
pip install -r requirements.txt pyinstaller
pyinstaller admi.spec --noconfirm
```

Résultat : **`dist\ADMI\ADMI.exe`** (dossier autonome, aucun Python requis chez
le client). Distribuez tout le dossier `dist\ADMI\` (zippé). Double-clic sur
`ADMI.exe` → licence → connexion → tableau de bord.

> Astuce : si l'app ne démarre pas, éditez `admi.spec` et passez `console=False`
> à `console=True` pour voir les erreurs dans une fenêtre.

---

## C. Linux serveur — Docker (recommandé pour un serveur)

Pour un serveur, ne distribuez pas un binaire : lancez le service en conteneur.
Sur le serveur Linux (Docker installé) :

```bash
docker compose up -d --build
# ADMI est accessible sur  http://<ip-du-serveur>:8501
```

- Les données (licence, comptes, saisies) sont persistées dans le volume
  `admi-data` (voir `docker-compose.yml`).
- Placez idéalement un reverse-proxy (Nginx / Caddy / Traefik) devant pour le
  HTTPS et un nom de domaine.

### Variante sans Docker (service Python)
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
ADMI_DATA_DIR=/var/lib/admi \
  streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```
(à passer en service **systemd** pour un démarrage automatique.)

### Binaire Linux autonome
Si vous préférez un exécutable (poste Linux, pas serveur) : voir la voie **A**
(artefact `ADMI-linux`) ou lancez `pyinstaller admi.spec` sur une machine Linux.

---

## D. macOS
Déjà couvert : `dist/ADMI.app` (voir `README.md`). Build via
`pyinstaller admi.spec` sur un Mac, ou artefact `ADMI-macos-intel` de la voie A.

---

## Notes communes
- **Licence** : chaque installation demande un code (généré par `licgen`).
- **Connexion** : `admin` / `admin` par défaut (à changer).
- **Stockage** : `ADMI_DATA_DIR` force l'emplacement des données (utilisé par
  Docker) ; sinon dossier utilisateur standard selon l'OS.
- **Windows/Linux** ne sont pas signés non plus : mêmes avertissements de
  sécurité qu'sur macOS (SmartScreen sur Windows → « Informations
  complémentaires » → « Exécuter quand même »).
