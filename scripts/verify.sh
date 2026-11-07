#!/bin/bash
# MacBook Verify v1.1 - one-click MacBook verification + active self-test.
# Bash 3.2 compatible; no Homebrew/Python/Node dependency.

set -u
VERSION="2.0.0"
MODE="full"
OPEN_REPORT=1
OUTPUT_BASE="$HOME/Desktop"
APP_MODE=0
ACTIVE_TESTS=1
VERIFY_APFS=0
BATTERY_DISCHARGE_MINUTES=0

usage() {
  cat <<EOF
MacBook Verify v$VERSION

Usage:
  verify.sh [--quick|--full|--deep|--burn-in] [--static-only] [--no-open] [--output DIR]

Modes:
  --quick       ~1 minute: light CPU/RAM/SSD tests
  --full        Default: practical used-Mac check (~2-5 minutes)
  --deep        Longer CPU/RAM/SSD + 30-day error history
  --burn-in     3-minute CPU load plus deeper memory/storage checks

Options:
  --static-only Collect/analyze without active load/write tests
  --no-open     Do not open report.html automatically
  --output DIR  Parent directory for report folder and ZIP
  --verify-apfs          Xác minh cấu trúc APFS (không sửa ổ)
  --battery-discharge N  Quan sát pin đã rút sạc từ 1-30 phút
  --app         Internal launcher flag
  --help        Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --quick) MODE="quick"; shift ;;
    --full) MODE="full"; shift ;;
    --deep) MODE="deep"; shift ;;
    --burn-in) MODE="burn-in"; shift ;;
    --static-only) ACTIVE_TESTS=0; shift ;;
    --verify-apfs) VERIFY_APFS=1; shift ;;
    --battery-discharge) [ "$#" -ge 2 ] || { echo "ERROR: --battery-discharge needs minutes" >&2; exit 2; }; BATTERY_DISCHARGE_MINUTES="$2"; shift 2 ;;
    --no-open) OPEN_REPORT=0; shift ;;
    --output) [ "$#" -ge 2 ] || { echo "ERROR: --output requires DIR" >&2; exit 2; }; OUTPUT_BASE="$2"; shift 2 ;;
    --app) APP_MODE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$BATTERY_DISCHARGE_MINUTES" in
  ''|*[!0-9]*) echo "ERROR: --battery-discharge expects 0..30 minutes" >&2; exit 2 ;;
esac
if [ "$BATTERY_DISCHARGE_MINUTES" -gt 30 ]; then
  echo "ERROR: max 30 minutes for battery observation" >&2; exit 2
fi

if [ "$(uname -s 2>/dev/null || true)" != "Darwin" ]; then
  echo "MacBook Verify only runs on macOS." >&2
  exit 1
fi

export LANG=C
export LC_ALL=C
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

for _required in "$SCRIPT_DIR/lib/common.sh" "$SCRIPT_DIR/collectors/static.sh" "$SCRIPT_DIR/tests/active.sh" "$SCRIPT_DIR/report.sh"; do
  if [ ! -f "$_required" ]; then echo "ERROR: Missing component: $_required" >&2; exit 1; fi
  if ! /bin/bash -n "$_required"; then echo "ERROR: Syntax preflight failed: $_required" >&2; exit 1; fi
done
. "$SCRIPT_DIR/lib/common.sh"
. "$SCRIPT_DIR/collectors/static.sh"
. "$SCRIPT_DIR/tests/active.sh"
. "$SCRIPT_DIR/report.sh"

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$OUTPUT_BASE" 2>/dev/null || { echo "ERROR: Cannot create output directory: $OUTPUT_BASE" >&2; exit 1; }
OUT_DIR="$OUTPUT_BASE/MacBook-Verify-$TIMESTAMP"
RAW_DIR="$OUT_DIR/raw"
RESULTS_FILE="$OUT_DIR/results.tsv"
SCRATCH_DIR="/private/tmp/macbook-verify-${UID:-0}-$$"
mkdir -p "$RAW_DIR" "$SCRATCH_DIR" || exit 1
: > "$RESULTS_FILE"

