#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$ROOT_DIR/scripts/verify.sh"
APP_DIR="$HOME/Applications/MacBook Verify.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES_DIR="$CONTENTS/Resources"

if [ ! -f "$SOURCE" ]; then
  echo "Cannot find: $SOURCE" >&2
  exit 1
fi

mkdir -p "$MACOS_DIR" "$RES_DIR" || exit 1
cp "$SOURCE" "$RES_DIR/verify.sh" || exit 1
chmod +x "$RES_DIR/verify.sh"

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleDisplayName</key><string>MacBook Verify</string>
  <key>CFBundleExecutable</key><string>MacBookVerify</string>
  <key>CFBundleIdentifier</key><string>com.ngocthanhluong.macbookverify</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>MacBook Verify</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/MacBookVerify" <<'LAUNCHER'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$(cd "$HERE/../Resources" && pwd)"
exec /bin/bash "$RESOURCES/verify.sh" --app
LAUNCHER
chmod +x "$MACOS_DIR/MacBookVerify"

/usr/bin/codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true

printf '\nInstalled: %s\n' "$APP_DIR"
printf 'Launching MacBook Verify now...\n'
/usr/bin/open "$APP_DIR" >/dev/null 2>&1 || true
