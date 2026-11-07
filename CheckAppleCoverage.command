#!/bin/bash
# Apple Coverage guided check: copy serial, open Apple, import user-copied results.
# Requires explicit human verification on Apple's website, never bypasses CAPTCHA.
set -u
export LANG=C
export LC_ALL=C
ROOT="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 required. Install: brew install python"
  read -r -p "Press Enter to close..." _
  exit 1
fi
if [ "$(uname -s)" != Darwin ]; then
  echo "Run on macOS."
  exit 1
fi
HW="$(/usr/sbin/system_profiler SPHardwareDataType 2>/dev/null || true)"
SERIAL="$(printf '%s\n' "$HW" | /usr/bin/awk -F ': ' '/Serial Number \(system\):/ {print $2;exit}')"
MODEL="$(printf '%s\n' "$HW" | /usr/bin/awk -F ': ' '/Model Identifier:/ {print $2;exit}')"
if [ -z "$SERIAL" ]; then
  echo "Unable to read Mac serial. Run MacBook Verify first or inspect System Settings."
  read -r -p "Press Enter to close..." _
  exit 2
fi
OUT="$HOME/Desktop/Apple-Coverage-$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$OUT"
echo "Serial: $SERIAL"
echo "Opening official Apple Check Coverage. Serial copied to clipboard."
/usr/bin/env python3 "$ROOT/scripts/apple_coverage.py" --serial "$SERIAL" \
  --model-identifier "$MODEL" --out-dir "$OUT" --open-official || exit 2
cat <<'EOF'

1. On Apple Check Coverage, paste serial, complete any Apple CAPTCHA/sign-in.
2. Once Apple shows coverage details, copy the RESULTS PAGE TEXT (Cmd+A, Cmd+C).
3. Return here and press Enter. The parser imports only labelled dates.
   If no date is parsable, use the date entry form in apple-coverage.html.

No Apple Account password or page token is collected.
EOF
read -r -p "Copied the Apple coverage results? Press Enter to import..." _
/usr/bin/env python3 "$ROOT/scripts/apple_coverage.py" --serial "$SERIAL" \
  --model-identifier "$MODEL" --out-dir "$OUT" --import-clipboard || true
echo
echo "Coverage report: $OUT/apple-coverage.html"
/usr/bin/open "$OUT/apple-coverage.html" 2>/dev/null || true
read -r -p "Press Enter to finish..." _
