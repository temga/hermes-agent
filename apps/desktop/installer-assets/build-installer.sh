#!/bin/bash
# build-installer.sh — CI-adapted version of build-installer.command
# Creates a styled DMG from Hermes.zip with custom icon + background.
#
# Usage: build-installer.sh <source.zip> <output.dmg> [assets-dir]
#   <source.zip>   — path to Hermes.zip (adhoc-signed .app archive)
#   <output.dmg>   — path for output Hermes-Installer.dmg
#   [assets-dir]   — directory containing installer-icon-black-orange.png
#                    and dmg-background.png (default: script's dir)
set -euo pipefail

SOURCE_ZIP="${1:?Usage: build-installer.sh <source.zip> <output.dmg> [assets-dir]}"
OUTPUT_DMG="${2:?Output DMG path required}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSETS_DIR="${3:-$SCRIPT_DIR}"
SOURCE_ICON="$ASSETS_DIR/installer-icon-black-orange.png"
BACKGROUND="$ASSETS_DIR/dmg-background.png"
VOLUME_NAME="Hermes Installer"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Этот сборщик нужно запускать на Mac."
  exit 1
fi

for required in "$SOURCE_ZIP" "$SOURCE_ICON" "$BACKGROUND"; do
  if [[ ! -f "$required" ]]; then
    echo "Не найден файл: $required"
    exit 1
  fi
done

for tool in ditto sips iconutil hdiutil osascript; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Не найдена системная утилита: $tool"
    exit 1
  fi
done

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hermes-installer.XXXXXX")"
MOUNTED_DEVICE=""

cleanup() {
  if [[ -n "$MOUNTED_DEVICE" ]]; then
    hdiutil detach "$MOUNTED_DEVICE" -quiet >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "1/6  Распаковка Hermes…"
ditto -x -k "$SOURCE_ZIP" "$WORK_DIR/source"
APP="$WORK_DIR/source/Hermes.app"

if [[ ! -d "$APP" ]]; then
  echo "В Hermes.zip не найден Hermes.app"
  exit 1
fi

echo "2/6  Создание иконки установочного образа…"
ICONSET="$WORK_DIR/HermesInstaller.iconset"
mkdir -p "$ICONSET"
sips -z 16 16     "$SOURCE_ICON" --out "$ICONSET/icon_16x16.png" >/dev/null
sips -z 32 32     "$SOURCE_ICON" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
sips -z 32 32     "$SOURCE_ICON" --out "$ICONSET/icon_32x32.png" >/dev/null
sips -z 64 64     "$SOURCE_ICON" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
sips -z 128 128   "$SOURCE_ICON" --out "$ICONSET/icon_128x128.png" >/dev/null
sips -z 256 256   "$SOURCE_ICON" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256   "$SOURCE_ICON" --out "$ICONSET/icon_256x256.png" >/dev/null
sips -z 512 512   "$SOURCE_ICON" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512   "$SOURCE_ICON" --out "$ICONSET/icon_512x512.png" >/dev/null
sips -z 1024 1024 "$SOURCE_ICON" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET" -o "$WORK_DIR/VolumeIcon.icns"

echo "3/6  Проверка приложения без внесения изменений…"
if codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1; then
  echo "     Текущая подпись Hermes.app корректна."
else
  echo "     Предупреждение: текущая подпись Hermes.app не прошла проверку."
  echo "     Приложение не изменяется и не переподписывается."
fi

echo "4/6  Подготовка окна установщика…"
DMG_ROOT="$WORK_DIR/dmg-root"
mkdir -p "$DMG_ROOT/.background"
ditto "$APP" "$DMG_ROOT/Hermes.app"
ln -s /Applications "$DMG_ROOT/Applications"
cp "$BACKGROUND" "$DMG_ROOT/.background/background.png"
cp "$WORK_DIR/VolumeIcon.icns" "$DMG_ROOT/.VolumeIcon.icns"

RW_DMG="$WORK_DIR/Hermes-Installer-rw.dmg"
SIZE_MB="$(du -sm "$DMG_ROOT" | awk '{print $1 + 50}')"
hdiutil create -quiet -ov -format UDRW -fs HFS+ \
  -volname "$VOLUME_NAME" -size "${SIZE_MB}m" -srcfolder "$DMG_ROOT" "$RW_DMG"

ATTACH_OUTPUT="$(hdiutil attach -readwrite -noverify -noautoopen "$RW_DMG")"
MOUNTED_DEVICE="$(printf '%s\n' "$ATTACH_OUTPUT" | awk '/Apple_HFS/ {print $1; exit}')"
MOUNT_DIR="$(printf '%s\n' "$ATTACH_OUTPUT" | awk -F '\t' '/Apple_HFS/ {print $NF; exit}')"

if command -v SetFile >/dev/null 2>&1; then
  SetFile -a C "$MOUNT_DIR"
fi

echo "5/6  Оформление DMG…"
osascript <<APPLESCRIPT
tell application "Finder"
  tell disk "$VOLUME_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set pathbar visible of container window to false
    set bounds of container window to {200, 120, 900, 600}
    set theViewOptions to icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 112
    set text size of theViewOptions to 13
    set background picture of theViewOptions to file ".background:background.png"
    set position of item "Hermes.app" of container window to {170, 180}
    set position of item "Applications" of container window to {530, 180}
    update without registering applications
    delay 2
    close
    open
    delay 2
  end tell
end tell
APPLESCRIPT

sync
hdiutil detach "$MOUNTED_DEVICE" -quiet
MOUNTED_DEVICE=""

echo "6/6  Сжатие и проверка образа…"
rm -f "$OUTPUT_DMG"
hdiutil convert "$RW_DMG" -quiet -format UDZO -imagekey zlib-level=9 -o "$OUTPUT_DMG"
hdiutil verify "$OUTPUT_DMG" >/dev/null

echo
echo "Готово: $OUTPUT_DMG"
