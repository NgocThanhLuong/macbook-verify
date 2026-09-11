#!/bin/bash
set -u
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Applications/MacBook Verify.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES_DIR="$CONTENTS/Resources"

for p in "$ROOT_DIR/scripts/verify.sh" "$ROOT_DIR/scripts/lib/common.sh" "$ROOT_DIR/scripts/collectors/static.sh" "$ROOT_DIR/scripts/tests/active.sh" "$ROOT_DIR/scripts/report.sh"; do
  [ -f "$p" ] || { echo "Missing project component: $p" >&2; exit 1; }
done

/bin/rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RES_DIR" || exit 1
/usr/bin/ditto "$ROOT_DIR/scripts" "$RES_DIR/scripts" || exit 1
[ -d "$ROOT_DIR/data" ] && /usr/bin/ditto "$ROOT_DIR/data" "$RES_DIR/data"
[ -d "$ROOT_DIR/helpers" ] && /usr/bin/ditto "$ROOT_DIR/helpers" "$RES_DIR/helpers"
/bin/chmod +x "$RES_DIR/scripts/verify.sh" "$RES_DIR/scripts/collectors/static.sh" "$RES_DIR/scripts/tests/active.sh" "$RES_DIR/scripts/report.sh" 2>/dev/null || true

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleDisplayName</key><string>MacBook Verify</string>
<key>CFBundleExecutable</key><string>MacBookVerify</string>
<key>CFBundleIdentifier</key><string>com.ngocthanhluong.macbookverify</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>MacBook Verify</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0.0</string>
<key>CFBundleVersion</key><string>100</string>
<key>LSMinimumSystemVersion</key><string>11.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

cat > "$MACOS_DIR/MacBookVerify" <<'LAUNCHER'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$(cd "$HERE/../Resources" && pwd)"
exec /bin/bash "$RES/scripts/verify.sh" --full --app
LAUNCHER
/bin/chmod +x "$MACOS_DIR/MacBookVerify"
/usr/bin/codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true
printf '\nInstalled: %s\n' "$APP_DIR"
printf 'Launching Full Check now...\n'
/usr/bin/open "$APP_DIR" >/dev/null 2>&1 || true
