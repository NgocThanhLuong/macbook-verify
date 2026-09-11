#!/bin/bash
# MacBook Verify v1.0 - one-click MacBook verification + active self-test.
# Bash 3.2 compatible; no Homebrew/Python/Node dependency.

set -u
VERSION="1.0.0"
MODE="full"
OPEN_REPORT=1
OUTPUT_BASE="$HOME/Desktop"
APP_MODE=0
ACTIVE_TESTS=1

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
    --no-open) OPEN_REPORT=0; shift ;;
    --output) [ "$#" -ge 2 ] || { echo "ERROR: --output requires DIR" >&2; exit 2; }; OUTPUT_BASE="$2"; shift 2 ;;
    --app) APP_MODE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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