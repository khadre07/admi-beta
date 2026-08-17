# Signature, installeurs & mise à jour

Les exécutables ADMI sont **autonomes mais non signés** : au premier lancement,
macOS (Gatekeeper) et Windows (SmartScreen) affichent un avertissement. Voici
comment produire des installeurs et signer les binaires. La signature exige
**vos propres certificats / comptes** — elle ne peut pas être faite à votre place.

---

## macOS

### Installeur .dmg (sans signature)
```bash
./.venv/bin/pyinstaller admi.spec --noconfirm   # -> dist/ADMI.app
./build_dmg.sh                                   # -> dist/ADMI.dmg
```
L'utilisateur ouvre le DMG et glisse **ADMI.app** dans **Applications**.
(Sans notarisation : 1er lancement = **clic droit → Ouvrir**.)

### Signer + notariser (compte Apple Developer, 99 $/an)
```bash
# 1. Signer l'app avec votre identité "Developer ID Application"
codesign --deep --force --options runtime \
  --sign "Developer ID Application: VOTRE NOM (TEAMID)" dist/ADMI.app

# 2. Créer le DMG puis le notariser
./build_dmg.sh
xcrun notarytool submit dist/ADMI.dmg \
  --apple-id "vous@exemple.com" --team-id "TEAMID" --password "APP-SPECIFIC-PWD" --wait

# 3. Agrafer le ticket
xcrun stapler staple dist/ADMI.dmg
```
Après notarisation, l'app s'ouvre par un simple double-clic, sans avertissement.

---

## Windows

### Installeur .exe (Inno Setup)
Sur le PC Windows, après `pyinstaller admi.spec` :
```bat
ISCC.exe windows\ADMI.iss      REM -> dist\ADMI-Setup.exe
```
(Inno Setup : https://jrsoftware.org/isdl.php)

### Signer (certificat de signature de code Windows)
```bat
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 ^
  dist\ADMI\ADMI.exe
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 ^
  dist\ADMI-Setup.exe
```
Sans signature, SmartScreen affiche « Informations complémentaires →
Exécuter quand même ». Un certificat EV supprime l'avertissement immédiatement.

---

## Linux
- **Docker** (recommandé serveur) — voir `DEPLOIEMENT.md`.
- **Binaire autonome** : artefact `ADMI-linux` de la CI, ou `pyinstaller admi.spec`
  sur une machine Linux. Un `.AppImage` peut être produit à partir de `dist/ADMI/`.

---

## Mise à jour automatique (notification)
L'application vérifie une éventuelle nouvelle version si la variable
`ADMI_UPDATE_URL` pointe vers un JSON `{"version": "...", "url": "..."}`
(voir `admi/update.py`). Si une version plus récente est publiée, une bannière
propose le lien de téléchargement. Sans cette variable, aucune requête réseau.
