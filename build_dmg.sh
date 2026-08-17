#!/usr/bin/env bash
# Crée un installeur macOS ADMI.dmg à partir de dist/ADMI.app
set -e
cd "$(dirname "$0")"

APP="dist/ADMI.app"
DMG="dist/ADMI.dmg"

if [ ! -d "$APP" ]; then
  echo "✗ $APP introuvable — construisez d'abord l'app :"
  echo "    ./.venv/bin/pyinstaller admi.spec --noconfirm"
  exit 1
fi

echo "→ Nettoyage des attributs de quarantaine…"
xattr -cr "$APP" 2>/dev/null || true

rm -f "$DMG"
STAGING="$(mktemp -d)"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"   # glisser-déposer vers Applications

echo "→ Création du DMG…"
hdiutil create -volname "ADMI" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGING"

echo "✓ Installeur créé : $DMG"
du -h "$DMG" | cut -f1