cleanup() {
  [ -n "${SCRATCH_DIR:-}" ] && [ -d "$SCRATCH_DIR" ] && /bin/rm -rf "$SCRATCH_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

printf '\nMacBook Verify v%s\n' "$VERSION"
printf 'Mode: %s\n' "$MODE"
printf 'Output: %s\n' "$OUT_DIR"
printf 'Active tests create at most 1 GiB of temporary scratch data and remove it after the test.\n'

collect_static_data
analyze_static_data

if [ "$ACTIVE_TESTS" -eq 1 ]; then
  run_active_tests
else
  record_result Active "Active self-test suite" SKIP "Disabled" "Run without --static-only to exercise CPU, memory, storage, network and post-load battery telemetry."
fi


# Optional DriveDx-style deep SSD telemetry; never requires sudo or writes to a drive.
mbv_step "Collecting optional advanced SSD SMART telemetry"
if command -v python3 >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/ssd_diagnostics.py" ]; then
  if /usr/bin/env python3 "$SCRIPT_DIR/ssd_diagnostics.py" --out-dir "$OUT_DIR" > "$RAW_DIR/ssd-deep-console.txt" 2>&1; then
    [ -s "$OUT_DIR/ssd-results.tsv" ] && /bin/cat "$OUT_DIR/ssd-results.tsv" >> "$RESULTS_FILE"
  else
    record_result "SSD Deep" "Advanced SMART collection" INFO "Unavailable" "Optional Python3/smartctl module could not run; review raw/ssd-deep-console.txt."
    printf '<!doctype html><meta charset="utf-8"><title>SSD Deep Health</title><h1>Advanced SMART unavailable</h1><p>Review raw/ssd-deep-console.txt; built-in checks are still available.</p>\n' > "$OUT_DIR/ssd-report.html"
    printf '{"records":[],"status":"UNAVAILABLE"}\n' > "$OUT_DIR/ssd-report.json"
    : > "$OUT_DIR/ssd-results.tsv"
  fi
else
  record_result "SSD Deep" "Advanced SMART collection" INFO "Unavailable" "Python 3 not installed; built-in SSD checks remain available."
  printf '<!doctype html><meta charset="utf-8"><title>SSD Deep Health</title><h1>Advanced SMART unavailable</h1><p>Install Python 3 and smartmontools for deep telemetry.</p>\n' > "$OUT_DIR/ssd-report.html"
  printf '{"records":[],"status":"UNAVAILABLE"}\n' > "$OUT_DIR/ssd-report.json"
  : > "$OUT_DIR/ssd-results.tsv"
fi


# Apple Coverage and device provenance; no silent external serial lookup.
mbv_step "Collecting local Apple coverage and device provenance"
if command -v python3 >/dev/null 2>&1 && [ -n "${SYSTEM_SERIAL:-}" ]; then
  if /usr/bin/env python3 "$SCRIPT_DIR/apple_coverage.py" \
      --serial "$SYSTEM_SERIAL" --model-identifier "${MODEL_IDENTIFIER:-}" \
      --out-dir "$OUT_DIR" > "$RAW_DIR/apple-coverage-console.txt" 2>&1; then
    record_result Provenance "Apple coverage evidence" INFO "User-assisted" "See apple-coverage.html; dates are not automatically authenticated."
  else
    record_result Provenance "Apple coverage evidence" INFO "Unavailable" "See raw/apple-coverage-console.txt."
  fi
else
  record_result Provenance "Apple coverage evidence" INFO "Unavailable" "Python 3 and a readable serial are required."
fi


# Keep all report links valid when optional Python or Apple identity is unavailable.
if [ ! -s "$OUT_DIR/apple-coverage.html" ]; then
  printf '<!doctype html><meta charset="utf-8"><title>Apple Coverage</title><h1>Apple Coverage unavailable</h1><p>Python 3 and a valid system serial are required. On modern MacBooks, manufacturing/first-activation dates cannot be obtained from a randomized serial.</p><p><a href="https://checkcoverage.apple.com/">Open official Apple Coverage</a></p>\n' > "$OUT_DIR/apple-coverage.html"
fi
if [ ! -s "$OUT_DIR/apple-coverage.json" ]; then
  printf '{"status":"UNAVAILABLE","manufacture_date":null,"activation_date":null,"warranty_expires":null,"applecare_expires":null,"provenance":"not_available"}\n' > "$OUT_DIR/apple-coverage.json"
fi



# Independent read-only battery capacity + cell diagnostics from IOKit.
mbv_step "Analyzing AppleSmartBattery deep controller evidence"
if command -v python3 >/dev/null 2>&1; then
  if /usr/bin/env python3 "$SCRIPT_DIR/battery_diagnostics.py" \
       --out-dir "$OUT_DIR" --system-power-file "$RAW_DIR/battery-system.txt" \
       --raw-evidence-file "$RAW_DIR/battery-deep-plist.xml" \
       --machine-id "${SYSTEM_SERIAL:-local}" \
       > "$RAW_DIR/battery-deep-console.txt" 2>&1; then
    [ -s "$OUT_DIR/battery-results.tsv" ] && /bin/cat "$OUT_DIR/battery-results.tsv" >> "$RESULTS_FILE"
  else
    record_result "Battery Deep" "Controller inspection" INFO "Unavailable" "Review raw/battery-deep-console.txt"
  fi
else
  record_result "Battery Deep" "Controller inspection" INFO "Unavailable" "Python 3 required"
fi
if [ ! -s "$OUT_DIR/battery-report.html" ]; then
  printf '<!doctype html><meta charset="utf-8"><title>Battery Deep</title><h1>Battery telemetry unavailable</h1>\n' > "$OUT_DIR/battery-report.html"
fi
if [ ! -s "$OUT_DIR/battery-report.json" ]; then
  printf '{"status":"UNAVAILABLE","capacity":{"capacity_health_percent":null,"raw_health_percent":null},"diagnostic_signal_score":null}\n' > "$OUT_DIR/battery-report.json"
fi



# Professional system profiler, macOS security, ports, APFS and repair evidence.
mbv_step "Thu thập System Information tiếng Việt, CPU/GPU, APFS và bảo mật"
if command -v python3 >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/pro_inspection.py" ]; then
  _apfs_args=""
  if [ "$VERIFY_APFS" -eq 1 ]; then _apfs_args="--verify-apfs"; fi
  if /usr/bin/env python3 "$SCRIPT_DIR/pro_inspection.py" --out-dir "$OUT_DIR" \
       --raw-dir "$RAW_DIR" $_apfs_args > "$RAW_DIR/pro-inspection-console.txt" 2>&1; then
    [ -s "$OUT_DIR/pro-results.tsv" ] && /bin/cat "$OUT_DIR/pro-results.tsv" >> "$RESULTS_FILE"
  else
    record_result Pro "System Information chuyên sâu" INFO "Không khả dụng" "Xem raw/pro-inspection-console.txt."
  fi
else
  record_result Pro "System Information chuyên sâu" INFO "Chưa chạy" "Yêu cầu Python 3."
fi
if [ ! -s "$OUT_DIR/system-information.html" ]; then
  printf '<!doctype html><meta charset="utf-8"><title>System Information</title><h1>Thông tin hệ thống không khả dụng</h1>\n' > "$OUT_DIR/system-information.html"
fi
if [ ! -s "$OUT_DIR/system-information.json" ]; then
  printf '{"collection":{"status":"UNAVAILABLE"},"cpu":{},"gpu":{},"checks":[]}\n' > "$OUT_DIR/system-information.json"
fi

# Explicit battery observation: never run silently by default.
if [ "$BATTERY_DISCHARGE_MINUTES" -gt 0 ]; then
  if command -v python3 >/dev/null 2>&1; then
    if /usr/bin/env python3 "$SCRIPT_DIR/battery_discharge.py" \
        --minutes "$BATTERY_DISCHARGE_MINUTES" --out-dir "$OUT_DIR" \
        > "$RAW_DIR/battery-discharge-console.txt" 2>&1; then
      [ -s "$OUT_DIR/battery-discharge.tsv" ] && /bin/cat "$OUT_DIR/battery-discharge.tsv" >> "$RESULTS_FILE"
    else
      record_result Battery "Quan sát pin khi rút sạc" INFO "Không chạy được" "Xem raw/battery-discharge-console.txt"
    fi
  else
    record_result Battery "Quan sát pin khi rút sạc" SKIP "Thiếu Python 3" "Không thay đổi cấu hình sạc."
  fi
fi
if [ ! -s "$OUT_DIR/battery-discharge.html" ]; then
  printf '<!doctype html><meta charset="utf-8"><title>Quan sát pin</title><h1>Chưa chạy quan sát pin</h1><p>Chỉ chạy khi dùng --battery-discharge N và rút sạc.</p>\n' > "$OUT_DIR/battery-discharge.html"
fi

# Offline comparison UI; JSON file input is handled only in local browser.
if command -v python3 >/dev/null 2>&1; then
  /usr/bin/env python3 "$SCRIPT_DIR/compare_macs.py" --out-dir "$OUT_DIR" \
    > "$RAW_DIR/compare-console.txt" 2>&1 || true
fi

generate_report

mbv_step "Creating evidence manifest"
(
  cd "$OUT_DIR" || exit 1
  /usr/bin/find . -type f ! -name 'manifest.sha256' -print | /usr/bin/sort | while IFS= read -r _f; do /usr/bin/shasum -a 256 "$_f"; done
) > "$OUT_DIR/manifest.sha256" 2>/dev/null || true

ZIP_PATH="$OUTPUT_BASE/MacBook-Verify-$TIMESTAMP.zip"
mbv_step "Packaging report ZIP"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$OUT_DIR" "$ZIP_PATH" >/dev/null 2>&1 || ZIP_PATH=""

set -- $(status_counts)
_SCORE="$(health_score)"
printf '\n────────────────────────────────────────\n'
printf 'PASS %s | WARN %s | FAIL %s | INFO %s | SKIP %s\n' "$1" "$2" "$3" "$4" "$5"
printf 'Automatic health score: %s/100\n' "$_SCORE"
printf 'Report: %s\n' "$OUT_DIR/report.html"
[ -n "$ZIP_PATH" ] && printf 'ZIP:    %s\n' "$ZIP_PATH"
printf '────────────────────────────────────────\n'

if [ "$OPEN_REPORT" -eq 1 ]; then /usr/bin/open "$OUT_DIR/report.html" >/dev/null 2>&1 || true; fi
if [ "$APP_MODE" -eq 1 ]; then
  /usr/bin/osascript -e 'display notification "Verification finished. Report opened in your browser." with title "MacBook Verify"' >/dev/null 2>&1 || true
fi

cleanup
trap - EXIT INT TERM
exit 0